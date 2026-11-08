from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from livetune import controller as control
from livetune import advisor, loadgen, trace, tune
from livetune.metrics import window
from livetune.policy import Policy, Slo
from livetune.server import KV_TOLERANCE, Server


def _value(raw: str) -> Any:
    if raw == "null":
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def _corpus(path: str) -> list[int]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "prompts" in data:
        return [token for prompt in data["prompts"] for token in prompt]
    return list(data)


def _appender(path: str | None, mode: str = "a"):
    handle = open(path, mode) if path else None

    def write(event: Any) -> None:
        line = event if isinstance(event, str) else json.dumps(event)
        print(line, flush=True)
        if handle:
            handle.write(line + "\n")
            handle.flush()

    return write


def _differences(expected: dict[str, Any], actual: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted(set(expected) | set(actual)):
        a, b = expected.get(key), actual.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            out.update(_differences(a, b, f"{prefix}{key}."))
        elif a != b:
            out[prefix + key] = (a, b)
    return out


def load_policy(path: str, server: Server, allow_scope_mismatch: bool) -> Policy:
    policy = Policy.load(path)
    expected, actual = policy.provenance.get("scope"), server.fingerprint()
    if expected is None and not allow_scope_mismatch:
        raise SystemExit(f"{path} records no tuning scope; rebuild it with `livetune policy`, or pass --allow-scope-mismatch")
    if expected is not None and not allow_scope_mismatch:
        differs = _differences(expected, actual)
        # Free memory varies a little between starts; a policy holds within a few percent of its KV capacity.
        kv = differs.get("kv_tokens")
        if kv and all(kv) and abs(kv[1] - kv[0]) <= KV_TOLERANCE * kv[0]:
            del differs["kv_tokens"]
        if not differs:
            return policy
        raise SystemExit(f"{path} was tuned for a different server (policy, live): {differs}; pass --allow-scope-mismatch to override")
    return policy


def replay(args: argparse.Namespace, server: Server) -> None:
    import threading

    policy = load_policy(args.policy, server, args.allow_scope_mismatch)
    write = _appender(args.out)
    startup = server.livetune_state()["startup"]
    server.apply(startup)
    stop = threading.Event()
    events: list[dict[str, Any]] = []
    failures: list[BaseException] = []
    step_lock = threading.Lock()
    thread = None
    if not args.static:
        # Seeded from readback, so the first rule changes only what differs and starts no variant cooldown.
        controller = control.Controller(policy, startup=startup, applied=dict(server.livetune_state()["settings"]))

        def log(event: dict[str, Any]) -> None:
            events.append(event)
            write({"controller": event})

        def run_controller() -> None:
            try:
                control.run(controller, server.scrape, server.apply, window, interval_s=args.interval, log=log, stop=stop.is_set,
                            sleep=stop.wait, step_lock=step_lock)
            except BaseException as exc:
                failures.append(exc)
                raise

        thread = threading.Thread(target=run_controller, daemon=True)
        thread.start()

    def stop_controller() -> None:
        stop.set()
        if thread is not None:
            thread.join()

    try:
        prompts = loadgen.PromptSource(_corpus(args.corpus))
        segments = _segments(args, prompts)
        for index, run_segment in enumerate(segments):
            started = time.time()
            summary = run_segment()
            if index == len(segments) - 1:
                # Join first, so a failure while the last phase ran cannot slip past this check.
                stop_controller()
            # Waits out a window still applying, so every event that started in this phase is counted.
            with step_lock:
                if failures:
                    raise RuntimeError("the controller stopped during the replay; its results are not controlled") from failures[0]
                write(phase_report(summary, events, started, time.time() - started, policy, "static" if args.static else "controlled"))
    finally:
        stop_controller()
        server.apply(startup)


def _segments(args: argparse.Namespace, prompts: loadgen.PromptSource) -> list[Any]:
    """What a replay plays: scripted closed-loop phases, or recorded traffic arriving open loop."""
    import asyncio

    if args.trace:
        arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed)
        if not arrivals:
            raise SystemExit(f"no records in {args.trace}")
        return [lambda: asyncio.run(loadgen.run_arrivals(args.url, arrivals, prompts)).summary()]
    phases = [loadgen.Phase(**p) for p in json.loads(Path(args.phases).read_text())]
    return [lambda phase=phase, index=index: asyncio_phase(args.url, phase, prompts, index) for index, phase in enumerate(phases)]


def tune_policy(
    server: Server,
    slo: Slo,
    prompts: loadgen.PromptSource,
    grid: dict[str, list[Any]],
    profiles: list[dict[str, Any]] | None,
    arrivals: list[trace.Arrival] | None,
    seconds: float,
    warmup: float,
    record: Any,
) -> Policy:
    """Measure each grid value against the startup settings, per profile or against recorded traffic."""
    import asyncio

    start = dict(server.livetune_state()["startup"])
    scope = server.fingerprint()

    def measure(profile: tune.Profile, settings: dict[str, Any]) -> dict[str, Any]:
        server.apply(settings)
        if arrivals is not None:
            # Every candidate meets the same recorded traffic, arriving at its recorded times.
            summary = asyncio.run(loadgen.run_arrivals(server.url, arrivals, prompts, name=profile.name)).summary()
        else:
            if warmup:
                loadgen.run(server.url, [profile.phase(warmup)], prompts, log=lambda _: None)
            summary = loadgen.run(server.url, [profile.phase(seconds)], prompts, log=lambda _: None)[0]
        record({"profile": profile.name, "settings": settings, "summary": summary, "scope": scope})
        return summary

    profiles = profiles if profiles is not None else [tune.trace_profile(arrivals or [])]
    tune.check_distinguishable(profiles)
    try:
        results = [tune.tune_profile(tune.Profile(**p), start, grid, slo, measure) for p in profiles]
    finally:
        server.apply(start)
    return tune.build_policy(results, slo, {"tuned_at": time.time(), "url": server.url, "scope": scope}, start)


def improve(args: argparse.Namespace, server: Server) -> None:
    """Keep improving: advise from production, measure the proposals on a canary against the
    production traffic just recorded, and publish a policy only when something beat startup."""
    canary = Server(args.canary)
    out = Path(args.work_dir)
    out.mkdir(parents=True, exist_ok=True)
    write = _appender(str(out / "improve.jsonl"))
    while True:
        started = time.time()
        report = advise(argparse.Namespace(seconds=args.advise_seconds, interval=args.interval, trace_dir=args.trace_dir), server)
        entry: dict[str, Any] = {"t": started, "proposals": report["proposals"], "grid": report["grid"]}
        differs = _differences(server.fingerprint(), canary.fingerprint())
        kv = differs.get("kv_tokens")
        if kv and all(kv) and abs(kv[1] - kv[0]) <= KV_TOLERANCE * kv[0]:
            del differs["kv_tokens"]
        records = list(trace.read([args.trace_dir], since=started - args.window))
        if differs:
            # A canary that differs from production would measure another intervention.
            entry["skipped"] = {"canary_scope_differs": sorted(differs)}
        elif not report["grid"] or not records:
            entry["skipped"] = "nothing to test" if not report["grid"] else "no recorded traffic"
        else:
            snapshot = out / f"trace-{int(started)}.jsonl"
            snapshot.write_text("".join(r.to_json() + "\n" for r in records))
            policy = tune_policy(canary, Slo(args.slo_tps, args.slo_ttft), loadgen.PromptSource(_corpus(args.corpus)), report["grid"],
                                 None, trace.arrivals(records, speed=args.speed), 0, 0, _appender(str(out / f"trials-{int(started)}.jsonl")))
            winner = policy.rule("trace").settings
            entry["winner"] = winner
            if winner != policy.rule("unmeasured").settings:
                tmp = Path(args.policy_out + ".tmp")
                tmp.write_text(policy.to_json())
                tmp.replace(args.policy_out)  # controllers reload a complete file, never a partial one
                entry["published"] = args.policy_out
        write(entry)
        if args.once:
            return
        time.sleep(max(args.every - (time.time() - started), 0))


def advise(args: argparse.Namespace, server: Server) -> dict[str, Any]:
    """Watch the server for a while, then propose experiments from what it saw."""
    before = server.livetune_state()
    started_wall = time.time()
    windows, previous = [], server.scrape()
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        time.sleep(args.interval)
        current = server.scrape()
        windows.append(window(previous, current))
        previous = current
    after = server.livetune_state()
    records = list(trace.read([args.trace_dir], since=started_wall)) if args.trace_dir else []
    batches = trace.batch_deltas((before.get("telemetry") or {}).get("batches", {}), (after.get("telemetry") or {}).get("batches", {}))
    evidence = advisor.Evidence(
        windows=windows,
        traffic=trace.summarize(records),
        batches=batches,
        settings=after.get("settings", {}),
        startup=after.get("startup", {}),
        kv_capacity=int(server.info().get("max_total_num_tokens") or 0),
        page_size=int(after.get("page_size") or 1),
    )
    proposals = advisor.advise(evidence)
    utilization = {
        "forward_share": round(evidence.mean("forward_share"), 3),
        "eviction_share": round(evidence.mean("eviction_share"), 3),
        "kv_free_share": round(evidence.mean("kv_free_share"), 4),
        "output_tps": round(evidence.mean("output_tps"), 1),
    }
    return {"utilization": utilization, "traffic": evidence.traffic, "batches": batches, "proposals": advisor.to_json(proposals), "grid": advisor.as_grid(proposals)}


def phase_report(summary: dict[str, Any], events: list[dict[str, Any]], started: float, seconds: float, policy: Policy, mode: str) -> dict[str, Any]:
    during = [e for e in events if started <= e["wall"] <= started + seconds]
    switches = [e for e in during if "action" in e]
    apply_errors = sum("error" in e["action"] for e in switches)
    return {
        **summary,
        "mode": mode,
        # A rejected apply leaves traffic on settings the controller did not choose; such a phase is not controlled evidence.
        "apply_errors": apply_errors,
        "valid": apply_errors == 0,
        # Both halves of the SLO must be measured for a phase to pass or fail it.
        "slo_met": None if None in (summary["tps_per_user_p50"], summary["ttft_p90"]) else policy.slo.met(summary["tps_per_user_p50"], summary["ttft_p90"]),
        "rules": sorted({e["rule"] for e in during if e.get("rule")}),
        "first_switch_s": round(switches[0]["wall"] - started, 1) if switches else None,
    }


def asyncio_phase(url: str, phase: loadgen.Phase, prompts: loadgen.PromptSource, index: int) -> dict[str, Any]:
    import asyncio

    return asyncio.run(loadgen.run_phase(url, phase, prompts, index)).summary()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="livetune")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "set", "load", "tune", "control", "replay", "policy", "traffic", "advise", "improve"):
        p = sub.add_parser(name)
        p.add_argument("--url", default="http://127.0.0.1:30000")
    sub.choices["set"].add_argument("pairs", nargs="+")
    for name in ("load", "tune", "replay"):
        sub.choices[name].add_argument("--corpus", required=True)
        sub.choices[name].add_argument("--out", required=name == "tune")
    sub.choices["load"].add_argument("--phases", required=True)
    r = sub.choices["replay"]
    source = r.add_mutually_exclusive_group(required=True)
    source.add_argument("--phases", help="closed-loop phases (JSON list)")
    source.add_argument("--trace", help="recorded traffic (trace directory or file), replayed open loop")
    r.add_argument("--speed", type=float, default=1.0, help="trace time compression: 2 replays twice as fast")
    r.add_argument("--policy", required=True)
    r.add_argument("--static", action="store_true", help="hold the startup settings instead of running the controller")
    r.add_argument("--interval", type=float, default=5.0)
    for name in ("control", "replay"):
        sub.choices[name].add_argument("--allow-scope-mismatch", action="store_true", help="use a policy tuned on a different model, layout or GPU")
    t = sub.choices["tune"]
    workload = t.add_mutually_exclusive_group(required=True)
    workload.add_argument("--profiles", help="closed-loop profiles (JSON list)")
    workload.add_argument("--trace", help="recorded traffic to measure every candidate against, open loop")
    t.add_argument("--speed", type=float, default=1.0, help="trace time compression")
    t.add_argument("--grid", required=True)
    t.add_argument("--slo-tps", type=float, required=True)
    t.add_argument("--slo-ttft", type=float, required=True)
    t.add_argument("--seconds", type=float, default=40)
    t.add_argument("--warmup", type=float, default=10)
    pol = sub.choices["policy"]
    pol.add_argument("--trials", required=True)
    pol.add_argument("--slo-tps", type=float, required=True)
    pol.add_argument("--slo-ttft", type=float, required=True)
    pol.add_argument("--out", required=True)
    tr = sub.choices["traffic"]
    tr.add_argument("--trace-dir", required=True)
    tr.add_argument("--since", type=float, default=0.0, help="wall-clock seconds; 0 reads everything")
    a = sub.choices["advise"]
    a.add_argument("--seconds", type=float, default=300)
    a.add_argument("--interval", type=float, default=5.0)
    a.add_argument("--trace-dir", help="the server's LIVETUNE_TRACE_DIR, for the traffic mix")
    a.add_argument("--out", help="write the report here as well")
    im = sub.choices["improve"]
    im.add_argument("--canary", required=True, help="a server with the production scope that only replayed traffic reaches")
    im.add_argument("--trace-dir", required=True)
    im.add_argument("--corpus", required=True)
    im.add_argument("--slo-tps", type=float, required=True)
    im.add_argument("--slo-ttft", type=float, required=True)
    im.add_argument("--policy-out", required=True, help="where controllers read their policy")
    im.add_argument("--work-dir", required=True)
    im.add_argument("--every", type=float, default=3600)
    im.add_argument("--window", type=float, default=600, help="seconds of recorded traffic to replay")
    im.add_argument("--advise-seconds", type=float, default=300)
    im.add_argument("--interval", type=float, default=5.0)
    im.add_argument("--speed", type=float, default=1.0)
    im.add_argument("--once", action="store_true")
    c = sub.choices["control"]
    c.add_argument("--policy", required=True)
    c.add_argument("--interval", type=float, default=5.0)
    c.add_argument("--log")
    c.add_argument("--mode", choices=("act", "observe"), default="act", help="observe logs decisions without applying them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = Server(args.url)

    if args.command == "traffic":
        print(json.dumps(trace.summarize(list(trace.read([args.trace_dir], since=args.since))), indent=1))
        return 0
    if args.command == "advise":
        report = advise(args, server)
        if args.out:
            Path(args.out).write_text(json.dumps(report, indent=1))
        print(json.dumps(report, indent=1))
        return 0
    if args.command == "improve":
        improve(args, server)
        return 0
    if args.command == "status":
        print(json.dumps(server.livetune_state(), indent=1))
    elif args.command == "set":
        settings = dict((k, _value(v)) for k, v in (pair.split("=", 1) for pair in args.pairs))
        started = time.perf_counter()
        server.apply(settings)
        print(json.dumps({"applied": settings, "seconds": round(time.perf_counter() - started, 3)}))
    elif args.command == "load":
        phases = [loadgen.Phase(**p) for p in json.loads(Path(args.phases).read_text())]
        loadgen.run(args.url, phases, loadgen.PromptSource(_corpus(args.corpus)), log=_appender(args.out))
    elif args.command == "tune":
        grid = json.loads(Path(args.grid).read_text())
        # An `advise` report carries its live proposals as a grid.
        grid = grid["grid"] if "proposals" in grid else grid
        arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed) if args.trace else None
        profiles = json.loads(Path(args.profiles).read_text()) if args.profiles else None
        policy = tune_policy(server, Slo(args.slo_tps, args.slo_ttft), loadgen.PromptSource(_corpus(args.corpus)), grid,
                             profiles, arrivals, args.seconds, args.warmup, _appender(args.out + ".trials.jsonl", mode="w"))
        Path(args.out).write_text(policy.to_json())
        print(policy.to_json())
    elif args.command == "policy":
        slo = Slo(args.slo_tps, args.slo_ttft)
        trials = [json.loads(line) for line in Path(args.trials).read_text().splitlines() if line.strip()]
        scopes = {json.dumps(t.get("scope"), sort_keys=True) for t in trials}
        if len(scopes) != 1 or "null" in scopes:
            raise SystemExit("trials must all record the same tuning scope; rerun tune for older or mixed trial files")
        scope = trials[0]["scope"]
        start = scope["startup"]
        policy = tune.build_policy(tune.best_from_trials(trials, slo, start), slo, {"trials": args.trials, "scope": scope}, start)
        Path(args.out).write_text(policy.to_json())
        print(policy.to_json())
    elif args.command == "replay":
        replay(args, server)
    elif args.command == "control":
        policy = load_policy(args.policy, server, args.allow_scope_mismatch)
        acting = args.mode == "act"
        live = server.livetune_state()
        controller = control.Controller(policy, startup=live["startup"], applied=dict(live["settings"]), judge_changes=acting)
        apply = server.apply if acting else (lambda settings: None)
        log = _appender(args.log)
        seen = Path(args.policy).stat().st_mtime

        def scrape() -> Any:
            # A republished policy takes effect at the next window; one that fails its scope check is ignored.
            nonlocal seen
            mtime = Path(args.policy).stat().st_mtime
            if mtime != seen:
                seen = mtime
                try:
                    controller.replace_policy(load_policy(args.policy, server, args.allow_scope_mismatch))
                    log({"t": time.time(), "policy_reloaded": args.policy})
                except (SystemExit, ValueError, OSError) as exc:
                    log({"t": time.time(), "policy_rejected": str(exc)})
            return server.scrape()

        control.run(controller, scrape, apply, window, interval_s=args.interval, log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
