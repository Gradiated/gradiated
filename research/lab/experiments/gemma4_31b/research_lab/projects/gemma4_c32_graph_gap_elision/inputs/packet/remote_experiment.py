#!/usr/bin/env python3
"""Bound component, counter consumer, and conditional c32 endpoint."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import traceback


ROOT = pathlib.Path("/home/glmrunner/gemma4-persistent-grouped-lm-head")
PROJECT = ROOT / "project"
CHECKPOINT = ROOT / "checkpoint"
ARTIFACTS = pathlib.Path(os.environ["GROUPED_LM_HEAD_ARTIFACT_ROOT"])
DEADLINE = dt.datetime.fromisoformat(
    os.environ["GROUPED_LM_HEAD_DEADLINE_UTC"].replace("Z", "+00:00")
)
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
WEIGHT = CHECKPOINT / "model-00001-of-00002.safetensors"


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    remaining = int(
        (DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds()
    )
    if remaining <= 0:
        raise RuntimeError("absolute_experiment_deadline_reached")
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        timeout=max(1, min(timeout, remaining)),
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def remaining_seconds() -> int:
    return int((DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds())


def container_prefix(gpu: bool = True) -> list[str]:
    result = [
        "sudo",
        "docker",
        "run",
        "--rm",
    ]
    if gpu:
        result += ["--gpus", "all", "--ipc=host"]
    return result + [
        "-v",
        f"{PROJECT}:/work/project:ro",
        "-v",
        f"{CHECKPOINT}:/work/checkpoint:ro",
        "-v",
        f"{ARTIFACTS}:/work/artifacts",
        "-e",
        "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python",
        IMAGE,
    ]


def component() -> dict:
    result = run(
        [
            *container_prefix(),
            "python3",
            "/work/project/exact_consumer_component.py",
            "--weight",
            "/work/checkpoint/model-00001-of-00002.safetensors",
            "--artifact-root",
            "/work/artifacts/component",
        ],
        2400,
    )
    (ARTIFACTS / "component.stdout").write_text(result.stdout)
    (ARTIFACTS / "component.stderr").write_text(result.stderr)
    terminal = ARTIFACTS / "component/COMPONENT_TERMINAL.json"
    if result.returncode not in (0, 2) or not terminal.exists():
        raise RuntimeError(f"component_consumer_invalid:{result.returncode}")
    value = json.loads(terminal.read_text())
    atomic(ARTIFACTS / "COMPONENT_PERSISTED.json", value)
    return value


def counters() -> dict:
    root = ARTIFACTS / "counters"
    root.mkdir(parents=True, exist_ok=True)
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
    metrics = [
        "gpu__time_duration.sum",
        "launch__registers_per_thread",
        "launch__shared_mem_per_block",
        "launch__shared_mem_per_block_dynamic",
        "launch__waves_per_multiprocessor",
        "dram__bytes_read.sum",
        "dram__bytes_write.sum",
        "lts__t_bytes.sum",
    ]
    result = run(
        [
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
            f"{PROJECT}:/work/project:ro",
            "-v",
            f"{CHECKPOINT}:/work/checkpoint:ro",
            "-v",
            f"{ARTIFACTS}:/work/artifacts",
            "-e",
            "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python",
            IMAGE,
            ncu,
            "--target-processes",
            "all",
            "--kernel-name-base",
            "function",
            "--kernel-name",
            "regex:(nvjet_sm90_tst_512x32|depth_interleaved_grouped_lm_head)",
            "--metrics",
            ",".join(metrics),
            "--export",
            "/work/artifacts/counters/grouped-lm-head",
            "python3",
            "/work/project/counter_probe.py",
            "--weight",
            "/work/checkpoint/model-00001-of-00002.safetensors",
        ],
        2400,
    )
    (root / "ncu.stdout").write_text(result.stdout)
    (root / "ncu.stderr").write_text(result.stderr)
    report = root / "grouped-lm-head.ncu-rep"
    if result.returncode or not report.exists():
        raise RuntimeError(f"counter_capture_invalid:{result.returncode}")
    exported = run(
        [
            "sudo",
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ARTIFACTS}:/work/artifacts",
            IMAGE,
            ncu,
            "--import",
            "/work/artifacts/counters/grouped-lm-head.ncu-rep",
            "--csv",
            "--page",
            "raw",
        ],
        600,
    )
    (root / "ncu.csv").write_text(exported.stdout)
    (root / "ncu-export.stderr").write_text(exported.stderr)
    if exported.returncode or "depth_interleaved_grouped_lm_head" not in exported.stdout:
        raise RuntimeError(f"counter_export_invalid:{exported.returncode}")
    value = {
        "schema_version": 1,
        "complete": True,
        "metrics": metrics,
        "report_sha256": sha256(report),
        "csv_sha256": sha256(root / "ncu.csv"),
    }
    atomic(root / "COUNTER_TERMINAL.json", value)
    return value


def endpoint() -> dict:
    environment = {
        **os.environ,
        "GROUPED_LM_HEAD_REMOTE_ROOT": str(ROOT),
        "GROUPED_LM_HEAD_PAIR_ROOT": str(ARTIFACTS / "pair"),
    }
    remaining = int(
        (DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds()
    )
    if remaining <= 0:
        raise RuntimeError("endpoint_deadline_insufficient")
    result = subprocess.run(
        ["/usr/bin/python3", str(PROJECT / "endpoint_pair.py")],
        text=True,
        capture_output=True,
        check=False,
        timeout=min(6000, remaining),
        env=environment,
    )
    (ARTIFACTS / "endpoint.stdout").write_text(result.stdout)
    (ARTIFACTS / "endpoint.stderr").write_text(result.stderr)
    terminal = ARTIFACTS / "pair/PAIR_TERMINAL.json"
    if result.returncode not in (0, 2) or not terminal.exists():
        raise RuntimeError(f"endpoint_consumer_invalid:{result.returncode}")
    value = json.loads(terminal.read_text())
    atomic(ARTIFACTS / "PAIR_PERSISTED.json", value)
    return value


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    atomic(
        ARTIFACTS / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "pre_science": True,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
        },
    )
    try:
        persisted_component = ARTIFACTS / "COMPONENT_PERSISTED.json"
        component_value = (
            json.loads(persisted_component.read_text())
            if persisted_component.exists()
            else component()
        )
        if not component_value.get("component_pass"):
            terminal = {
                "schema_version": 1,
                "classification": "scientific_terminal",
                "result": "component_nonpositive_or_incorrect",
                "component": component_value,
                "endpoint_executed": False,
            }
            atomic(ARTIFACTS / "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json", terminal)
            return 2
        persisted_counters = ARTIFACTS / "counters/COUNTER_TERMINAL.json"
        counter_value = (
            json.loads(persisted_counters.read_text())
            if persisted_counters.exists()
            else counters()
        )
        if remaining_seconds() < 2400:
            terminal = {
                "schema_version": 1,
                "classification": "typed_lifecycle_boundary",
                "result": "component_positive_endpoint_not_started",
                "component": component_value,
                "counters": counter_value,
                "endpoint_executed": False,
                "remaining_seconds": remaining_seconds(),
                "required_endpoint_reserve_seconds": 2400,
            }
            atomic(
                ARTIFACTS / "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json",
                terminal,
            )
            return 2
        persisted_pair = ARTIFACTS / "PAIR_PERSISTED.json"
        pair_value = (
            json.loads(persisted_pair.read_text())
            if persisted_pair.exists()
            else endpoint()
        )
        result = (
            "positive"
            if pair_value.get("valid")
            and pair_value.get("service_time_delta_fraction", 0.0) < 0.0
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
        atomic(ARTIFACTS / "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json", terminal)
        return 0 if result == "positive" else 2
    except Exception as error:
        atomic(
            ARTIFACTS / "REMOTE_EXCEPTION.json",
            {
                "schema_version": 1,
                "classification": "recoverable_integration_or_consumer_defect",
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(),
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
