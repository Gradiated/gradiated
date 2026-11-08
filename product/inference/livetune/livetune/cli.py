from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from livetune import controller as control
from livetune import advisor, loadgen, rollout, trace, tune
from livetune.knobs import VARIANT_KEY
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
        differs = _scope_differences(expected, actual)
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
        try:
            arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed)
        except ValueError as exc:
            raise SystemExit(f"{args.trace}: {exc}") from exc
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
    # Every candidate and confirmation run sends the same token ids; content changes MoE routing.
    trace_ids = loadgen.trace_prompts(arrivals, prompts) if arrivals is not None else None
    if arrivals is not None and "stream_interval" in grid and any((a.max_new_tokens or 0) > a.output_tokens for a in arrivals):
        # An early-stopped request is cut off at a chunk boundary, so larger chunks overrun its recorded
        # output by up to stream_interval - 1 tokens and would be measured on more work.
        logging.getLogger(__name__).warning("dropping stream_interval from the grid: the trace has early-stopped requests")
        grid = {knob: values for knob, values in grid.items() if knob != "stream_interval"}

    def measure(profile: tune.Profile, settings: dict[str, Any]) -> dict[str, Any]:
        server.apply(settings)
        # Every measurement starts from the same cold prefix cache; a cache warmed by the previous
        # trial would favour whichever candidate ran later.
        server.flush_cache()
        if arrivals is not None:
            # Every candidate meets the same recorded traffic, arriving at its recorded times.
            summary = asyncio.run(loadgen.run_arrivals(server.url, arrivals, trace_ids, name=profile.name)).summary()
        else:
            if warmup:
                loadgen.run(server.url, [profile.phase(warmup)], prompts, log=lambda _: None)
            summary = loadgen.run(server.url, [profile.phase(seconds)], prompts, log=lambda _: None)[0]
        # The workload mode decides which caps can bind when `policy` rebuilds from these trials.
        record({"profile": profile.name, "open_loop": profile.open_loop, "settings": settings, "summary": summary, "scope": scope})
        return summary

    profiles = profiles if profiles is not None else [tune.trace_profile(arrivals or [])]
    tune.check_distinguishable(profiles)
    try:
        results = [tune.tune_profile(tune.Profile(**p), start, grid, slo, measure) for p in profiles]
    finally:
        server.apply(start)
    return tune.build_policy(results, slo, {"tuned_at": time.time(), "url": server.url, "scope": scope}, start)


def variant_eval(args: argparse.Namespace, server: Server) -> dict[str, Any]:
    """Try one forward variant live on a canary: gate it against stock, measure it, and switch back.

    The variant is registered under its content hash, so every revision gets its own pinned id.
    The canary must run with LIVETUNE_LIVE_VARIANTS=1 and share LIVETUNE_VARIANTS_DIR with this host.
    """
    import asyncio
    import hashlib

    from livetune import gate, variants

    code = Path(args.variant).read_text()
    name = f"{args.name}-{hashlib.sha256(code.encode()).hexdigest()[:10]}"
    variant_id = variants.register(args.variants_dir, name, code)
    source = loadgen.PromptSource(_corpus(args.corpus), seed=args.seed)
    prompts = [source.family_prompt(args.prompt_tokens, 0, None) for _ in range(args.prompts)]
    # Baselines are always stock, whatever the canary was running; that is restored at the end.
    incumbent = server.livetune_state()["settings"].get(VARIANT_KEY, variants.STOCK)
    stock_id = variants.STOCK
    report: dict[str, Any] = {"variant": name, "id": variant_id, "incumbent": incumbent}
    try:
        server.apply({VARIANT_KEY: stock_id})
        stock, stock_again = server.greedy(prompts, args.tokens), server.greedy(prompts, args.tokens)
        started = time.monotonic()
        server.apply({VARIANT_KEY: variant_id})
        report["switch_s"] = round(time.monotonic() - started, 1)
        verdict = gate.judge(stock, stock_again, server.greedy(prompts, args.tokens))
        report["gate"] = dataclasses.asdict(verdict)
        if verdict.passed and args.trace:
            arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed)
            ids = loadgen.trace_prompts(arrivals, source)
            runs: dict[str, list[dict[str, Any]]] = {"variant": [], "stock": []}
            # Interleaved, and every run starts from a flushed cache, so order and warmth cancel out.
            for label in ("variant", "stock", "variant", "stock"):
                server.apply({VARIANT_KEY: variant_id if label == "variant" else stock_id})
                server.flush_cache()
                runs[label].append(asyncio.run(loadgen.run_arrivals(server.url, arrivals, ids, name=label)).summary())
            merged = {label: tune.merged(summaries) for label, summaries in runs.items()}
            report["performance"] = merged
            if args.slo_tps is not None and args.slo_ttft is not None:
                report["faster"] = tune._wins(merged["variant"], merged["stock"], Slo(args.slo_tps, args.slo_ttft), 0.02)
        report["decision"] = "keep" if verdict.passed and report.get("faster", True) else "reject"
    finally:
        server.apply({VARIANT_KEY: incumbent})
    return report


def improve(args: argparse.Namespace, server: Server) -> None:
    """Keep improving: advise from production, measure the proposals on a canary against the
    production traffic just recorded, and publish a policy only when something beat startup."""
    canary = Server(args.canary)
    out = Path(args.work_dir)
    # Snapshots copy Confidential trace records, so the work directory is the owner's only.
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.chmod(0o700)
    write = _appender(str(out / "improve.jsonl"))
    while True:
        started = time.time()
        report = advise(argparse.Namespace(seconds=args.advise_seconds, interval=args.interval, trace_dir=args.trace_dir), server)
        entry: dict[str, Any] = {"t": started, "proposals": report["proposals"], "grid": report["grid"]}
        differs = _scope_differences(server.fingerprint(), canary.fingerprint())
        # The window ends now, after advising, so it is the trailing --window seconds and no more.
        records = list(trace.read([args.trace_dir], since=time.time() - args.window))
        if differs:
            # A canary that differs from production would measure another intervention.
            entry["skipped"] = {"canary_scope_differs": sorted(differs)}
        elif not report["grid"] or not records:
            entry["skipped"] = "nothing to test" if not report["grid"] else "no recorded traffic"
        elif gaps := trace.replay_gaps(records):
            # Replay would send these as plain requests and tune for a different workload.
            entry["skipped"] = {"unreproducible_modes": gaps}
        else:
            snapshot = out / f"trace-{int(started)}.jsonl"
            with os.fdopen(os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
                handle.write("".join(r.to_json() + "\n" for r in records))
            policy = tune_policy(canary, Slo(args.slo_tps, args.slo_ttft), loadgen.PromptSource(_corpus(args.corpus)), report["grid"],
                                 None, trace.arrivals(records, speed=args.speed), 0, 0, _appender(str(out / f"trials-{int(started)}.jsonl")))
            winner = policy.rule("trace").settings
            entry["winner"] = winner
            if winner != policy.rule("unmeasured").settings:
                staged_before = Path(args.stage_policy).read_text() if args.stage_url else None
                verdict = stage(args, server, policy) if args.stage_url else None
                if verdict is not None:
                    entry["stage"] = dataclasses.asdict(verdict)
                if verdict is None or verdict.decision == "promote":
                    entry["published"] = args.policy_out
                    guard = promote(args, server, policy)
                    if guard is not None:
                        entry["guard"] = dataclasses.asdict(guard)
                        if guard.decision == "revert" and staged_before is not None:
                            # The staged replica still runs the candidate the fleet just rejected.
                            _publish(args.stage_policy, staged_before)
        write(entry)
        if args.once:
            return
        time.sleep(max(args.every - (time.time() - started), 0))


def _scope_differences(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    differs = _differences(expected, actual)
    # Free memory varies a little between starts; a policy holds within a few percent of its KV capacity.
    kv = differs.get("kv_tokens")
    if kv and all(kv) and abs(kv[1] - kv[0]) <= KV_TOLERANCE * kv[0]:
        del differs["kv_tokens"]
    return differs


def _publish(path: str, text: str) -> None:
    tmp = Path(path + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)  # controllers reload a complete file, never a partial one


def _watch(servers: list[Server], seconds: float, interval: float) -> list[list[Any]]:
    """Metric windows from several servers over the same span."""
    windows: list[list[Any]] = [[] for _ in servers]
    previous = [s.scrape() for s in servers]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(interval)
        for i, s in enumerate(servers):
            try:
                current = s.scrape()
            except Exception:  # a peer that cannot be read loses this window
                previous[i] = None
                continue
            if previous[i] is not None:
                windows[i].append(window(previous[i], current))
            previous[i] = current
    return windows


def _runs_candidate(server: Server, policy: Policy) -> bool:
    """Whether the server's controller has loaded this policy and is applying one of its tuned rules."""
    live = server.livetune_state().get("settings", {})
    if live.get("policy_version") != policy.version:
        return False
    startup = policy.rules[-1].settings
    candidates = [rule.settings for rule in policy.rules if rule.settings != startup]
    return any(all(live.get(key) == value for key, value in settings.items()) for settings in candidates)


def _wait_applied(server: Server, policy: Policy, timeout_s: float, interval_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if _runs_candidate(server, policy):
                return True
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_s)


def promote(args: argparse.Namespace, production: Server, policy: Policy) -> rollout.Verdict | None:
    """Publish to the fleet, then guard it: compare the fleet after against just before, and restore
    the previous policy if it regressed. A big shift in traffic makes the comparison inconclusive, and
    the change stays, since it has already passed replay and the stage."""
    scope = production.fingerprint()
    members = [production] + [Server(url) for url in (args.fleet or "").split(",") if url]
    # Replicas outside production's scope refuse the policy, so their unchanged windows would dilute the comparison.
    fleet = [m for m in members if not _scope_differences(scope, m.fingerprint())]
    previous = Path(args.policy_out).read_text() if Path(args.policy_out).exists() else None
    slo = Slo(args.slo_tps, args.slo_ttft)
    before = _watch(fleet, args.guard_seconds, args.interval) if args.guard_seconds and previous is not None else None
    _publish(args.policy_out, policy.to_json())
    if before is None:
        return None
    # Judge only the replicas that took the candidate up, from the moment they did.
    from concurrent.futures import ThreadPoolExecutor

    # All replicas get the same apply window, measured from publishing, not one after another.
    with ThreadPoolExecutor(max_workers=max(len(fleet), 1)) as pool:
        ready = list(pool.map(lambda m: _wait_applied(m, policy, args.stage_apply_s, args.interval), fleet))
    applied = [i for i, ok in enumerate(ready) if ok]
    if not applied:
        return rollout.Verdict("inconclusive", "no fleet replica applied the published policy", rollout.Side.of([], slo), rollout.Side.of([], slo))
    after = _watch([fleet[i] for i in applied], args.guard_seconds, args.interval)
    left = [fleet[i].url for i in applied if not _runs_candidate(fleet[i], policy)]
    if left:
        # A replica that dropped the candidate mid-guard (local probation rollback, say) was measured
        # partly on other settings; a guard prefers the known-good policy over an unproven one.
        verdict = rollout.Verdict("revert", f"replicas left the candidate during the guard: {left}", rollout.Side.of([], slo), rollout.Side.of([], slo))
    else:
        verdict = rollout.judge([w for side in after for w in side], [w for i in applied for w in before[i]], slo)
    if verdict.decision == "revert":
        _publish(args.policy_out, previous)
    return verdict


def stage(args: argparse.Namespace, production: Server, policy: Policy) -> rollout.Verdict:
    """Run a candidate on one production replica beside its peers; restore the replica's policy unless it is promoted."""
    replica = Server(args.stage_url)
    peers = [Server(url) for url in args.peers.split(",") if url]
    slo = Slo(args.slo_tps, args.slo_ttft)
    scope = production.fingerprint()
    # Evidence counts only from replicas running the intervention production runs.
    outside = [s.url for s in (replica, *peers) if _scope_differences(scope, s.fingerprint())]
    if outside or not peers:
        reason = f"replicas outside production's scope: {outside}" if outside else "no peers to compare against"
        return rollout.Verdict("inconclusive", reason, rollout.Side.of([], slo), rollout.Side.of([], slo))
    previous = Path(args.stage_policy).read_text()
    _publish(args.stage_policy, policy.to_json())
    verdict = None
    try:
        # The scope ignores live settings, so an unchanged replica would match its peers: measure
        # only once the replica reports a candidate rule live, and only if it still does at the end.
        if not _wait_applied(replica, policy, args.stage_apply_s, args.interval):
            verdict = rollout.Verdict("inconclusive", "the staged replica did not apply the candidate", rollout.Side.of([], slo), rollout.Side.of([], slo))
            return verdict
        watched = _watch([replica, *peers], args.stage_seconds, args.interval)
        verdict = rollout.judge(watched[0], [w for side in watched[1:] for w in side], slo)
        if verdict.decision == "promote" and not _runs_candidate(replica, policy):
            verdict = rollout.Verdict("inconclusive", "the staged replica left the candidate during the stage", verdict.stage, verdict.peers)
        return verdict
    finally:
        if verdict is None or verdict.decision != "promote":
            _publish(args.stage_policy, previous)


def _batch_counters(server: Server) -> dict[str, float]:
    """Batch counters summed over every data-parallel scheduler, so they cover what the metrics and trace cover."""
    total: dict[str, float] = {}
    for state in server.livetune_states():
        for key, value in ((state.get("telemetry") or {}).get("batches") or {}).items():
            total[key] = total.get(key, 0.0) + value
    return total


def advise(args: argparse.Namespace, server: Server) -> dict[str, Any]:
    """Watch the server for a while, then propose experiments from what it saw."""
    before = _batch_counters(server)
    started_wall = time.time()
    windows, previous = [], server.scrape()
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        time.sleep(args.interval)
        current = server.scrape()
        windows.append(window(previous, current))
        previous = current
    after_state = server.livetune_state()
    after = _batch_counters(server)
    records = list(trace.read([args.trace_dir], since=started_wall)) if args.trace_dir else []
    batches = trace.batch_deltas(before, after)
    evidence = advisor.Evidence(
        windows=windows,
        traffic=trace.summarize(records),
        batches=batches,
        settings=after_state.get("settings", {}),
        startup=after_state.get("startup", {}),
        kv_capacity=int(server.info().get("max_total_num_tokens") or 0),
        page_size=int(after_state.get("page_size") or 1),
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
    for name in ("status", "set", "load", "tune", "control", "replay", "policy", "traffic", "advise", "improve", "variant-eval"):
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
    ve = sub.choices["variant-eval"]
    ve.add_argument("--variant", required=True, help="a Python file defining install(model, patch, ctx)")
    ve.add_argument("--name", required=True)
    ve.add_argument("--variants-dir", default=os.environ.get("LIVETUNE_VARIANTS_DIR"), required=not os.environ.get("LIVETUNE_VARIANTS_DIR"))
    ve.add_argument("--corpus", required=True)
    ve.add_argument("--prompts", type=int, default=8)
    ve.add_argument("--prompt-tokens", type=int, default=1024)
    ve.add_argument("--tokens", type=int, default=64)
    ve.add_argument("--seed", type=int, default=7)
    ve.add_argument("--trace", help="recorded traffic to measure the variant against stock, interleaved")
    ve.add_argument("--speed", type=float, default=1.0)
    ve.add_argument("--slo-tps", type=float)
    ve.add_argument("--slo-ttft", type=float)
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
    im.add_argument("--stage-url", help="a production replica that runs each winner first, beside its peers")
    im.add_argument("--stage-policy", help="the policy file the staged replica's controller reads")
    im.add_argument("--peers", default="", help="comma-separated production replicas to compare against")
    im.add_argument("--stage-seconds", type=float, default=1800)
    im.add_argument("--stage-apply-s", type=float, default=180, help="how long the staged controller may take to apply the candidate")
    im.add_argument("--fleet", default="", help="comma-separated production replicas the guard watches with --url")
    im.add_argument("--guard-seconds", type=float, default=1800, help="fleet time before and after publishing to compare; 0 disables")
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
    if args.command == "variant-eval":
        if args.trace and (args.slo_tps is None or args.slo_ttft is None):
            raise SystemExit("--trace needs --slo-tps and --slo-ttft, so a slower variant cannot be kept on correctness alone")
        print(json.dumps(variant_eval(args, server), indent=1))
        return 0
    if args.command == "improve":
        if args.stage_url and not (args.stage_policy and args.peers):
            raise SystemExit("--stage-url needs --stage-policy and --peers")
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
        try:
            arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed) if args.trace else None
        except ValueError as exc:
            raise SystemExit(f"{args.trace}: {exc}") from exc
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
        if acting:
            server.apply({"policy_version": policy.version})  # announce which policy this replica runs
        log = _appender(args.log)
        seen = Path(args.policy).stat().st_mtime

        def scrape() -> Any:
            # A republished policy takes effect at the next window; one that fails its scope check is ignored.
            nonlocal seen
            mtime = Path(args.policy).stat().st_mtime
            if mtime != seen:
                seen = mtime
                try:
                    reloaded = load_policy(args.policy, server, args.allow_scope_mismatch)
                    controller.replace_policy(reloaded)
                    if acting:
                        server.apply({"policy_version": reloaded.version})
                    log({"t": time.time(), "policy_reloaded": args.policy, "version": reloaded.version})
                except (SystemExit, ValueError, OSError) as exc:
                    log({"t": time.time(), "policy_rejected": str(exc)})
            return server.scrape()

        control.run(controller, scrape, apply, window, interval_s=args.interval, log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
