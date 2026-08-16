#!/usr/bin/env python3
"""No-mutation proof for the direct systemd retained-arm sequence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve()


def append(path: Path, event: str, **fields: object) -> None:
    row = {"event": event, "pid": os.getpid(), "time_ns": time.time_ns(), **fields}
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def control(args: argparse.Namespace) -> int:
    append(args.events, "control_started", systemd_exec_pid=os.environ.get("SYSTEMD_EXEC_PID"))
    if os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        return 71
    if args.fail_control:
        append(args.events, "control_failed")
        return 72
    args.summary.write_text(json.dumps({
        "retained_for_next_experiment": True,
        "instance_id": "computeinstance-proof",
        "final_instance_count": 1,
        "final_disk_count": 1,
    }, sort_keys=True))
    append(args.events, "control_retained", instance_id="computeinstance-proof")
    if args.retained_exit_one:
        append(args.events, "control_retained_exit_one")
        return 1
    return 0


def recovery(args: argparse.Namespace) -> int:
    summary = json.loads(args.control_summary.read_text())
    if not summary.get("retained_for_next_experiment") or summary.get("instance_id") != "computeinstance-proof":
        return 73
    append(args.events, "recovery_started", instance_id=summary["instance_id"], max_num_batched_tokens=args.max_num_batched_tokens, max_num_seqs=args.max_num_seqs, frontier_concurrencies=args.frontier_concurrencies, kv_cache_dtype=args.kv_cache_dtype)
    args.cleanup.write_text(json.dumps({"deleted_instance": summary["instance_id"], "deleted_disk": "proof-boot", "final_instance_count": 0, "final_disk_count": 0, "scientific_failure": True}, sort_keys=True))
    append(args.events, "recovery_cleanup_verified")
    return 0


def systemd_command(mode: str, summary: Path, events: Path, cleanup: Path, unit: str) -> list[str]:
    control_args = ["/usr/bin/python3", str(ROOT), "control", "--summary", str(summary), "--events", str(events)]
    if mode == "failure":
        control_args.append("--fail-control")
    if mode == "retained_exit_one":
        control_args.append("--retained-exit-one")
    post = ["/usr/bin/python3", str(ROOT), "recovery", "--control-summary", str(summary), "--events", str(events), "--cleanup", str(cleanup), "--parent-experiment-id", "99dd188923b37c4f5a6711c1690db2b1c620f4add3f910c69e1794bbfb8ad123", "--max-num-batched-tokens", "65536", "--max-num-seqs", "32", "--frontier-concurrencies", "32", "--num-kv-splits", "4", "--kv-cache-dtype", "fp8_e4m3fn"]
    command = ["systemd-run", "--user", "--wait", "--pipe", "--collect", "--unit=" + unit, "--property=Type=oneshot", "--property=RuntimeMaxSec=20s"]
    if mode == "retained_exit_one":
        command.append("--property=SuccessExitStatus=1")
    return [*command, "--property=ExecStartPost=" + " ".join(post), *control_args]


def prove(output: Path) -> int:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for mode in ("success", "failure", "retained_exit_one"):
        events, summary, cleanup = (output / f"{mode}-{name}.jsonl" for name in ("events", "summary", "cleanup"))
        for path in (events, summary, cleanup):
            path.unlink(missing_ok=True)
        unit = "glm47-near-stock-proof-" + mode + "-" + uuid.uuid4().hex[:10]
        command = systemd_command(mode, summary, events, cleanup, unit)
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        rows = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
        results[mode] = {"command": command, "returncode": result.returncode, "events": rows, "summary_exists": summary.exists(), "cleanup": json.loads(cleanup.read_text()) if cleanup.exists() else None, "stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]}
    success = results["success"]
    failure = results["failure"]
    retained_exit_one = results["retained_exit_one"]
    success_events = [row["event"] for row in success["events"]]
    failure_events = [row["event"] for row in failure["events"]]
    retained_exit_one_events = [row["event"] for row in retained_exit_one["events"]]
    direct_tokens = {"bash", "-lc", "-c", "$("}
    post = next(part for part in success["command"] if part.startswith("--property=ExecStartPost="))
    passed = (
        success["returncode"] == 0
        and success_events == ["control_started", "control_retained", "recovery_started", "recovery_cleanup_verified"]
        and success["events"][0]["systemd_exec_pid"] == str(success["events"][0]["pid"])
        and success["events"][1]["time_ns"] < success["events"][2]["time_ns"]
        and success["events"][2]["max_num_batched_tokens"] == "65536"
        and success["events"][2]["max_num_seqs"] == "32"
        and success["events"][2]["frontier_concurrencies"] == "32"
        and success["events"][2]["kv_cache_dtype"] == "fp8_e4m3fn"
        and success["cleanup"] == {"deleted_disk": "proof-boot", "deleted_instance": "computeinstance-proof", "final_disk_count": 0, "final_instance_count": 0, "scientific_failure": True}
        and failure["returncode"] != 0
        and failure_events == ["control_started", "control_failed"]
        and not failure["summary_exists"]
        and failure["cleanup"] is None
        and retained_exit_one["returncode"] == 0
        and retained_exit_one_events == ["control_started", "control_retained", "control_retained_exit_one", "recovery_started", "recovery_cleanup_verified"]
        and retained_exit_one["events"][0]["systemd_exec_pid"] == str(retained_exit_one["events"][0]["pid"])
        and retained_exit_one["events"][2]["time_ns"] < retained_exit_one["events"][3]["time_ns"]
        and retained_exit_one["cleanup"] == {"deleted_disk": "proof-boot", "deleted_instance": "computeinstance-proof", "final_disk_count": 0, "final_instance_count": 0, "scientific_failure": True}
        and not any(token in post.split() for token in direct_tokens)
    )
    (output / "RETAINED_SEQUENCE_PROOF_R2.json").write_text(json.dumps({"pass": passed, "results": results}, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("control")
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--fail-control", action="store_true")
    p.add_argument("--retained-exit-one", action="store_true")
    p = sub.add_parser("recovery")
    p.add_argument("--control-summary", type=Path, required=True)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--cleanup", type=Path, required=True)
    p.add_argument("--parent-experiment-id", required=True)
    p.add_argument("--max-num-batched-tokens", required=True)
    p.add_argument("--max-num-seqs", required=True)
    p.add_argument("--frontier-concurrencies", required=True)
    p.add_argument("--num-kv-splits", required=True)
    p.add_argument("--kv-cache-dtype", required=True)
    p = sub.add_parser("prove")
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "control": return control(args)
    if args.mode == "recovery": return recovery(args)
    return prove(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
