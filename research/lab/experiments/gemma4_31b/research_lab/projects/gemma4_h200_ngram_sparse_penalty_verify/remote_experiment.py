#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time


ROOT = Path("/home/glmrunner/gemma4-h200-ngram-sparse-penalty")
OUT = ROOT / "out"
CONTROL = ROOT / "inputs/control"
COMPARATOR = ROOT / "inputs/comparator/requests.jsonl"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
MODEL = "google/gemma-4-31B-it"
COMPONENT_CONTAINER = "gemma4-ngram-sparse-penalty-component"
CANDIDATE_CONTAINER = "gemma4-ngram-sparse-penalty-candidate"
DONOR_CONTAINER = "gemma4-ngram-torch-staircase-candidate"
CHECKPOINT = (
    "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
)


def atomic(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(
    args: list[str], timeout: int | None = None, binary: bool = False
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        text=not binary,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def capture_installed_sources() -> None:
    paths = [
        "/sgl-workspace/sglang/python/sglang/srt/sampling/penaltylib",
        "/sgl-workspace/sglang/python/sglang/srt/speculative/ngram_info.py",
        "/sgl-workspace/sglang/python/sglang/srt/sampling/sampling_batch_info.py",
        "/sgl-workspace/sglang/python/sglang/srt/model_executor/model_runner.py",
    ]
    captured = run(
        [
            "sudo",
            "docker",
            "exec",
            DONOR_CONTAINER,
            "tar",
            "-czf",
            "-",
            *paths,
        ],
        timeout=180,
        binary=True,
    )
    if captured.returncode:
        raise RuntimeError(
            "installed_source_capture_failed:"
            + captured.stderr.decode(errors="replace")[-1000:]
        )
    archive = ROOT / "installed-consumer-sources.tar.gz"
    archive.write_bytes(captured.stdout)
    inspect = run(["sudo", "docker", "inspect", DONOR_CONTAINER], timeout=60)
    (ROOT / "donor-container-inspect.json").write_text(inspect.stdout)
    atomic(
        "INSTALLED_SOURCE_CAPTURE.json",
        {
            "archive": archive.name,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "paths": paths,
            "donor_container": DONOR_CONTAINER,
            "capture_before_mutation": True,
        },
    )


def load_base():
    spec = importlib.util.spec_from_file_location(
        "bound_remote_candidate", ROOT / "base/remote_candidate.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("bound_base_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.OUT = OUT
    module.CONTROL = CONTROL
    module.COMPARATOR = COMPARATOR
    module.CONTAINER = CANDIDATE_CONTAINER
    return module


def frozen_server_args() -> list[str]:
    launch = json.loads((CONTROL / "launch-5000.json").read_text())
    command = launch["cmd"]
    index = command.index("sglang.launch_server")
    return command[index + 1 :]


def launch(container: str, patch: str) -> list[str]:
    server_args = frozen_server_args()
    command = [
        "sudo",
        "docker",
        "run",
        "-d",
        "--name",
        container,
        "--gpus",
        "all",
        "--ipc=host",
        "--network",
        "host",
        "-e",
        f"PYTHONPATH=/work/{patch}",
        "-e",
        "SPARSE_PENALTY_OUT=/work/out",
        "-e",
        "SPARSE_PENALTY_TARGET_ROWS=384",
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
        f"{patch.upper()}_LAUNCH.json",
        {
            "command_after_image": command[command.index(IMAGE) + 1 :],
            "server_args": server_args,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(f"{patch}_launch_failed")
    return server_args


def wait_server(base) -> None:
    base.wait_server()


def component_request(base, source: dict, index: int) -> dict:
    request = base.body(source, f"component-{index}")
    request["prompt"][535] = 210000 + index
    started = time.monotonic()
    try:
        parsed, timing, _ = base.post(request)
        return {
            "i": index,
            "latency_seconds": time.monotonic() - started,
            "completion_tokens": parsed["usage"]["completion_tokens"],
            "timing": timing,
        }
    except Exception as exc:
        return {"i": index, "error": repr(exc)}


def run_component(base) -> dict:
    run(["sudo", "docker", "rm", "-f", DONOR_CONTAINER], timeout=60)
    run(["sudo", "docker", "rm", "-f", COMPONENT_CONTAINER], timeout=60)
    base.CONTAINER = COMPONENT_CONTAINER
    launch(COMPONENT_CONTAINER, "component")
    wait_server(base)
    trace = json.loads((CONTROL / "TRACE_PACKET.json").read_text())
    group = next(x for x in trace["primary_groups"] if x["name"] == "primary_c1")
    base.post(base.body(group["warmup"], "component-warmup"))
    atomic(
        "INVOCATION_STATE.json",
        {
            "science_started": True,
            "phase": "real_call_component",
            "requests": 48,
        },
    )
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
        futures = [
            pool.submit(
                component_request,
                base,
                copy.deepcopy(group["scored"][i % len(group["scored"])]),
                i,
            )
            for i in range(48)
        ]
        rows = [future.result() for future in futures]
    elapsed = time.monotonic() - started
    atomic("COMPONENT_REQUESTS.json", rows)
    component_path = OUT / "COMPONENT_CANDIDATE.json"
    if not component_path.exists():
        raise RuntimeError("component_target_shape_not_observed")
    measured = json.loads(component_path.read_text())
    baseline = measured["baseline_penalty_plus_argmax_ms"]["median"]
    candidate = measured["candidate_penalty_plus_argmax_ms"]["median"]
    failures = [row for row in rows if "error" in row]
    admitted = bool(
        measured.get("exact")
        and measured.get("shape") == [384, 262144]
        and measured.get("nonzero_coordinates_after_repeat", 10**9) <= 384 * 4
        and candidate < baseline
        and baseline - candidate >= 0.05
        and not failures
    )
    terminal = {
        "result": (
            "exact_sparse_positive_component"
            if admitted
            else "penalty_component_reject"
        ),
        "component_science_consumed": True,
        "candidate_endpoint_admitted": admitted,
        "request_elapsed_seconds": elapsed,
        "request_failures": failures,
        "component": measured,
        "physical_hypothesis": (
            "Direct stop-token column writes remove a dense FP32 logits "
            "read-modify-write before the unchanged greedy argmax."
        ),
        "predicted_counter_movement": {
            "removed_dense_penalty_read_write_bytes_per_max_call": measured.get(
                "dense_penalty_application_read_write_bytes"
            ),
            "argmax_bytes_unchanged": measured.get("dense_logits_bytes"),
        },
    }
    atomic("COMPONENT_TERMINAL.json", terminal)
    return terminal


def candidate_launch(base) -> list[str]:
    return launch(CANDIDATE_CONTAINER, "candidate")


def run_endpoint(base, component: dict) -> None:
    run(["sudo", "docker", "rm", "-f", COMPONENT_CONTAINER], timeout=60)
    base.CONTAINER = CANDIDATE_CONTAINER
    base.launch = lambda: candidate_launch(base)
    base.main()
    terminal_path = OUT / "FINAL_TERMINAL.json"
    terminal = json.loads(terminal_path.read_text())
    terminal["result"] = "measured_direct_sparse_penalty_candidate"
    terminal["component_terminal_sha256"] = hashlib.sha256(
        (OUT / "COMPONENT_TERMINAL.json").read_bytes()
    ).hexdigest()
    terminal["intervention"] = {
        "kind": "direct_sparse_min_new_token_columns",
        "producer": "BatchedMinNewTokensPenalizer sparse stop-token ids",
        "consumer": "unchanged NgramVerifyInput._greedy_verify",
        "dense_penalty_matrix_materialized": False,
        "request_or_scheduler_setting_changed": False,
    }
    primary = terminal["primary"]
    late_windows = json.loads((OUT / "WINDOWS.json").read_text())[-3:]
    if len(late_windows) >= 2:
        xs = [
            (row["request_index_begin"] + row["request_index_end_exclusive"])
            / 2
            for row in late_windows
        ]
        ys = [row["client_queue_mean_seconds"] for row in late_windows]
        x_mean = statistics.mean(xs)
        y_mean = statistics.mean(ys)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        terminal["primary"]["late_client_queue_slope_seconds_per_request"] = (
            sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
            / denominator
            if denominator
            else None
        )
    terminal["decision"] = {
        "exact_index_aligned_semantics": (
            primary["exact_index_aligned_semantics_matching_control"]
            == primary["scheduled"]
        ),
        "zero_failures": not primary["failures"],
        "final_release_drift_within_one_interval": (
            primary["final_client_queue_seconds"] <= base.ARRIVAL_SPACING
        ),
        "planning_cost_at_or_below_0_14": (
            terminal.get("economics", {}).get(
                "usd_per_million_total_tokens", float("inf")
            )
            <= 0.14
        ),
    }
    atomic("FINAL_TERMINAL.json", terminal)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    capture_installed_sources()
    base = load_base()
    component = run_component(base)
    if not component["candidate_endpoint_admitted"]:
        atomic(
            "FINAL_TERMINAL.json",
            {
                "result": "penalty_component_reject_no_endpoint",
                "candidate_science_consumed": False,
                "component": component,
            },
        )
        return
    atomic(
        "INVOCATION_STATE.json",
        {
            "science_started": False,
            "phase": "component_persisted_candidate_server_load",
        },
    )
    run_endpoint(base, component)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logs = {}
        for container in (COMPONENT_CONTAINER, CANDIDATE_CONTAINER):
            result = run(["sudo", "docker", "logs", container], timeout=60)
            logs[container] = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
            (OUT / f"{container}.stdout.log").write_text(result.stdout)
            (OUT / f"{container}.stderr.log").write_text(result.stderr)
        state = (
            json.loads((OUT / "INVOCATION_STATE.json").read_text())
            if (OUT / "INVOCATION_STATE.json").exists()
            else {}
        )
        atomic(
            "ATTEMPT_TERMINAL.json",
            {
                "result": "recoverable_experiment_or_consumer_defect",
                "error": repr(exc),
                "science_started": bool(state.get("science_started")),
                "phase": state.get("phase"),
                "component_persisted": (OUT / "COMPONENT_TERMINAL.json").exists(),
                "candidate_cuda_marker": (OUT / "CANDIDATE_PATH.json").exists(),
                "logs_sha256": {
                    container: {
                        stream: hashlib.sha256(
                            value[stream].encode()
                        ).hexdigest()
                        for stream in ("stdout", "stderr")
                    }
                    for container, value in logs.items()
                },
            },
        )
        raise
