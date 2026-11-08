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
from livetune.server import Server


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


def _appender(path: str | None):
    handle = open(path, "a") if path else None

    def write(event: Any) -> None:
        line = event if isinstance(event, str) else json.dumps(event)
        print(line, flush=True)
        if handle:
            handle.write(line + "\n")
            handle.flush()

    return write


def replay(args: argparse.Namespace, server: Server) -> None:
    import threading

    policy = Policy.load(args.policy)
    write = _appender(args.out)
    server.apply(server.livetune_state()["startup"])
    stop = threading.Event()
    events: list[dict[str, Any]] = []
    if not args.static:
        controller = control.Controller(policy)

        def log(event: dict[str, Any]) -> None:
            event["wall"] = time.time()
            events.append(event)
            if "action" in event:
                write({"controller": event})

        thread = threading.Thread(
            target=control.run,
            args=(controller, server.scrape, server.apply, window),
            kwargs={"interval_s": args.interval, "log": log, "stop": stop.is_set, "sleep": stop.wait},
            daemon=True,
        )
        thread.start()
    phases = [loadgen.Phase(**p) for p in json.loads(Path(args.phases).read_text())]
    prompts = loadgen.PromptSource(_corpus(args.corpus))
    for index, phase in enumerate(phases):
        started = time.time()
        summary = asyncio_phase(args.url, phase, prompts, index)
        write(phase_report(summary, events, started, phase.seconds, policy, "static" if args.static else "controlled"))
    stop.set()
    server.apply(server.livetune_state()["startup"])


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
        sub.choices[name].add_argument("--out")
    for name in ("load", "replay"):
        sub.choices[name].add_argument("--phases", required=True)
    r = sub.choices["replay"]
    r.add_argument("--policy", required=True)
    r.add_argument("--static", action="store_true", help="hold the startup settings instead of running the controller")
    r.add_argument("--interval", type=float, default=5.0)
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
        record = _appender(args.out + ".trials.jsonl" if args.out else None)

        def measure(profile: tune.Profile, settings: dict[str, Any]) -> dict[str, Any]:
            server.apply(settings)
            if args.warmup:
                loadgen.run(args.url, [profile.phase(args.warmup)], prompts, log=lambda _: None)
            summary = loadgen.run(args.url, [profile.phase(args.seconds)], prompts, log=lambda _: None)[0]
            record({"profile": profile.name, "settings": settings, "summary": summary})
            return summary

        results = [
            tune.tune_profile(tune.Profile(**p), start, json.loads(Path(args.grid).read_text()), slo, measure)
            for p in json.loads(Path(args.profiles).read_text())
        ]
        server.apply(start)
        policy = tune.build_policy(results, slo, {"tuned_at": time.time(), "url": args.url, "startup": start})
        Path(args.out).write_text(policy.to_json())
        print(policy.to_json())
    elif args.command == "policy":
        slo = Slo(args.slo_tps, args.slo_ttft)
        trials = [json.loads(line) for line in Path(args.trials).read_text().splitlines() if line.strip()]
        start = server.livetune_state()["startup"]
        policy = tune.build_policy(tune.best_from_trials(trials, slo, start), slo, {"trials": args.trials, "startup": start})
        Path(args.out).write_text(policy.to_json())
        print(policy.to_json())
    elif args.command == "replay":
        replay(args, server)
    elif args.command == "control":
        policy = Policy.load(args.policy)
        controller = control.Controller(policy)
        apply = server.apply if args.mode == "act" else (lambda settings: None)
        control.run(controller, server.scrape, apply, window, interval_s=args.interval, log=_appender(args.log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
