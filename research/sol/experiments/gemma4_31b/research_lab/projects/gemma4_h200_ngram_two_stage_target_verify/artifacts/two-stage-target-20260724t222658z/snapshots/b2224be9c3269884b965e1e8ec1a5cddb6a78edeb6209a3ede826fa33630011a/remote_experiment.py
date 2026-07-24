#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import traceback


ROOT = Path("/home/glmrunner/gemma4-h200-ngram-two-stage-target-verify")
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
CONTAINER = "gemma4-ngram-two-stage-target-candidate"
PREFIX_REQUESTS = 871
FULL_REQUESTS = 1036


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


def launch(base, arm_out: Path) -> list[str]:
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
        f"TWO_STAGE_OUT=/work/{arm_out.relative_to(ROOT)}",
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


def summarize_events(path: Path) -> dict:
    events = [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    full_rows = sum(row["full_target_rows"] for row in events)
    target_rows = sum(row["target_rows"] for row in events)
    saved_rows = sum(row["target_rows_saved"] for row in events)
    survivors = sum(row["stage_survivor_count"] for row in events)
    verified_requests = sum(row["batch_size"] for row in events)
    accepted_drafts = [
        value
        for row in events
        for value in row["num_correct_drafts"]
    ]
    return {
        "events": len(events),
        "verified_requests": verified_requests,
        "tree_depth_observed": sorted(
            {row["tree_depth"] for row in events}
        ),
        "producer_tree_unchanged": all(
            row["producer_tree_unchanged"] for row in events
        ),
        "stage_one_rows": sum(row["stage_one_rows"] for row in events),
        "stage_survivors": survivors,
        "stage_two_rows": sum(row["stage_two_rows"] for row in events),
        "target_rows": target_rows,
        "full_target_rows": full_rows,
        "target_rows_saved": saved_rows,
        "target_row_reduction_fraction": (
            saved_rows / full_rows if full_rows else 0.0
        ),
        "stage_one_target_forward_ms": sum(
            row["stage_one_target_forward_ms"] for row in events
        ),
        "stage_two_target_forward_ms": sum(
            row["stage_two_target_forward_ms"] for row in events
        ),
        "continuation_prefix_masks_exact": all(
            row["continuation_prefix_mask_all_true"] for row in events
        ),
        "full_cache_ownership_exact": all(
            row["full_cache_slots_unique"]
            and row["accepted_cache_slots_unique"]
            and row["stage_one_cache_slots"]
            == row["batch_size"] * 6
            and row["stage_two_cache_slots_owned_by_survivors"]
            == row["stage_survivor_count"] * 6
            for row in events
        ),
        "accepted_draft_mean": (
            statistics.mean(accepted_drafts) if accepted_drafts else None
        ),
        "accepted_draft_count": len(accepted_drafts),
        "accepted_bonus_tokens_persisted": all(
            len(row["accepted_bonus_tokens"]) == row["batch_size"]
            for row in events
        ),
        "events_sha256": sha256(path),
    }


def run_arm(
    base,
    name: str,
    scheduled: int,
    comparator: Path,
) -> dict:
    arm_out = OUT / name
    arm_out.mkdir(parents=True, exist_ok=False)
    run(["sudo", "docker", "rm", "-f", CONTAINER], timeout=120)
    base.ROOT = ROOT
    base.OUT = arm_out
    base.CONTROL = CONTROL
    base.COMPARATOR = comparator
    base.CONTAINER = CONTAINER
    base.SCHEDULED = scheduled
    base.launch = lambda: launch(base, arm_out)
    base.main()
    endpoint = json.loads((arm_out / "FINAL_TERMINAL.json").read_text())
    events_path = arm_out / "TWO_STAGE_EVENTS.jsonl"
    if not events_path.exists():
        raise RuntimeError(f"{name}_missing_two_stage_events")
    telemetry = summarize_events(events_path)
    primary = endpoint["primary"]
    exact = (
        primary["completed"] == scheduled
        and not primary["failures"]
        and primary["output_token_sequences_matching_control"] == scheduled
        and primary["finish_reasons_matching_control"] == scheduled
        and primary["usage_matching_control"] == scheduled
        and primary["exact_index_aligned_semantics_matching_control"]
        == scheduled
    )
    positive = (
        exact
        and telemetry["producer_tree_unchanged"]
        and telemetry["tree_depth_observed"] == [12]
        and telemetry["target_rows_saved"] > 0
        and telemetry["continuation_prefix_masks_exact"]
        and telemetry["full_cache_ownership_exact"]
        and telemetry["accepted_bonus_tokens_persisted"]
    )
    terminal = {
        "schema_version": 1,
        "arm": name,
        "scheduled": scheduled,
        "candidate_only": True,
        "control_replayed": False,
        "comparator_sha256": sha256(comparator),
        "exact_index_aligned_semantics": exact,
        "positive": positive,
        "primary": primary,
        "telemetry": telemetry,
        "requests_sha256": sha256(arm_out / "requests.jsonl"),
        "finish_reason_and_usage_persisted": True,
        "accepted_and_bonus_tokens_persisted": (
            telemetry["accepted_bonus_tokens_persisted"]
        ),
    }
    atomic(arm_out / "ARM_TERMINAL.json", terminal)
    return terminal


def main() -> None:
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
        "comparator.telemetry.jsonl": (
            "ccd467e9fcdaeced3d1e9bee59627263e80b86079109272d0f226ab698f9a731"
        ),
        "installed-consumer-sources.tar.gz": (
            "a9f58ef78cc089747460dff368c8acd0ec26813f75b7ef974ec34a3aa77c0bd6"
        ),
    }
    actual = {name: sha256(BOUND / name) for name in expected}
    if actual != expected:
        raise RuntimeError(f"bound_input_hash_mismatch:{actual}")
    rows = FULL_COMPARATOR.read_text().splitlines()
    if len(rows) != FULL_REQUESTS:
        raise RuntimeError(f"full_comparator_row_count:{len(rows)}")
    prefix_comparator = BOUND / "prefix-through-870.requests.jsonl"
    prefix_comparator.write_text("\n".join(rows[:PREFIX_REQUESTS]) + "\n")
    run(
        [
            "sudo",
            "docker",
            "rm",
            "-f",
            "gemma4-ngram-adaptive-candidate",
        ],
        timeout=120,
    )
    base = load_base()
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "scientific_invocation_started": True,
            "candidate_cuda_started": False,
            "phase": "prefix_through_request_870",
        },
    )
    prefix = run_arm(
        base, "prefix-through-870", PREFIX_REQUESTS, prefix_comparator
    )
    atomic(
        OUT / "PREFIX_PERSISTED.json",
        {
            "schema_version": 1,
            "prefix_terminal_sha256": sha256(
                OUT / "prefix-through-870/ARM_TERMINAL.json"
            ),
            "requests_sha256": prefix["requests_sha256"],
            "positive": prefix["positive"],
        },
    )
    if not prefix["positive"]:
        atomic(
            OUT / "FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "classification": "scientific_terminal",
                "result": "two_stage_prefix_nonpositive_or_inexact",
                "prefix": prefix,
                "full_trajectory_executed": False,
            },
        )
        return
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "scientific_invocation_started": True,
            "candidate_cuda_started": True,
            "phase": "conditional_full_1036",
            "prefix_persisted": True,
        },
    )
    full = run_arm(base, "full-1036", FULL_REQUESTS, FULL_COMPARATOR)
    atomic(
        OUT / "FINAL_TERMINAL.json",
        {
            "schema_version": 1,
            "classification": "scientific_terminal",
            "result": (
                "exact_positive_two_stage_full_trajectory"
                if full["positive"]
                else "two_stage_full_trajectory_nonpositive_or_inexact"
            ),
            "prefix": prefix,
            "full": full,
            "full_trajectory_executed": True,
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logs = run(["sudo", "docker", "logs", CONTAINER], timeout=120)
        (OUT / "container.stdout.log").write_text(logs.stdout)
        (OUT / "container.stderr.log").write_text(logs.stderr)
        state = (
            json.loads((OUT / "INVOCATION_STATE.json").read_text())
            if (OUT / "INVOCATION_STATE.json").exists()
            else {}
        )
        atomic(
            OUT / "ATTEMPT_TERMINAL.json",
            {
                "schema_version": 1,
                "classification": (
                    "ordinary_integration_or_consumer_defect"
                ),
                "error": repr(error),
                "traceback": traceback.format_exc(),
                "scientific_invocation_started": bool(
                    state.get("scientific_invocation_started")
                ),
                "candidate_cuda_started": bool(
                    state.get("candidate_cuda_started")
                ),
                "phase": state.get("phase"),
                "prefix_persisted": (
                    OUT / "PREFIX_PERSISTED.json"
                ).exists(),
                "container_stdout_sha256": hashlib.sha256(
                    logs.stdout.encode()
                ).hexdigest(),
                "container_stderr_sha256": hashlib.sha256(
                    logs.stderr.encode()
                ).hexdigest(),
            },
        )
        raise
