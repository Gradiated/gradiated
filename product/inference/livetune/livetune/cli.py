from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from livetune import controller as control
from livetune import loadgen, tune
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
    thread = None
    if not args.static:
        controller = control.Controller(policy, startup=startup)

        def log(event: dict[str, Any]) -> None:
            event["wall"] = time.time()
            events.append(event)
            write({"controller": event})

        def run_controller() -> None:
            try:
                control.run(controller, server.scrape, server.apply, window, interval_s=args.interval, log=log, stop=stop.is_set, sleep=stop.wait)
            except BaseException as exc:
                failures.append(exc)
                raise

        thread = threading.Thread(target=run_controller, daemon=True)
        thread.start()
    try:
        phases = [loadgen.Phase(**p) for p in json.loads(Path(args.phases).read_text())]
        prompts = loadgen.PromptSource(_corpus(args.corpus))
        for index, phase in enumerate(phases):
            started = time.time()
            summary = asyncio_phase(args.url, phase, prompts, index)
            if failures:
                raise RuntimeError("the controller stopped during the replay; its results are not controlled") from failures[0]
            write(phase_report(summary, events, started, phase.seconds, policy, "static" if args.static else "controlled"))
    finally:
        stop.set()
        if thread is not None:
            thread.join()
        server.apply(startup)


def phase_report(summary: dict[str, Any], events: list[dict[str, Any]], started: float, seconds: float, policy: Policy, mode: str) -> dict[str, Any]:
    during = [e for e in events if started <= e["wall"] <= started + seconds]
    switches = [e for e in during if "action" in e]
    return {
        **summary,
        "mode": mode,
        "slo_met": policy.slo.met(summary["tps_per_user_p50"], summary["ttft_p90"]),
        "rules": sorted({e["rule"] for e in during if e.get("rule")}),
        "first_switch_s": round(switches[0]["wall"] - started, 1) if switches else None,
    }


def asyncio_phase(url: str, phase: loadgen.Phase, prompts: loadgen.PromptSource, index: int) -> dict[str, Any]:
    import asyncio

    return asyncio.run(loadgen.run_phase(url, phase, prompts, index)).summary()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="livetune")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "set", "load", "tune", "control", "replay", "policy"):
        p = sub.add_parser(name)
        p.add_argument("--url", default="http://127.0.0.1:30000")
    sub.choices["set"].add_argument("pairs", nargs="+")
    for name in ("load", "tune", "replay"):
        sub.choices[name].add_argument("--corpus", required=True)
        sub.choices[name].add_argument("--out", required=name == "tune")
    for name in ("load", "replay"):
        sub.choices[name].add_argument("--phases", required=True)
    r = sub.choices["replay"]
    r.add_argument("--policy", required=True)
    r.add_argument("--static", action="store_true", help="hold the startup settings instead of running the controller")
    r.add_argument("--interval", type=float, default=5.0)
    for name in ("control", "replay"):
        sub.choices[name].add_argument("--allow-scope-mismatch", action="store_true", help="use a policy tuned on a different model, layout or GPU")
    t = sub.choices["tune"]
    t.add_argument("--profiles", required=True)
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
    c = sub.choices["control"]
    c.add_argument("--policy", required=True)
    c.add_argument("--interval", type=float, default=5.0)
    c.add_argument("--log")
    c.add_argument("--mode", choices=("act", "observe"), default="act", help="observe logs decisions without applying them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = Server(args.url)

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
        slo = Slo(args.slo_tps, args.slo_ttft)
        prompts = loadgen.PromptSource(_corpus(args.corpus))
        start = {k: v for k, v in server.livetune_state()["startup"].items()}
        scope = server.fingerprint()
        record = _appender(args.out + ".trials.jsonl", mode="w")

        def measure(profile: tune.Profile, settings: dict[str, Any]) -> dict[str, Any]:
            server.apply(settings)
            if args.warmup:
                loadgen.run(args.url, [profile.phase(args.warmup)], prompts, log=lambda _: None)
            summary = loadgen.run(args.url, [profile.phase(args.seconds)], prompts, log=lambda _: None)[0]
            record({"profile": profile.name, "settings": settings, "summary": summary, "scope": scope})
            return summary

        profiles = json.loads(Path(args.profiles).read_text())
        tune.check_distinguishable(profiles)
        try:
            results = [tune.tune_profile(tune.Profile(**p), start, json.loads(Path(args.grid).read_text()), slo, measure) for p in profiles]
        finally:
            server.apply(start)
        policy = tune.build_policy(results, slo, {"tuned_at": time.time(), "url": args.url, "scope": scope}, start)
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
        controller = control.Controller(policy, startup=server.livetune_state()["startup"], judge_changes=acting)
        apply = server.apply if acting else (lambda settings: None)
        control.run(controller, server.scrape, apply, window, interval_s=args.interval, log=_appender(args.log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
