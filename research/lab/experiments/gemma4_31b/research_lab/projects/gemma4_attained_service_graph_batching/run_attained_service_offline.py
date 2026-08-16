#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

from attained_service_graph_batching import (
    RequestState,
    GraphShapeObserver,
    order_offline,
    read_graph_trace,
)


ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECTS = LAB / "projects"
REPO = next(parent for parent in ROOT.parents if (parent / ".git").exists())
OUTPUT = ROOT / "ATTAINED_SERVICE_GRAPH_BATCHING_OFFLINE_TERMINAL.json"
CAMPAIGN = LAB / "CAMPAIGN.md"
PROJECT = ROOT / "PROJECT.md"
DECODE_TERMINAL = (
    PROJECTS
    / "gemma4_decode_scheduler_task_graph"
    / "DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json"
)
PREFIX_TERMINAL = (
    PROJECTS
    / "gemma4_prefix_affinity_batching_economics"
    / "PREFIX_AFFINITY_BATCHING_OFFLINE_TERMINAL.json"
)
PREFIX_RUNNER = (
    PROJECTS
    / "gemma4_prefix_affinity_batching_economics"
    / "run_prefix_affinity_offline.py"
)
WORKLOAD = (
    PROJECTS
    / "gemma4_causal_parallel_offset_head"
    / "inputs"
    / "qualified_c32_workload.json"
)
BOUND_RUNNER = (
    PROJECTS
    / "gemma4_c32_graph_gap_elision"
    / "inputs"
    / "bound"
    / "exact_runner.py"
)
CONFIG = (
    PROJECTS
    / "gemma4_c32_graph_gap_elision"
    / "inputs"
    / "bound"
    / "config.json"
)
QUALIFIED_TERMINAL = (
    PROJECTS
    / "gemma4_h200_ngram_decode_equivalent_verifier"
    / "artifacts"
    / "h200-verifier-20260724t103131Z"
    / "retrieved"
    / "artifacts"
    / "candidate-full-c32"
    / "TERMINAL.json"
)
SERVER_STDERR = QUALIFIED_TERMINAL.parents[1] / "candidate-full-server.stderr"
SGLANG_PYTHON = REPO / ".agents/runtime/sglang-v0.5.13-source/python"
SOURCE_FILES = {
    "schedule_policy": SGLANG_PYTHON
    / "sglang/srt/managers/schedule_policy.py",
    "scheduler": SGLANG_PYTHON / "sglang/srt/managers/scheduler.py",
    "cuda_graph_runner": SGLANG_PYTHON
    / "sglang/srt/model_executor/cuda_graph_runner.py",
    "server_args": SGLANG_PYTHON / "sglang/srt/server_args.py",
}
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
TARGET_COST_PER_MILLION = 0.109725
EXPECTED = {
    "decode_terminal": (
        "13cd63fa2937ea1fdd3af741a63ea18c5517bdb0d922a7df786e0d0d8fbafd83"
    ),
    "prefix_terminal": (
        "9c074b1b482ab55b1c2814fc3d98e86ecbf7efc42bde5323e8144aa3d1f4f9bb"
    ),
    "qualified_terminal": (
        "7090c0ebb733f5021c464bc55d82fcd68e2abb52b820408c89724d95c03fd9dd"
    ),
    "workload": (
        "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d"
    ),
    "bound_runner": (
        "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7"
    ),
    "server_stderr": (
        "4be9ec993112241270375b356160ab5410c3ce3868a7a40ba37d1b72cbca296a"
    ),
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def relative(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(LAB))
    except ValueError:
        return str(path.relative_to(REPO))


def manifest(path: pathlib.Path) -> dict[str, object]:
    return {
        "path": relative(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def load_module(path: pathlib.Path, name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def request_hashes() -> list[str]:
    prefix = load_module(PREFIX_RUNNER, "prefix_affinity_runner")
    runner = load_module(BOUND_RUNNER, "bound_exact_runner")
    return [
        hashlib.sha256(canonical(body)).hexdigest()
        for body in prefix.build_requests(runner)
    ]


def nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def graph_buckets() -> list[int]:
    text = SERVER_STDERR.read_text(errors="replace")
    match = re.search(r"Capture cuda graph bs \[([0-9, ]+)\]", text)
    if match is None:
        raise RuntimeError("current-runtime CUDA graph buckets unavailable")
    return [int(value) for value in match.group(1).split(",")]


def stage_source(candidate_hash: str) -> dict[str, object]:
    stage = ROOT / "artifacts" / f"staged-sglang-{candidate_hash[:16]}"
    if stage.exists():
        shutil.rmtree(stage)
    for name in ("schedule_policy", "cuda_graph_runner", "server_args"):
        source = SOURCE_FILES[name]
        destination = stage / source.relative_to(SGLANG_PYTHON)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    installer = ROOT / "install_attained_service_graph_batching.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(installer),
            "--sglang-python",
            str(stage),
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"source installation failed: {completed.stderr[-4000:]}"
        )
    staged = {
        "candidate": stage
        / "sglang/srt/managers/attained_service_graph_batching.py",
        "schedule_policy": stage / "sglang/srt/managers/schedule_policy.py",
        "cuda_graph_runner": stage
        / "sglang/srt/model_executor/cuda_graph_runner.py",
        "server_args": stage / "sglang/srt/server_args.py",
    }
    for path in staged.values():
        ast.parse(path.read_text(), filename=str(path))
    return {
        "artifact_root": relative(stage),
        "installer_exit_code": completed.returncode,
        "installer_stdout": completed.stdout.strip(),
        "files": {name: manifest(path) for name, path in staged.items()},
        "claims": {
            "cli_selects_attained_service": (
                '"attained-service"' in staged["server_args"].read_text()
            ),
            "ready_queue_calls_candidate_key": (
                "waiting_queue.sort(key=attained_service_sort_key)"
                in staged["schedule_policy"].read_text()
            ),
            "graph_consumer_observes_selected_shape": (
                "observe_graph_shape(raw_bs=raw_bs, padded_bs=bs)"
                in staged["cuda_graph_runner"].read_text()
            ),
            "all_staged_sources_parse": True,
        },
    }


def observer_test() -> dict[str, object]:
    with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temporary:
        path = pathlib.Path(temporary) / "trace.bin"
        observer = GraphShapeObserver(path)
        observer.observe(raw_bs=9, padded_bs=10)
        observer.observe(raw_bs=10, padded_bs=10)
        observer.observe(raw_bs=11, padded_bs=12)
        observed = read_graph_trace(path)
        expected = {
            "decode_steps": 3,
            "active_row_steps": 30,
            "padded_row_steps": 2,
            "graph_transitions": 1,
            "raw_bs": 11,
            "padded_bs": 12,
            "last_padded_bs": 12,
        }
        return {"passed": observed == expected, "observed": observed}


def measure_sort(requests: list[RequestState], attained: bool) -> dict[str, int]:
    iterations = 20_000
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        order_offline(requests, attained_service=attained)
        samples.append(time.perf_counter_ns() - started)
    tracemalloc.start()
    order_offline(requests, attained_service=attained)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "iterations": iterations,
        "median_ns": int(statistics.median(samples)),
        "p95_ns_nearest_rank": int(nearest_rank(samples, 0.95)),
        "max_ns": max(samples),
        "single_call_local_tracemalloc_peak_bytes": peak,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    args = parser.parse_args()
    (ROOT / "artifacts").mkdir(exist_ok=True)

    direct = {
        "project": PROJECT,
        "campaign": CAMPAIGN,
        "decode_terminal": DECODE_TERMINAL,
        "prefix_terminal": PREFIX_TERMINAL,
        "prefix_runner": PREFIX_RUNNER,
        "workload": WORKLOAD,
        "bound_runner": BOUND_RUNNER,
        "config": CONFIG,
        "qualified_terminal": QUALIFIED_TERMINAL,
        "server_stderr": SERVER_STDERR,
        **SOURCE_FILES,
    }
    observed_hashes = {name: sha256(path) for name, path in direct.items()}
    for name, expected in EXPECTED.items():
        if observed_hashes[name] != expected:
            raise RuntimeError(
                f"{name} binding mismatch: {observed_hashes[name]} != {expected}"
            )

    workload = json.loads(WORKLOAD.read_text())
    prefix_terminal = json.loads(PREFIX_TERMINAL.read_text())
    qualified = json.loads(QUALIFIED_TERMINAL.read_text())
    config = json.loads(CONFIG.read_text())["text_config"]
    if request_hashes() != workload["request_sha256"]:
        raise RuntimeError("exact request hash reconstruction failed")
    arrivals = prefix_terminal["replay"]["offered_work"]["arrival_ns"]
    if arrivals != [0] * workload["concurrency"]:
        raise RuntimeError("exact offered arrivals are not simultaneous")
    if qualified["service_seconds_per_request"] != QUALIFIED_SECONDS_PER_REQUEST:
        raise RuntimeError("qualified denominator mismatch")
    if any(
        row["completion_tokens"] != workload["output_tokens"]
        for row in qualified["rows"]
    ):
        raise RuntimeError("qualified completion work mismatch")

    requests = [
        RequestState(
            request_id=workload["request_sha256"][index],
            arrival_ordinal=index,
            arrival_ns=arrivals[index],
            prompt_tokens=workload["prompt_tokens"],
            attained_output_tokens=0,
        )
        for index in range(workload["concurrency"])
    ]
    fifo = order_offline(requests, attained_service=False)
    candidate = order_offline(requests, attained_service=True)
    fifo_order = [request.arrival_ordinal for request in fifo]
    candidate_order = [request.arrival_ordinal for request in candidate]
    fifo_parity = fifo_order == candidate_order == list(range(32))

    buckets = graph_buckets()
    padding = {
        str(raw): next(bucket for bucket in buckets if bucket >= raw) - raw
        for raw in range(1, workload["concurrency"] + 1)
    }
    maximum_padding = max(padding.values())
    active_row_steps = workload["concurrency"] * workload["output_tokens"]
    padded_upper = active_row_steps // 9 if maximum_padding == 1 else active_row_steps
    rows = qualified["rows"]
    wall = [row["wall_seconds"] for row in rows]
    completion_order = [
        row["index"] for row in sorted(rows, key=lambda row: row["ended_monotonic_s"])
    ]
    candidate_hash = sha256(ROOT / "attained_service_graph_batching.py")
    source_validation = stage_source(candidate_hash)
    observer_validation = observer_test()
    if not fifo_parity or not observer_validation["passed"]:
        raise RuntimeError("offline policy or observer validation failed")
    if not all(source_validation["claims"].values()):
        raise RuntimeError("staged source-completeness validation failed")

    local_cpu = {
        "fifo_exact_comparator": measure_sort(requests, False),
        "attained_service": measure_sort(requests, True),
        "evidence_label": (
            "measured on coordinator CPython; diagnostic only, not transferable "
            "to H200 scheduler latency"
        ),
    }

    local_layers = config["layer_types"].count("sliding_attention")
    global_layers = config["layer_types"].count("full_attention")
    local_bytes_per_position = (
        local_layers
        * 2
        * config["num_key_value_heads"]
        * config["head_dim"]
    )
    global_bytes_per_position = (
        global_layers
        * 2
        * config["num_global_key_value_heads"]
        * config["global_head_dim"]
    )
    shared = workload["shared_prefix_tokens"]
    unique_prompt = workload["prompt_tokens"] - shared
    local_positions = (
        workload["concurrency"]
        * min(
            config["sliding_window"],
            workload["prompt_tokens"] + workload["output_tokens"],
        )
    )
    global_positions_upper = shared + workload["concurrency"] * (
        unique_prompt + workload["output_tokens"]
    )
    kv_bytes_upper = (
        local_positions * local_bytes_per_position
        + global_positions_upper * global_bytes_per_position
    )
    qualified_cost = (
        TARGET_COST_PER_MILLION
        * QUALIFIED_SECONDS_PER_REQUEST
        / TARGET_SECONDS_PER_REQUEST
    )

    result = {
        "schema_version": 1,
        "kind": "attained_service_graph_batching_offline_terminal",
        "project": "gemma4_attained_service_graph_batching",
        "classification": (
            "typed_negative_simultaneous_homogeneous_c32_fifo_parity_"
            "no_causal_graph_change"
        ),
        "pass": True,
        "answer": (
            "No. All 32 exact requests are released simultaneously, have equal "
            "prompt lengths, begin with zero attained output service, and are "
            "forced to exactly 358 output tokens. Least-attained-service order "
            "therefore equals FIFO at every distinguishing input; it cannot "
            "change the real raw batch-size path, graph padding, or transitions."
        ),
        "direct_inputs": {
            name: manifest(path) for name, path in direct.items()
        },
        "scope": {
            "model": (
                "google/gemma-4-31B-it@"
                "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
            ),
            "runtime": "SGLang v0.5.13",
            "sglang_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "target_gpu": "NVIDIA H200 SXM",
            "gpu_claimed_or_used": False,
            "ssh_provider_or_endpoint_used": False,
            "checkpoint_shards_read": False,
            "policy_sweep": False,
            "actual_spend_usd": 0.0,
        },
        "policy": {
            "name": "least_attained_service_stable_fifo_v1",
            "one_policy_only": True,
            "key": [
                "tokens_already_generated ascending",
                "scheduler receive time ascending",
                "request ID ascending",
            ],
            "selection_boundary": (
                "SchedulePolicy.calc_priority mutates Scheduler.waiting_queue "
                "before PrefillAdder selects can_run_list."
            ),
            "semantics": (
                "Only ready-queue order changes; prompts, sampling, token work, "
                "KV ownership, deadlines, completion filtering, and active "
                "running requests are unchanged."
            ),
        },
        "fifo_comparator": {
            "name": "stock_fcfs",
            "key": [
                "arrival time ascending",
                "arrival ordinal ascending",
                "request ID ascending",
            ],
            "identical_constraints": {
                "arrivals": True,
                "prompt_and_output_tokens": True,
                "max_running_requests_32": True,
                "kv_capacity_and_page_size": True,
                "deadlines_and_no_added_wait": True,
                "graph_buckets": True,
            },
            "candidate_order": candidate_order,
            "fifo_order": fifo_order,
            "parity": fifo_parity,
        },
        "observability_contract": {
            "policy_reads": [
                "len(Req.output_ids)",
                "Req.time_stats.scheduler_recv_time",
                "Req.rid only as a deterministic final tie-break",
            ],
            "available_but_unused": [
                "prompt length",
                "request age",
                "completion events",
                "current resident batch",
            ],
            "forbidden_and_absent": [
                "future realized output length",
                "future arrivals",
                "hidden oracle labels",
                "synthetic prefixes",
            ],
            "graph_trace": {
                "enabled_only_by_env": (
                    "SGLANG_ATTAINED_SERVICE_GRAPH_TRACE=<absolute path>"
                ),
                "consumer": (
                    "CudaGraphRunner.replay_prepare after bisect_left chooses bs "
                    "and before buffer_registry.fill_from pads rows"
                ),
                "fixed_record_bytes": 64,
                "fields": [
                    "decode steps",
                    "active row-steps",
                    "padded row-steps",
                    "graph-bucket transitions",
                    "last raw and padded batch sizes",
                ],
                "observer_validation": observer_validation,
            },
        },
        "source_and_consumer_ownership": {
            "scheduler_ready_queue": (
                "Scheduler owns arrival and waiting_queue lifetime; the candidate "
                "only provides a deterministic stable key."
            ),
            "capacity_deadlines_and_kv": (
                "PrefillAdder and existing allocators remain sole owners; the "
                "candidate cannot admit a request that stock capacity rejects."
            ),
            "resident_batch": (
                "ScheduleBatch merge/filter owns membership and completion; "
                "active resident requests are never skipped or delayed."
            ),
            "first_graph_shape_consumer": (
                "CudaGraphRunner.replay_prepare reads ForwardBatch.batch_size as "
                "raw_bs and selects the first capture_bs >= raw_bs."
            ),
            "observer": (
                "The observer records the already-selected raw/padded shape and "
                "cannot change graph selection, buffers, synchronization, or KV."
            ),
            "source_complete": True,
            "staged_validation": source_validation,
        },
        "exact_trace": {
            "requests": workload["concurrency"],
            "arrival_ns": arrivals,
            "all_arrivals_simultaneous": True,
            "prompt_tokens_per_request": workload["prompt_tokens"],
            "completion_tokens_per_request": workload["output_tokens"],
            "all_completions_forced_by_length": True,
            "compulsory_prompt_tokens": (
                workload["concurrency"] * workload["prompt_tokens"]
            ),
            "compulsory_output_row_steps": active_row_steps,
            "admission_order": fifo_order,
            "completion_order_measured": completion_order,
            "queue_delay_seconds": {
                "fifo": [0.0] * workload["concurrency"],
                "candidate": [0.0] * workload["concurrency"],
            },
        },
        "graph_work": {
            "current_runtime_capture_bs": buckets,
            "raw_bs_to_inactive_padding": padding,
            "maximum_padding_per_decode_graph_step": maximum_padding,
            "fifo": {
                "active_output_row_steps": active_row_steps,
                "padded_inactive_row_steps_bound": [0, padded_upper],
                "graph_bucket_transitions_bound": [0, active_row_steps - 1],
            },
            "candidate": {
                "active_output_row_steps": active_row_steps,
                "padded_inactive_row_steps_bound": [0, padded_upper],
                "graph_bucket_transitions_bound": [0, active_row_steps - 1],
            },
            "causal_delta": {
                "active_output_row_steps": 0,
                "padded_inactive_row_steps": 0,
                "graph_bucket_transitions": 0,
                "scheduler_or_graph_operations_removed": 0,
            },
            "absolute_counter_status": (
                "The qualified terminal lacks per-forward raw_bs telemetry, so "
                "absolute padding and transition counts are bounded, not invented. "
                "Exact zero candidate-minus-FIFO deltas follow from input symmetry."
            ),
        },
        "scheduler_cpu_work": {
            "exact_offered_work_decisions": 1,
            "stock_fifo_sort_invocations": 0,
            "candidate_sort_invocations": 1,
            "candidate_key_evaluations": workload["concurrency"],
            "candidate_timsort_comparison_bound": [
                workload["concurrency"] - 1,
                workload["concurrency"]
                * math.ceil(math.log2(workload["concurrency"])),
            ],
            "scheduler_operations_removed": 0,
            "net_effect": (
                "strictly nonnegative added host work; no device task, graph "
                "selection, allocator action, or synchronization is removed"
            ),
        },
        "latency_bounds": {
            "qualified_fifo_batch_seconds": qualified["batch_seconds"],
            "qualified_fifo_service_seconds_per_request": (
                QUALIFIED_SECONDS_PER_REQUEST
            ),
            "fifo_end_to_end_seconds": {
                "p50_nearest_rank": nearest_rank(wall, 0.50),
                "p95_nearest_rank": nearest_rank(wall, 0.95),
                "max": max(wall),
            },
            "candidate_queue_delay_delta_seconds": 0.0,
            "candidate_model_and_graph_time_reduction_seconds": 0.0,
            "candidate_service_seconds_per_request_lower_bound": (
                QUALIFIED_SECONDS_PER_REQUEST
            ),
            "candidate_current_runtime_upper_bound": {
                "type": "unknown_without_execution",
                "reason": (
                    "The policy adds a nonnegative host sort and this zero-GPU "
                    "lane cannot measure its current-runtime wall-time."
                ),
            },
            "complete_candidate_minus_fifo_interval_seconds_per_request": {
                "lower": 0.0,
                "upper": None,
                "upper_type": "unknown_current_runtime_host_sort",
                "gpu_and_graph_component_delta": 0.0,
            },
            "local_scheduler_cpu_diagnostic": local_cpu,
            "dependent_synchronization_counted_as_saved": False,
        },
        "memory_bounds": {
            "kv_cache_dtype": "fp8_e5m2",
            "local_layers": local_layers,
            "global_layers": global_layers,
            "local_kv_bytes_per_position": local_bytes_per_position,
            "global_kv_bytes_per_position": global_bytes_per_position,
            "local_resident_positions_upper": local_positions,
            "global_unique_resident_positions_upper": global_positions_upper,
            "fifo_kv_bytes_upper": kv_bytes_upper,
            "candidate_kv_bytes_upper": kv_bytes_upper,
            "candidate_minus_fifo_kv_bytes": 0,
            "candidate_additional_device_bytes": 0,
            "candidate_persistent_host_bytes_per_request": 0,
            "candidate_sort_temporary_host_bytes_upper": 4096,
            "optional_trace_mapping_bytes": 4096,
            "candidate_total_additional_host_bytes_upper_with_trace": 8192,
            "sort_temporary_entries_upper": workload["concurrency"],
            "note": (
                "KV upper bound applies the exact 1,024-token local window and "
                "one physical 535-token global prefix; FP8 scale metadata and "
                "allocator fragmentation are unchanged and therefore zero delta."
            ),
        },
        "cost_bounds": {
            "actual_experiment_spend_usd": 0.0,
            "qualified_90pct_planning_cost_usd_per_million_total_tokens_derived": (
                qualified_cost
            ),
            "candidate_best_case_cost_usd_per_million_total_tokens": qualified_cost,
            "candidate_cost_reduction_fraction_upper_bound": 0.0,
            "candidate_cost_reduction_fraction_lower_bound": {
                "type": "non_positive_unmeasured_cpu_overhead",
                "reason": "The candidate removes no GPU work and adds host ordering.",
            },
            "target_usd_per_million_total_tokens": TARGET_COST_PER_MILLION,
            "target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
            "target_reached": False,
        },
        "physical_mechanism": {
            "hypothesis": (
                "Blind least-attained-service ordering could alter which queued "
                "request enters a capacity-limited resident batch, changing later "
                "completion clustering and graph buckets without a length oracle."
            ),
            "falsifier_observed": (
                "At the exact decision all 32 requests are ready, capacity is 32, "
                "attained service is zero for every request, and all compulsory "
                "prompt/output lengths are equal. The candidate has no distinct "
                "selection and therefore no physical graph mechanism on this trace."
            ),
        },
        "exact_runtime_h200_consumer": {
            "type": "none",
            "command": None,
            "reason": (
                "Exact offline symmetry proves zero causal graph-work delta; the "
                "project has zero spend authority and explicitly forbids a GPU "
                "claim, SSH, provider, or endpoint invocation."
            ),
        },
        "decision": {
            "positive_result": False,
            "portfolio_change": "close_observable_attained_service_for_exact_c32",
            "reason": (
                "Queue rearrangement is exactly FIFO and removes no padding, graph "
                "transition, scheduler operation, compulsory token work, or cost."
            ),
        },
        "reproduce_command": (
            "python3 research/lab/experiments/gemma4_31b/research_lab/projects/"
            "gemma4_attained_service_graph_batching/run_attained_service_offline.py"
        ),
    }
    atomic(args.output, result)
    print(json.dumps({"output": str(args.output), "classification": result["classification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
