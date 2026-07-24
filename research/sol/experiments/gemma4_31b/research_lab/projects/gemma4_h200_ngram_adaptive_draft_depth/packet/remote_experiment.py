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
import threading
import time


ROOT = Path("/home/glmrunner/gemma4-h200-ngram-adaptive-depth")
OUT = ROOT / "out"
CONTROL = ROOT / "inputs/control"
COMPARATOR = ROOT / "inputs/comparator/requests.jsonl"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
MODEL = "google/gemma-4-31B-it"
REFERENCE_CONTAINER = "gemma4-ngram-adaptive-reference"
CANDIDATE_CONTAINER = "gemma4-ngram-adaptive-candidate"
DONOR_CONTAINER = "gemma4-ngram-sparse-penalty-candidate"
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
        "/sgl-workspace/sglang/python/sglang/srt/speculative/ngram_worker.py",
        "/sgl-workspace/sglang/python/sglang/srt/speculative/cpp_ngram/ngram_corpus.py",
        "/sgl-workspace/sglang/python/sglang/srt/managers/schedule_batch.py",
        "/sgl-workspace/sglang/python/sglang/srt/managers/scheduler.py",
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
        "ADAPTIVE_NGRAM_OUT=/work/out",
        "-e",
        f"ADAPTIVE_TRACE_NAME={patch}",
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


def component_request(
    base, source: dict, index: int, barrier: threading.Barrier
) -> dict:
    request = base.body(source, f"component-{index}")
    request["prompt"][535] = 210000 + index
    request["min_tokens"] = 32
    request["max_tokens"] = 32
    barrier.wait()
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


def run_component_arm(base, container: str, patch: str) -> list[dict]:
    run(["sudo", "docker", "rm", "-f", container], timeout=60)
    base.CONTAINER = container
    launch(container, patch)
    wait_server(base)
    trace = json.loads((CONTROL / "TRACE_PACKET.json").read_text())
    group = next(x for x in trace["primary_groups"] if x["name"] == "primary_c1")
    warmup = base.body(group["warmup"], f"{patch}-component-warmup")
    warmup["min_tokens"] = 1
    warmup["max_tokens"] = 1
    base.post(warmup)
    barrier = threading.Barrier(8)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(
                component_request,
                base,
                copy.deepcopy(group["scored"][i % len(group["scored"])]),
                i,
                barrier,
            )
            for i in range(8)
        ]
        rows = [future.result() for future in futures]
    atomic(f"COMPONENT_REQUESTS_{patch.upper()}.json", rows)
    logs = run(["sudo", "docker", "logs", container], timeout=120)
    (OUT / f"{patch}-component-server.stdout.log").write_text(logs.stdout)
    (OUT / f"{patch}-component-server.stderr.log").write_text(logs.stderr)
    run(["sudo", "docker", "rm", "-f", container], timeout=120)
    return rows


def indexed(trace: dict) -> dict[str, dict]:
    return {
        identity: {
            "draft_tokens": trace["draft_tokens"][index],
            "target_predict": trace["target_predict"][index],
            "num_correct_drafts": trace["num_correct_drafts"][index],
            "accepted_bonus_tokens": trace["accepted_bonus_tokens"][index],
        }
        for index, identity in enumerate(trace["request_prompt_sha256"])
    }


def run_component(base) -> dict:
    run(["sudo", "docker", "rm", "-f", DONOR_CONTAINER], timeout=60)
    atomic(
        "INVOCATION_STATE.json",
        {
            "science_started": True,
            "phase": "high_load_depth_reference",
            "requests": 8,
        },
    )
    reference_rows = run_component_arm(
        base, REFERENCE_CONTAINER, "reference"
    )
    atomic(
        "INVOCATION_STATE.json",
        {
            "science_started": True,
            "phase": "high_load_depth_candidate",
            "requests": 8,
        },
    )
    candidate_rows = run_component_arm(
        base, CANDIDATE_CONTAINER, "candidate"
    )
    reference = json.loads(
        (OUT / "HIGH_LOAD_REFERENCE_TRACE.json").read_text()
    )
    candidate = json.loads(
        (OUT / "HIGH_LOAD_CANDIDATE_TRACE.json").read_text()
    )
    reference_index = indexed(reference)
    candidate_index = indexed(candidate)
    shared = sorted(set(reference_index) & set(candidate_index))
    comparisons = []
    for identity in shared:
        ref = reference_index[identity]
        cand = candidate_index[identity]
        comparisons.append(
            {
                "request_prompt_sha256": identity,
                "draft_prefix_exact": (
                    cand["draft_tokens"] == ref["draft_tokens"][:6]
                ),
                "target_predict_prefix_exact": (
                    cand["target_predict"] == ref["target_predict"][:6]
                ),
                "num_correct_drafts_exact": (
                    cand["num_correct_drafts"]
                    == ref["num_correct_drafts"]
                ),
                "accepted_bonus_tokens_exact": (
                    cand["accepted_bonus_tokens"]
                    == ref["accepted_bonus_tokens"]
                ),
            }
        )
    failures = [
        row
        for row in reference_rows + candidate_rows
        if "error" in row
    ]
    exact = bool(
        candidate["real_cuda_call"]
        and candidate["batch_size"] >= 8
        and candidate["draft_depth"] == 6
        and candidate["target_rows_per_request"] == 6
        and reference["greedy_consumer_source_sha256"]
        == candidate["greedy_consumer_source_sha256"]
        and len(shared) == 8
        and all(
            row["draft_prefix_exact"]
            and row["target_predict_prefix_exact"]
            and row["num_correct_drafts_exact"]
            and row["accepted_bonus_tokens_exact"]
            for row in comparisons
        )
        and not failures
    )
    terminal = {
        "result": "exact_adaptive_depth_component" if exact else "adaptive_depth_component_reject",
        "component_science_consumed": True,
        "candidate_endpoint_admitted": exact,
        "request_failures": failures,
        "reference": reference,
        "candidate": candidate,
        "comparisons": comparisons,
        "physical_hypothesis": (
            "At eight or more running requests, the first rejection occurs "
            "within six rows, so rows seven through twelve do no useful "
            "greedy acceptance work."
        ),
    }
    atomic("COMPONENT_TERMINAL.json", terminal)
    return terminal


def candidate_launch(base) -> list[str]:
    return launch(CANDIDATE_CONTAINER, "candidate")


def run_endpoint(base, component: dict) -> None:
    component_trace = OUT / "HIGH_LOAD_CANDIDATE_TRACE.json"
    if component_trace.exists():
        (OUT / "COMPONENT_HIGH_LOAD_CANDIDATE_TRACE.json").write_bytes(
            component_trace.read_bytes()
        )
    events_path = OUT / "ADAPTIVE_DEPTH_EVENTS.jsonl"
    if events_path.exists():
        events_path.unlink()
    base.CONTAINER = CANDIDATE_CONTAINER
    base.launch = lambda: candidate_launch(base)
    base.main()
    terminal_path = OUT / "FINAL_TERMINAL.json"
    terminal = json.loads(terminal_path.read_text())
    terminal["result"] = "measured_adaptive_ngram_draft_depth_candidate"
    terminal["component_terminal_sha256"] = hashlib.sha256(
        (OUT / "COMPONENT_TERMINAL.json").read_bytes()
    ).hexdigest()
    terminal["intervention"] = {
        "kind": "load_adaptive_ngram_draft_depth",
        "rule": {
            "running_requests_1_to_7": 12,
            "running_requests_8_or_more": 6,
        },
        "stacked": "direct_sparse_min_new_token_columns",
        "consumer": "unchanged NgramVerifyInput._greedy_verify",
    }
    events = [
        json.loads(line)
        for line in events_path.read_text().splitlines()
        if line.strip()
    ]
    depth_by_load = {}
    for name, predicate in (
        ("running_requests_1_to_7", lambda row: row["batch_size"] < 8),
        ("running_requests_8_or_more", lambda row: row["batch_size"] >= 8),
    ):
        selected = [row for row in events if predicate(row)]
        request_count = sum(row["batch_size"] for row in selected)
        accepted_drafts = [
            value
            for row in selected
            for value in row["num_correct_drafts"]
        ]
        depth_by_load[name] = {
            "verify_calls": len(selected),
            "request_verifications": request_count,
            "target_rows": sum(row["target_rows"] for row in selected),
            "observed_depths": sorted(
                {row["draft_depth"] for row in selected}
            ),
            "mean_accepted_drafts": (
                statistics.mean(accepted_drafts)
                if accepted_drafts
                else None
            ),
            "mean_accept_length_with_bonus": (
                statistics.mean(value + 1 for value in accepted_drafts)
                if accepted_drafts
                else None
            ),
        }
    terminal["adaptive_depth_telemetry"] = {
        "events": len(events),
        "by_load": depth_by_load,
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
        "zero_retractions": (
            terminal.get("metric_final", {}).get(
                "sglang:num_retracted_reqs", float("inf")
            )
            == 0
        ),
        "final_server_queue_empty": (
            terminal.get("metric_final", {}).get(
                "sglang:num_queue_reqs", float("inf")
            )
            == 0
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
        "late_run_slope_non_positive": (
            primary.get(
                "late_client_queue_slope_seconds_per_request",
                float("inf"),
            )
            <= 0
        ),
        "frozen_depth_rule_observed": (
            depth_by_load["running_requests_1_to_7"][
                "observed_depths"
            ]
            in ([], [12])
            and depth_by_load["running_requests_8_or_more"][
                "observed_depths"
            ]
            == [6]
        ),
    }
    atomic("FINAL_TERMINAL.json", terminal)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not (
        (ROOT / "installed-consumer-sources.tar.gz").exists()
        and (OUT / "INSTALLED_SOURCE_CAPTURE.json").exists()
    ):
        capture_installed_sources()
    base = load_base()
    component = run_component(base)
    if not component["candidate_endpoint_admitted"]:
        atomic(
            "FINAL_TERMINAL.json",
            {
                "result": "adaptive_depth_component_reject_no_endpoint",
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
        for container in (REFERENCE_CONTAINER, CANDIDATE_CONTAINER):
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
