#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback


ROOT = Path("/home/glmrunner/gemma4-h200-ngram-high-load-bypass")
OUT = ROOT / "out"
BOUND = ROOT / "bound_inputs"
CONTROL = BOUND / "inputs/control"
FULL_COMPARATOR = BOUND / "comparator.requests.jsonl"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
CHECKPOINT = (
    "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
)
CONTAINER = "gemma4-ngram-high-load-bypass-candidate"
PREFIX_REQUESTS = 871
FULL_REQUESTS = 1036
PLANNING_USD_PER_HOUR = 3.25


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str], timeout: int | None = None):
    return subprocess.run(
        args, text=True, capture_output=True, check=False, timeout=timeout
    )


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def load_base():
    spec = importlib.util.spec_from_file_location(
        "bound_production_runner", BOUND / "base/remote_candidate.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("bound_runner_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def launch(arm_out: Path) -> list[str]:
    frozen = json.loads((CONTROL / "launch-5000.json").read_text())["cmd"]
    module_index = frozen.index("sglang.launch_server")
    server_args = frozen[module_index + 1 :]
    command = [
        "sudo",
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--gpus",
        "all",
        "--ipc=host",
        "--network",
        "host",
        "-e",
        "PYTHONPATH=/work/candidate:/work/bound_inputs",
        "-e",
        f"HIGH_LOAD_BYPASS_OUT=/work/{arm_out.relative_to(ROOT)}",
        "-e",
        f"SPARSE_PENALTY_OUT=/work/{arm_out.relative_to(ROOT)}",
        "-v",
        f"{ROOT}:/work",
        "-v",
        f"{CHECKPOINT}:/work/checkpoint:ro",
        IMAGE,
        "python3",
        "-m",
        "sglang.launch_server",
        *server_args,
    ]
    result = run(command, timeout=120)
    atomic(
        arm_out / "LAUNCH.json",
        {
            "command_after_image": command[command.index(IMAGE) + 1 :],
            "server_args": server_args,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(f"candidate_launch_failed:{result.stderr[-1000:]}")
    return server_args


def slope(rows: list[dict]) -> float | None:
    valid = [row for row in rows if "error" not in row][-100:]
    if len(valid) < 2:
        return None
    xs = [float(row["i"]) for row in valid]
    ys = [
        max(0.0, row["client_started_s"] - row["scheduled_s"])
        for row in valid
    ]
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    return (
        sum(
            (x_value - x_mean) * (y_value - y_mean)
            for x_value, y_value in zip(xs, ys)
        )
        / denominator
        if denominator
        else 0.0
    )


def reference(comparator: Path) -> dict:
    rows = [
        json.loads(line)
        for line in comparator.read_text().splitlines()
        if line.strip()
    ]
    elapsed = max(row["completed_s"] for row in rows)
    total_tokens = sum(row["usage"]["total_tokens"] for row in rows)
    tokens_per_second = total_tokens / elapsed
    return {
        "requests": len(rows),
        "elapsed_seconds": elapsed,
        "total_tokens": total_tokens,
        "final_client_queue_seconds": max(
            row["client_started_s"] - row["scheduled_s"] for row in rows
        ),
        "late_client_queue_slope_seconds_per_request": slope(rows),
        "tokens_per_second": tokens_per_second,
        "usd_per_million_total_tokens": (
            PLANNING_USD_PER_HOUR
            / 3600
            * 1_000_000
            / tokens_per_second
        ),
        "requests_sha256": sha256(comparator),
    }


def summarize_events(path: Path) -> dict:
    events = [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    steps = [event for event in events if event["kind"] == "decode_step"]
    transitions = [event for event in events if event["kind"] == "transition"]
    ngram = [event for event in steps if event["mode"] == "depth_12_ngram"]
    bypass = [
        event
        for event in steps
        if event["mode"] == "ordinary_greedy_target_decode"
    ]
    target_rows = sum(event["target_rows"] for event in steps)
    full_ngram_rows = sum(
        event["batch_size"] * 12 for event in steps
    )
    return {
        "events": len(events),
        "transition_events": transitions,
        "ngram_steps": len(ngram),
        "bypass_steps": len(bypass),
        "ngram_target_rows": sum(event["target_rows"] for event in ngram),
        "bypass_target_rows": sum(event["target_rows"] for event in bypass),
        "target_rows": target_rows,
        "full_ngram_target_rows": full_ngram_rows,
        "target_rows_saved": full_ngram_rows - target_rows,
        "target_row_reduction_fraction": (
            (full_ngram_rows - target_rows) / full_ngram_rows
            if full_ngram_rows
            else 0.0
        ),
        "target_forward_wall_ms": sum(
            event["target_forward_wall_ms"] for event in steps
        ),
        "ngram_target_forward_wall_ms": sum(
            event["target_forward_wall_ms"] for event in ngram
        ),
        "bypass_target_forward_wall_ms": sum(
            event["target_forward_wall_ms"] for event in bypass
        ),
        "cache_ownership_exact": all(
            event["allocated_cache_slots"] == event["batch_size"]
            and event["unique_cache_slots"] == event["batch_size"]
            for event in bypass
        ),
        "threshold_frozen": all(
            (event["batch_size"] < 8)
            == (event["mode"] == "depth_12_ngram")
            for event in steps
        ),
        "events_sha256": sha256(path),
    }


def prepare_comparator(name: str, scheduled: int) -> Path:
    rows = FULL_COMPARATOR.read_text().splitlines()
    if len(rows) != FULL_REQUESTS:
        raise RuntimeError("bound_comparator_row_count_mismatch")
    if scheduled == FULL_REQUESTS:
        return FULL_COMPARATOR
    path = OUT / f"{name}.comparator.jsonl"
    path.write_text("\n".join(rows[:scheduled]) + "\n")
    return path


def run_arm(base, name: str, scheduled: int) -> dict:
    arm_out = OUT / name
    arm_out.mkdir(parents=True, exist_ok=False)
    comparator = prepare_comparator(name, scheduled)
    run(["sudo", "docker", "rm", "-f", CONTAINER], timeout=120)
    run(
        [
            "sudo",
            "docker",
            "rm",
            "-f",
            "gemma4-ngram-two-stage-target-candidate",
        ],
        timeout=120,
    )
    base.ROOT = ROOT
    base.OUT = arm_out
    base.CONTROL = CONTROL
    base.COMPARATOR = comparator
    base.CONTAINER = CONTAINER
    base.SCHEDULED = scheduled
    base.launch = lambda: launch(arm_out)
    base.main()
    endpoint = json.loads((arm_out / "FINAL_TERMINAL.json").read_text())
    events_path = arm_out / "HIGH_LOAD_BYPASS_EVENTS.jsonl"
    if not events_path.exists():
        raise RuntimeError(f"{name}_missing_high_load_bypass_events")
    telemetry = summarize_events(events_path)
    rows = [
        json.loads(line)
        for line in (arm_out / "requests.jsonl").read_text().splitlines()
        if line.strip()
    ]
    primary = endpoint["primary"]
    primary["late_client_queue_slope_seconds_per_request"] = slope(rows)
    exact = (
        primary["completed"] == scheduled
        and not primary["failures"]
        and primary["output_token_sequences_matching_control"] == scheduled
        and primary["finish_reasons_matching_control"] == scheduled
        and primary["usage_matching_control"] == scheduled
        and primary["exact_index_aligned_semantics_matching_control"]
        == scheduled
    )
    baseline = reference(comparator)
    economics = endpoint.get("economics", {})
    throughput_gain = (
        economics.get("tokens_per_second", 0.0)
        / baseline["tokens_per_second"]
        - 1
    )
    cost_reduction = (
        1
        - economics.get("usd_per_million_total_tokens", float("inf"))
        / baseline["usd_per_million_total_tokens"]
    )
    drift_improvement = (
        baseline["final_client_queue_seconds"]
        - primary["final_client_queue_seconds"]
    )
    credible_positive = (
        exact
        and telemetry["bypass_steps"] > 0
        and telemetry["ngram_steps"] > 0
        and telemetry["target_rows_saved"] > 0
        and telemetry["cache_ownership_exact"]
        and telemetry["threshold_frozen"]
        and (
            throughput_gain > 0.005
            or cost_reduction > 0.005
            or drift_improvement > 0.5
        )
    )
    terminal = {
        "schema_version": 1,
        "arm": name,
        "scheduled": scheduled,
        "candidate_only": True,
        "control_replayed": False,
        "comparator_sha256": sha256(comparator),
        "exact_index_aligned_semantics": exact,
        "credible_positive": credible_positive,
        "primary": primary,
        "telemetry": telemetry,
        "baseline_reference": baseline,
        "economics": economics,
        "improvement": {
            "throughput_fraction": throughput_gain,
            "planning_cost_reduction_fraction": cost_reduction,
            "final_client_queue_seconds": drift_improvement,
        },
        "requests_sha256": sha256(arm_out / "requests.jsonl"),
        "finish_reason_and_usage_persisted": True,
        "failures_persisted": True,
    }
    atomic(arm_out / "ARM_TERMINAL.json", terminal)
    return terminal


def main() -> None:
    partial_arm = OUT / "prefix-through-870"
    if (
        partial_arm.exists()
        and not (OUT / "PREFIX_PERSISTED.json").exists()
        and not (OUT / "FINAL_TERMINAL.json").exists()
    ):
        archived = ROOT / f"out.invalid-preprefix-{int(time.time())}"
        manifest = {
            str(path.relative_to(OUT)): sha256(path)
            for path in sorted(OUT.rglob("*"))
            if path.is_file()
        }
        OUT.replace(archived)
        OUT.mkdir(parents=True, exist_ok=False)
        atomic(
            OUT / "REPAIR_ARCHIVE.json",
            {
                "reason": "preprefix_observer_failure",
                "archived_output_root": str(archived),
                "files_sha256": manifest,
            },
        )
    OUT.mkdir(parents=True, exist_ok=True)
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "scientific_invocation_started": False,
            "candidate_cuda_started": False,
            "phase": "bound_input_validation",
        },
    )
    expected = {
        "comparator.requests.jsonl": (
            "12f9c7807c6f46cc8258b7c5cdae6ab529e2fb3bd9c82298296f8616ab42a253"
        ),
        "installed-consumer-sources.tar.gz": (
            "a9f58ef78cc089747460dff368c8acd0ec26813f75b7ef974ec34a3aa77c0bd6"
        ),
    }
    for name, digest in expected.items():
        if sha256(BOUND / name) != digest:
            raise RuntimeError(f"bound_input_hash_mismatch:{name}")
    base = load_base()
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "scientific_invocation_started": True,
            "candidate_cuda_started": False,
            "phase": "prefix_through_870",
        },
    )
    prefix = run_arm(base, "prefix-through-870", PREFIX_REQUESTS)
    atomic(OUT / "PREFIX_PERSISTED.json", prefix)
    full = None
    if prefix["exact_index_aligned_semantics"] and prefix["credible_positive"]:
        atomic(
            OUT / "INVOCATION_STATE.json",
            {
                "schema_version": 1,
                "scientific_invocation_started": True,
                "candidate_cuda_started": True,
                "phase": "conditional_full_1036",
                "prefix_terminal_sha256": sha256(
                    OUT / "prefix-through-870/ARM_TERMINAL.json"
                ),
            },
        )
        full = run_arm(base, "full-1036", FULL_REQUESTS)
    result = (
        "exact_positive_prefix_full_trajectory_complete"
        if full is not None
        else (
            "exact_nonpositive_prefix_gate_closed"
            if prefix["exact_index_aligned_semantics"]
            else "semantic_divergence_prefix_gate_closed"
        )
    )
    atomic(
        OUT / "FINAL_TERMINAL.json",
        {
            "schema_version": 1,
            "result": result,
            "candidate_sample_consumed": True,
            "prefix": prefix,
            "full": full,
            "full_trajectory_started": full is not None,
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        state_path = OUT / "INVOCATION_STATE.json"
        state = (
            json.loads(state_path.read_text()) if state_path.exists() else {}
        )
        logs = run(["sudo", "docker", "logs", CONTAINER], timeout=60)
        atomic(
            OUT / "ATTEMPT_TERMINAL.json",
            {
                "schema_version": 1,
                "result": "recoverable_candidate_harness_or_runtime_failure",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
                "invocation_state": state,
                "prefix_persisted": (OUT / "PREFIX_PERSISTED.json").exists(),
                "container_logs_stdout_sha256": hashlib.sha256(
                    logs.stdout.encode()
                ).hexdigest(),
                "container_logs_stderr_sha256": hashlib.sha256(
                    logs.stderr.encode()
                ).hexdigest(),
            },
        )
        (OUT / "container.stdout.log").write_text(logs.stdout)
        (OUT / "container.stderr.log").write_text(logs.stderr)
        raise
