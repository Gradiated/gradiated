#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import time
from typing import Any


ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-tree-verify")
PROJECT = ROOT / "project"
ARTIFACTS = ROOT / "artifacts"
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
DEADLINE = dt.datetime(2026, 7, 24, 14, 8, tzinfo=dt.timezone.utc)


def atomic(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def container_prefix() -> list[str]:
    return [
        "sudo",
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--ipc=host",
        "-v",
        f"{ROOT}:/work",
        "-e",
        "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python",
        IMAGE,
    ]


def component() -> dict[str, Any]:
    root = ARTIFACTS / "component"
    command = [
        *container_prefix(),
        "python3",
        "/work/project/component_benchmark.py",
        "--artifact-root",
        "/work/artifacts/component",
        "--candidate",
        "/work/project/inputs/bound/candidate_extend_attention.py",
    ]
    result = run(command, 1800)
    (ARTIFACTS / "component.stdout").write_text(result.stdout)
    (ARTIFACTS / "component.stderr").write_text(result.stderr)
    terminal = root / "COMPONENT_TERMINAL.json"
    if result.returncode not in (0, 2) or not terminal.exists():
        raise RuntimeError(f"component_harness_invalid:{result.returncode}")
    value = json.loads(terminal.read_text())
    atomic(ARTIFACTS / "COMPONENT_PERSISTED.json", value)
    return value


def counters() -> dict[str, Any]:
    counter_root = ARTIFACTS / "counters"
    counter_root.mkdir(parents=True, exist_ok=True)
    probe = run(
        [
            "sudo",
            "docker",
            "run",
            "--rm",
            IMAGE,
            "sh",
            "-lc",
            "command -v ncu || find /opt/nvidia -type f -name ncu 2>/dev/null | head -n1",
        ],
        120,
    )
    ncu = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
    if probe.returncode or not ncu:
        raise RuntimeError("counter_consumer_ncu_missing")
    metrics = ",".join(
        [
            "gpu__time_duration.sum",
            "launch__registers_per_thread",
            "launch__registers_per_thread_allocated",
            "launch__shared_mem_per_block",
            "launch__shared_mem_per_block_dynamic",
            "launch__occupancy_limit_registers",
            "launch__occupancy_limit_shared_mem",
            "launch__waves_per_multiprocessor",
            "dram__bytes_read.sum",
            "dram__bytes_write.sum",
            "lts__t_bytes.sum",
            "profiler__replayer_passes",
        ]
    )
    command = [
        "sudo",
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--ipc=host",
        "--cap-add",
        "SYS_ADMIN",
        "-v",
        f"{ROOT}:/work",
        "-e",
        "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python",
        IMAGE,
        ncu,
        "--target-processes",
        "all",
        "--profile-from-start",
        "off",
        "--kernel-name-base",
        "function",
        "--kernel-name",
        "regex:^_fwd_kernel$",
        "--launch-count",
        "4",
        "--metrics",
        metrics,
        "--export",
        "/work/artifacts/counters/tree-attention",
        "python3",
        "/work/project/component_benchmark.py",
        "--artifact-root",
        "/work/artifacts/counters/invocation",
        "--candidate",
        "/work/project/inputs/bound/candidate_extend_attention.py",
        "--counter-only",
    ]
    result = run(command, 1800)
    (counter_root / "ncu.stdout").write_text(result.stdout)
    (counter_root / "ncu.stderr").write_text(result.stderr)
    report = counter_root / "tree-attention.ncu-rep"
    if result.returncode or not report.exists():
        raise RuntimeError(f"counter_consumer_capture_invalid:{result.returncode}")
    export = run(
        [
            "sudo",
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ROOT}:/work",
            IMAGE,
            ncu,
            "--import",
            "/work/artifacts/counters/tree-attention.ncu-rep",
            "--csv",
            "--page",
            "raw",
        ],
        600,
    )
    (counter_root / "ncu.csv").write_text(export.stdout)
    (counter_root / "ncu-export.stderr").write_text(export.stderr)
    if export.returncode or "_fwd_kernel" not in export.stdout:
        raise RuntimeError(f"counter_consumer_export_invalid:{export.returncode}")
    terminal = {
        "schema_version": 1,
        "complete": True,
        "launch_order": [
            "control_local",
            "control_full",
            "candidate_local",
            "candidate_full",
        ],
        "report_sha256": sha256(report),
        "csv_sha256": sha256(counter_root / "ncu.csv"),
        "metrics": metrics.split(","),
    }
    atomic(counter_root / "COUNTER_TERMINAL.json", terminal)
    return terminal


def endpoint() -> dict[str, Any]:
    result = run(["/usr/bin/python3", str(PROJECT / "endpoint_pair.py")], 6000)
    (ARTIFACTS / "endpoint-pair.stdout").write_text(result.stdout)
    (ARTIFACTS / "endpoint-pair.stderr").write_text(result.stderr)
    terminal = ARTIFACTS / "pair/PAIR_TERMINAL.json"
    if result.returncode not in (0, 75) or not terminal.exists():
        raise RuntimeError(f"endpoint_pair_harness_invalid:{result.returncode}")
    value = json.loads(terminal.read_text())
    atomic(ARTIFACTS / "PAIR_PERSISTED.json", value)
    return value


def repair_wait(error: Exception, stage: str) -> None:
    invocation = ARTIFACTS / "component/INVOCATION_STATE.json"
    state = json.loads(invocation.read_text()) if invocation.exists() else {}
    atomic(
        ROOT / "REPAIR_READY.json",
        {
            "schema_version": 1,
            "classification": "recoverable_integration_or_consumer_defect",
            "stage": stage,
            "error": f"{type(error).__name__}: {error}",
            "candidate_cuda_invocation_started": state.get(
                "candidate_cuda_invocation_started", False
            ),
            "scientific_invocation_started": state.get(
                "scientific_invocation_started", False
            ),
            "claim_must_be_retained": True,
            "repair_deadline_utc": DEADLINE.isoformat(),
        },
    )
    while dt.datetime.now(dt.timezone.utc) < DEADLINE:
        time.sleep(20)
    raise RuntimeError("repair_deadline_expired")


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    atomic(
        ROOT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
        },
    )
    try:
        component_value = component()
    except Exception as error:
        repair_wait(error, "component")
        return 74
    if not component_value.get("component_pass"):
        terminal = {
            "schema_version": 1,
            "classification": "scientific_terminal",
            "result": "component_nonpositive_or_incorrect",
            "component": component_value,
            "endpoint_executed": False,
        }
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        return 2
    try:
        counter_value = counters()
    except Exception as error:
        repair_wait(error, "counter_consumer")
        return 74
    try:
        pair_value = endpoint()
    except Exception as error:
        repair_wait(error, "endpoint_consumer")
        return 74
    result = (
        "positive"
        if pair_value.get("valid")
        and pair_value.get("service_time_delta_fraction", 0) < 0
        and pair_value.get("p95_delta_fraction", 1) < 0.05
        else "nonpositive_or_invalid"
    )
    terminal = {
        "schema_version": 1,
        "classification": "scientific_terminal",
        "result": result,
        "component": component_value,
        "counters": counter_value,
        "pair": pair_value,
        "endpoint_executed": True,
    }
    atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
    return 0 if result == "positive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
