#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import run_ring_owner as base


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
PROJECT = base.PROJECT
BENCH = base.BENCH
REMOTE = base.REMOTE
RATE = base.RATE
PRIOR_SPEND = 1.4780371621171633
CAP = 14.0
FINAL_PATH = HERE / "artifacts/RING_PRODUCER_BINDING_FINAL_TERMINAL.json"
HIGHER_PRIORITY_STATUS = (
    HERE.parent / "gemma4_h200_mlp_width16384_codesign" / "STATUS.json"
)


def higher_priority_complete():
    try:
        value = json.loads(HIGHER_PRIORITY_STATUS.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return value.get("status") in {
        "completed",
        "terminal",
        "closed",
        "failed",
        "blocked",
    }


def validate_manifest():
    value = json.loads((HERE / "ENDPOINT_GPU_MANIFEST.json").read_text())
    for row in value["files"]:
        path = HERE / row["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.stat().st_size != row["bytes"] or actual != row["sha256"]:
            raise RuntimeError(f"immutable endpoint input mismatch:{row['path']}")
    return value


def retrieve(ip):
    root = HERE / "artifacts" / "remote-endpoint"
    root.mkdir(parents=True, exist_ok=True)
    names = (
        "endpoint-artifacts/WORKER_TERMINAL.json",
        "endpoint-artifacts/INVOCATION_STATE.json",
        "endpoint-artifacts/ENDPOINT_RESULT.json",
        "endpoint-compact.tar.gz",
        "endpoint-compact.tar.gz.sha256",
    )
    report = {}
    for name in names:
        destination = root / name.replace("/", "__")
        destination.unlink(missing_ok=True)
        ok, error = base.scp_from(ip, f"{REMOTE}/{name}", destination, 900)
        report[name] = {"success": ok, "diagnostic": error}
        base.emit("endpoint_retrieval", path=name, success=ok)
    base.atomic_json(root / "RETRIEVAL.json", report)
    return report


def checkpoint_validate(ip):
    rows = []
    for line in (HERE / "inputs" / "CHECKPOINT_SHA256SUMS.txt").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        rows.append((digest, Path(path).name))
    resident = "/home/glmrunner/gemma4-async-result-pipeline/checkpoint"
    checks = " ".join(f"{d}:{shlex.quote(n)}" for d, n in rows)
    command = (
        f"set -e; resident={shlex.quote(resident)}; test -d \"$resident\"; "
        f"for item in {checks}; do hash=${{item%%:*}}; name=${{item#*:}}; "
        "test -f \"$resident/$name\"; printf '%s  %s\\n' \"$hash\" \"$resident/$name\" | sha256sum -c -; done"
    )
    result = base.remote(ip, command, 1800)
    (HERE / "artifacts" / "endpoint-checkpoint.stdout").write_text(result.stdout)
    (HERE / "artifacts" / "endpoint-checkpoint.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("resident checkpoint manifest mismatch")


def read_remote_result():
    path = HERE / "artifacts/remote-endpoint/endpoint-artifacts__ENDPOINT_RESULT.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline-epoch", required=True, type=float)
    args = parser.parse_args()
    manifest = validate_manifest()
    pool = base.GpuPool(LAB)
    claim_deadline = args.deadline_epoch - 1800
    wait_recorded = False
    while not higher_priority_complete():
        if time.time() >= claim_deadline:
            final = {
                "schema_version": 1,
                "status": "terminal",
                "classification": "higher_priority_dependency_before_runway",
                "dependency": str(HIGHER_PRIORITY_STATUS),
                "candidate_cuda_started": False,
                "candidate_science_started": False,
                "current_claim_cost_usd": 0.0,
                "provider_cost_usd": PRIOR_SPEND,
                "timestamp_utc": base.utc_now(),
            }
            base.atomic_json(FINAL_PATH, final)
            return 4
        if not wait_recorded:
            base.emit(
                "priority_wait",
                dependency=str(HIGHER_PRIORITY_STATUS),
                claim_deadline_utc=dt.datetime.fromtimestamp(
                    claim_deadline, dt.timezone.utc
                )
                .isoformat()
                .replace("+00:00", "Z"),
            )
            wait_recorded = True
        time.sleep(15)
    wait_recorded = False
    while True:
        try:
            bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=9000)
            break
        except base.GpuPoolError as error:
            if time.time() >= claim_deadline:
                final = {
                    "schema_version": 1,
                    "status": "terminal",
                    "classification": "bench_unavailable_before_runway",
                    "reason": str(error),
                    "candidate_cuda_started": False,
                    "candidate_science_started": False,
                    "current_claim_cost_usd": 0.0,
                    "provider_cost_usd": PRIOR_SPEND,
                    "timestamp_utc": base.utc_now(),
                }
                base.atomic_json(FINAL_PATH, final)
                return 4
            if not wait_recorded:
                base.emit(
                    "bench_wait",
                    bench=BENCH,
                    claim_deadline_utc=dt.datetime.fromtimestamp(
                        claim_deadline, dt.timezone.utc
                    )
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
                wait_recorded = True
            time.sleep(15)
    claimed = time.time()
    lifecycle = dt.datetime.fromisoformat(
        bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    deadline = min(
        args.deadline_epoch,
        lifecycle - 300,
        claimed + (CAP - PRIOR_SPEND) / RATE * 3600,
    )
    heartbeat = base.Heartbeat(pool)
    heartbeat.start()
    final = {}
    condition = "ready"
    returncode = 0
    try:
        instance = base.get_instance(bench["resource"]["instance_id"])
        ip = base.extract_public_ipv4(instance)
        if not ip:
            raise RuntimeError("claimed guest has no public IPv4")
        probe = base.remote(ip, "nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader", 60)
        if probe.returncode:
            condition = "maintenance"
            raise RuntimeError(f"claimed guest unreachable:{probe.stderr[-500:]}")
        checkpoint_validate(ip)
        base.reconcile(ip, [
            {
                **row,
                "remote_name": row["remote_name"],
            }
            for row in manifest["files"]
        ])
        pool.update(
            PROJECT,
            {
                "project": PROJECT,
                "runtime": "Fresh-extend byte proof and conditional exact c32 ring candidate active",
                "checkpoint": "Exact resident checkpoint verified read-only by project-local manifest",
                "server_state": "Paired endpoint worker active",
            },
        )
        command = (
            f"RING_REMOTE_ROOT={shlex.quote(REMOTE)} "
            f"bash {shlex.quote(REMOTE + '/input/remote_endpoint_pair.sh')}"
        )
        while True:
            worker = base.remote(ip, command, max(60, int(deadline - time.time() - 180)))
            report = retrieve(ip)
            terminal_ok = report["endpoint-artifacts/WORKER_TERMINAL.json"]["success"]
            state_ok = report["endpoint-artifacts/INVOCATION_STATE.json"]["success"]
            result_ok = report["endpoint-artifacts/ENDPOINT_RESULT.json"]["success"]
            result = read_remote_result()
            if terminal_ok and state_ok and result_ok and result:
                final = {
                    "classification": result.get("classification", "endpoint_terminal"),
                    "endpoint_result": result,
                }
                break
            if time.time() >= deadline - 240:
                raise TimeoutError("endpoint repair deadline exhausted")
            state_path = HERE / "artifacts/remote-endpoint/endpoint-artifacts__INVOCATION_STATE.json"
            state = json.loads(state_path.read_text()) if state_path.is_file() else {}
            base.atomic_json(
                HERE / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "status": "repair_ready",
                    "worker_returncode": worker.returncode,
                    "invocation_state": state,
                    "absolute_deadline_utc": dt.datetime.fromtimestamp(
                        deadline - 180, dt.timezone.utc
                    ).isoformat().replace("+00:00", "Z"),
                },
            )
            while time.time() < deadline - 240:
                request = HERE / "REPAIR_REQUEST.json"
                if request.is_file():
                    request.unlink()
                    (HERE / "REPAIR_READY.json").unlink(missing_ok=True)
                    manifest = validate_manifest()
                    base.reconcile(ip, manifest["files"])
                    break
                time.sleep(5)
            else:
                raise TimeoutError("endpoint repair request deadline exhausted")
        elapsed = time.time() - claimed
        final.update(
            {
                "schema_version": 1,
                "status": "terminal",
                "claimed_seconds": elapsed,
                "current_claim_cost_usd": elapsed / 3600 * RATE,
                "provider_cost_usd": PRIOR_SPEND + elapsed / 3600 * RATE,
                "timestamp_utc": base.utc_now(),
            }
        )
        base.atomic_json(FINAL_PATH, final)
    except Exception as error:
        elapsed = time.time() - claimed
        final = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "typed_external_blocker" if condition == "maintenance" else "endpoint_owner_failure",
            "reason": str(error),
            "claimed_seconds": elapsed,
            "current_claim_cost_usd": elapsed / 3600 * RATE,
            "provider_cost_usd": PRIOR_SPEND + elapsed / 3600 * RATE,
            "timestamp_utc": base.utc_now(),
        }
        base.atomic_json(FINAL_PATH, final)
        returncode = 3
    finally:
        heartbeat.close()
        elapsed = time.time() - claimed
        pool.release(
            PROJECT,
            contents={
                "project": PROJECT,
                "ring_cache_result": final.get("classification", "incomplete"),
                "ring_cache_claim_cost_usd": round(elapsed / 3600 * RATE, 6),
                "ring_cache_cumulative_cost_usd": PRIOR_SPEND + elapsed / 3600 * RATE,
                "runtime": "Fresh-extend source-binding terminal; endpoint caches retained",
                "checkpoint": "Exact resident checkpoint unchanged",
                "server_state": "Final paired endpoint server retained if healthy",
                "artifacts": str(HERE / "artifacts"),
            },
            condition=condition,
        )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
