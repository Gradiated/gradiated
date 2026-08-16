#!/usr/bin/env python3
"""Exact-workload offline MI355X c64/c96 background-batching discriminator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
from collections import Counter, deque
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR.parent.parent
WORKSPACE = next(parent for parent in PROJECT_DIR.parents if parent.name == "workspace")
PARENT_DIR = PROJECT_DIR.parent / "gemma4_mi355x_fp8_runtime_codesign"
PARENT_SCREEN = PARENT_DIR / "MI355X_FP8_RUNTIME_SCREEN.json"
BINDINGS_PATH = PROJECT_DIR / "SOURCE_BINDINGS.json"
DEFAULT_OUTPUT = PROJECT_DIR / "MI355X_BACKGROUND_BATCHING_SCREEN.json"

MODEL_ID = "google/gemma-4-31B-it"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
VLLM_COMMIT = "0164022c907014a27e81c514cd4dff6091904c2b"

PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
TOTAL_TOKENS = PROMPT_TOKENS + OUTPUT_TOKENS
FRESH_PROMPT_TOKENS = 3678.822
CACHE_FRACTION = 0.127
COHORT_WIDTH = 32
TARGET_DEPTH = 12
TARGET_CYCLES = 15
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
QUEUE_P95_GATE_SECONDS = 10.0
COMPLETION_P95_GATE_SECONDS = 90.0
SELECTED_WIDTH = 96
OFFERED_REQUESTS_PER_SECOND = 2.0
FALLBACK_TIMEOUT_SECONDS = 10.0
SIMULATION_COHORTS = 30_000
SIMULATION_BURN_COHORTS = 3_000

TRANSFORMER_PARAMETERS = 29_396_828_160
TIED_HEAD_PARAMETERS = 1_409_286_144
FP8_PEAK_FLOPS = 5_000e12
BF16_PEAK_FLOPS = 2_500e12
MATH_EFFICIENCY = 0.20
HBM_BANDWIDTH_BYTES_PER_SECOND = 8_000e9
HBM_EFFICIENCY = 0.30
EFFECTIVE_HBM_BYTES_PER_SECOND = (
    HBM_BANDWIDTH_BYTES_PER_SECOND * HBM_EFFICIENCY
)
LAUNCH_SECONDS = 3e-6
KERNELS_PER_LAYER = 18
LAYERS = 60

SOURCE_ASSERTIONS = {
    "vllm/config/scheduler.py": [
        'policy: SchedulerPolicy = "fcfs"',
        "scheduler_cls: str | type[object] | None = None",
        "return resolve_obj_by_qualname(self.scheduler_cls)",
        "max_num_seqs: int = Field(",
        "enable_chunked_prefill: bool = True",
    ],
    "vllm/v1/core/sched/scheduler.py": [
        "self.max_num_running_reqs = self.scheduler_config.max_num_seqs",
        "self.waiting = create_request_queue(self.policy)",
        "# First, schedule the RUNNING requests.",
        "# Next, schedule the WAITING requests.",
        "num_scheduled_tokens[request_id] = num_new_tokens",
    ],
    "vllm/v1/worker/gpu_model_runner.py": [
        "def _is_uniform_decode(",
        "num_tokens == max_num_scheduled_tokens * num_reqs",
        "num_tokens_padded = self._pad_for_sequence_parallelism(num_tokens)",
        "num_tokens_padded = batch_descriptor.num_tokens",
        "tokens = [scheduler_output.num_scheduled_tokens[i] for i in req_ids]",
    ],
    "vllm/config/compilation.py": [
        "[1, 2, 4] + list(range(8, 256, 8))",
        "FULL_DECODE_ONLY mode: Capture full cudagraph for decode batches only.",
        "Mixed prefill-decode batches are run without cudagraphs.",
    ],
    "vllm/v1/worker/gpu_worker.py": [
        "if not self.model_config.enforce_eager:",
        "self.scheduler_config.max_num_seqs",
        "self.scheduler_config.max_num_batched_tokens",
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def fetch_vllm(destination: Path, bindings: dict[str, Any]) -> None:
    repo = bindings["repositories"]["vllm"]
    subprocess.run(["git", "init", "-q", str(destination)], check=True)
    subprocess.run(
        ["git", "-C", str(destination), "remote", "add", "origin", repo["url"]],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(destination),
            "-c",
            "protocol.version=2",
            "fetch",
            "--depth",
            "1",
            "--filter=blob:none",
            "origin",
            repo["commit"],
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(destination), "sparse-checkout", "init", "--no-cone"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(destination), "sparse-checkout", "set", "--stdin"],
        input="\n".join(f"/{path}" for path in repo["files"]) + "\n",
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "-q", "--detach", "FETCH_HEAD"],
        check=True,
    )


def verify_sources(
    bindings: dict[str, Any], vllm_root: Path
) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    observed_commit = subprocess.check_output(
        ["git", "-C", str(vllm_root), "rev-parse", "HEAD"], text=True
    ).strip()
    checks["vllm_commit"] = {
        "expected": VLLM_COMMIT,
        "observed": observed_commit,
        "pass": observed_commit == VLLM_COMMIT,
    }
    for relative, expected in bindings["repositories"]["vllm"]["files"].items():
        path = vllm_root / relative
        observed = sha256(path) if path.is_file() else None
        checks[f"sha256:{relative}"] = {
            "expected": expected,
            "observed": observed,
            "pass": observed == expected,
        }
        text = path.read_text(errors="replace") if path.is_file() else ""
        missing = [
            fragment
            for fragment in SOURCE_ASSERTIONS.get(relative, [])
            if fragment not in text
        ]
        checks[f"contract:{relative}"] = {
            "missing_fragments": missing,
            "pass": not missing,
            "required_fragments": SOURCE_ASSERTIONS.get(relative, []),
        }
    failures = [name for name, row in checks.items() if not row["pass"]]
    if failures:
        raise RuntimeError(f"source verification failed: {failures}")
    return checks


def line_items_for_width(
    width: int, parent_rows: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    prefill_chunks = math.ceil(width * FRESH_PROMPT_TOKENS / 8192)
    prefill_weight_bytes = TRANSFORMER_PARAMETERS * prefill_chunks / width
    prefill_compute_seconds = parent_rows["prefill_fp8_transformer_linears"][
        "seconds_per_request"
    ]
    prefill_weight_seconds = prefill_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND

    decode_transformer_flops = (
        2 * TRANSFORMER_PARAMETERS * OUTPUT_TOKENS
    )
    decode_transformer_weight_bytes = (
        TRANSFORMER_PARAMETERS * OUTPUT_TOKENS / width
    )
    decode_transformer_compute_seconds = decode_transformer_flops / (
        FP8_PEAK_FLOPS * MATH_EFFICIENCY
    )
    decode_transformer_weight_seconds = (
        decode_transformer_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND
    )

    decode_head_flops = 2 * TIED_HEAD_PARAMETERS * OUTPUT_TOKENS
    decode_head_weight_bytes = 2 * TIED_HEAD_PARAMETERS * OUTPUT_TOKENS / width
    decode_head_compute_seconds = decode_head_flops / (
        BF16_PEAK_FLOPS * MATH_EFFICIENCY
    )
    decode_head_weight_seconds = (
        decode_head_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND
    )

    verify_transformer_flops = (
        TARGET_CYCLES * TARGET_DEPTH * 2 * TRANSFORMER_PARAMETERS
    )
    verify_transformer_weight_bytes = (
        TARGET_CYCLES * TRANSFORMER_PARAMETERS / width
    )
    verify_transformer_compute_seconds = verify_transformer_flops / (
        FP8_PEAK_FLOPS * MATH_EFFICIENCY
    )
    verify_transformer_weight_seconds = (
        verify_transformer_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND
    )

    verify_head_flops = TARGET_CYCLES * TARGET_DEPTH * 2 * TIED_HEAD_PARAMETERS
    verify_head_weight_bytes = (
        TARGET_CYCLES * TARGET_DEPTH * 2 * TIED_HEAD_PARAMETERS / width
    )
    verify_head_compute_seconds = verify_head_flops / (
        BF16_PEAK_FLOPS * MATH_EFFICIENCY
    )
    verify_head_weight_seconds = (
        verify_head_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND
    )

    launch_count = (
        prefill_chunks * LAYERS * KERNELS_PER_LAYER / width
        + OUTPUT_TOKENS * LAYERS * KERNELS_PER_LAYER / width
        + TARGET_CYCLES * (LAYERS * KERNELS_PER_LAYER + TARGET_DEPTH) / width
    )

    copied_names = [
        "prefill_hybrid_attention",
        "prefill_norm_activation_conversion",
        "ordinary_decode_attention_kv",
        "ordinary_decode_norm_activation_conversion",
        "target_verification_attention_kv",
        "scheduler_service_reserve",
    ]
    copied = [dict(parent_rows[name]) for name in copied_names]
    rows = [
        {
            "compute_seconds_per_request": prefill_compute_seconds,
            "name": "prefill_fp8_transformer_linears",
            "resource": "max_fp8_tensor_or_compulsory_weight_hbm",
            "seconds_per_request": max(
                prefill_compute_seconds, prefill_weight_seconds
            ),
            "weight_bytes_per_request": prefill_weight_bytes,
            "weight_seconds_per_request": prefill_weight_seconds,
            "rule": "Exact fresh-token FLOPs at settled 20% FP8 efficiency versus one 29.397-GB stream per 8,192-token chunk; charge the maximum.",
        },
        copied[0],
        copied[1],
        {
            "compute_flops_per_request": decode_transformer_flops,
            "compute_seconds_per_request": decode_transformer_compute_seconds,
            "name": "ordinary_decode_fp8_transformer_linears",
            "resource": "max_fp8_tensor_or_weight_hbm",
            "seconds_per_request": max(
                decode_transformer_compute_seconds,
                decode_transformer_weight_seconds,
            ),
            "weight_bytes_per_request": decode_transformer_weight_bytes,
            "weight_seconds_per_request": decode_transformer_weight_seconds,
            "rule": "One exact FP8 transformer stream per width-wide decode step, zero L2 credit, versus exact FLOPs at settled 20% FP8 efficiency.",
        },
        {
            "compute_flops_per_request": decode_head_flops,
            "compute_seconds_per_request": decode_head_compute_seconds,
            "name": "ordinary_decode_bf16_tied_head",
            "resource": "max_bf16_tensor_or_weight_hbm",
            "seconds_per_request": max(
                decode_head_compute_seconds, decode_head_weight_seconds
            ),
            "weight_bytes_per_request": decode_head_weight_bytes,
            "weight_seconds_per_request": decode_head_weight_seconds,
            "rule": "One exact BF16 tied-head stream per width-wide decode step versus exact FLOPs at settled 20% BF16 efficiency.",
        },
        copied[2],
        copied[3],
        {
            "compute_flops_per_request": verify_transformer_flops,
            "compute_seconds_per_request": verify_transformer_compute_seconds,
            "m": width * TARGET_DEPTH,
            "name": "target_verification_transformer",
            "resource": "max_fp8_tensor_or_weight_hbm",
            "seconds_per_request": max(
                verify_transformer_compute_seconds,
                verify_transformer_weight_seconds,
            ),
            "target_cycles": TARGET_CYCLES,
            "weight_bytes_per_request": verify_transformer_weight_bytes,
            "weight_seconds_per_request": verify_transformer_weight_seconds,
            "rule": "Preserve all 15 conservative target cycles and 12 rows/request; exact FLOPs at 20% FP8 versus one transformer stream per cycle.",
        },
        {
            "compute_flops_per_request": verify_head_flops,
            "compute_seconds_per_request": verify_head_compute_seconds,
            "name": "target_verification_bf16_tied_head",
            "resource": "max_bf16_tensor_or_repeated_weight_hbm",
            "seconds_per_request": max(
                verify_head_compute_seconds, verify_head_weight_seconds
            ),
            "weight_bytes_per_request": verify_head_weight_bytes,
            "weight_seconds_per_request": verify_head_weight_seconds,
            "rule": "Preserve 12 semantic BF16 head calls per cycle; no grouped-head reuse credit.",
        },
        copied[4],
        {
            "launch_count_per_request": launch_count,
            "microseconds_per_launch": LAUNCH_SECONDS * 1e6,
            "name": "launch_reserve",
            "resource": "device_launch_latency",
            "seconds_per_request": launch_count * LAUNCH_SECONDS,
            "rule": "18 launches/layer plus target-head calls; eager/no graph-elision credit makes token padding exactly zero.",
        },
        copied[5],
    ]
    return rows


def width_screen(
    width: int, parent_rows: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    rows = line_items_for_width(width, parent_rows)
    seconds = sum(row["seconds_per_request"] for row in rows)
    m_tiles = math.ceil(width / 128)
    return {
        "full_width_batch_seconds": width * seconds,
        "full_width_service_seconds_per_request": seconds,
        "line_items": rows,
        "ordinary_decode_m": width,
        "ordinary_decode_m_tiles_at_128": m_tiles,
        "pass_economic_service_gate": seconds <= TARGET_SECONDS_PER_REQUEST,
        "target_verification_m": width * TARGET_DEPTH,
        "width": width,
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def simulate_timeout_policy(
    service_seconds: dict[int, float],
    *,
    offered_requests_per_second: float,
    cohorts: int,
    burn_cohorts: int,
) -> dict[str, Any]:
    interval = COHORT_WIDTH / offered_requests_per_second
    arrivals = [index * interval for index in range(cohorts)]
    waiting: deque[tuple[int, float]] = deque()
    next_arrival = 0
    now = 0.0
    completed: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []

    while next_arrival < cohorts or waiting:
        while next_arrival < cohorts and arrivals[next_arrival] <= now + 1e-12:
            waiting.append((next_arrival, arrivals[next_arrival]))
            next_arrival += 1
        if not waiting:
            now = arrivals[next_arrival]
            continue

        if len(waiting) >= SELECTED_WIDTH // COHORT_WIDTH:
            width = SELECTED_WIDTH
            cohort_count = SELECTED_WIDTH // COHORT_WIDTH
        elif now - waiting[0][1] >= FALLBACK_TIMEOUT_SECONDS - 1e-12:
            width = COHORT_WIDTH
            cohort_count = 1
        else:
            next_time = waiting[0][1] + FALLBACK_TIMEOUT_SECONDS
            if next_arrival < cohorts:
                next_time = min(next_time, arrivals[next_arrival])
            now = next_time
            continue

        selected = [waiting.popleft() for _ in range(cohort_count)]
        started = now
        finished = started + width * service_seconds[width]
        batches.append(
            {
                "cohort_ids": [cohort_id for cohort_id, _ in selected],
                "finished_seconds": finished,
                "started_seconds": started,
                "width": width,
            }
        )
        for cohort_id, arrival in selected:
            completed.append(
                {
                    "cohort_id": cohort_id,
                    "completion_seconds": finished - arrival,
                    "queue_seconds": started - arrival,
                    "width": width,
                }
            )
        now = finished

    lower = burn_cohorts
    upper = cohorts - burn_cohorts
    measured = [
        row for row in completed if lower <= row["cohort_id"] < upper
    ]
    counts = Counter(row["width"] for row in measured)
    measured_requests = len(measured) * COHORT_WIDTH
    fallback_requests = counts[COHORT_WIDTH] * COHORT_WIDTH
    selected_requests = counts[SELECTED_WIDTH] * COHORT_WIDTH
    weighted_service = (
        fallback_requests * service_seconds[COHORT_WIDTH]
        + selected_requests * service_seconds[SELECTED_WIDTH]
    ) / measured_requests
    queue_values = [row["queue_seconds"] for row in measured]
    completion_values = [row["completion_seconds"] for row in measured]
    return {
        "arrival_cohort_interval_seconds": interval,
        "arrival_cohorts": cohorts,
        "arrival_requests": cohorts * COHORT_WIDTH,
        "all_requests_and_tokens_preserved": (
            len(completed) == cohorts
            and sum(row["width"] // COHORT_WIDTH for row in batches) == cohorts
        ),
        "batch_count_by_width": {
            str(width): sum(batch["width"] == width for batch in batches)
            for width in sorted(service_seconds)
        },
        "completion_p50_seconds": percentile(completion_values, 0.50),
        "completion_p95_seconds": percentile(completion_values, 0.95),
        "completion_p95_gate_pass": (
            percentile(completion_values, 0.95)
            <= COMPLETION_P95_GATE_SECONDS
        ),
        "evaluated_requests": measured_requests,
        "fallback_request_fraction": fallback_requests / measured_requests,
        "fill_and_idle_seconds_per_request": max(
            0.0,
            1 / offered_requests_per_second - weighted_service,
        ),
        "offered_requests_per_second": offered_requests_per_second,
        "output_tokens_preserved": cohorts * COHORT_WIDTH * OUTPUT_TOKENS,
        "prompt_tokens_preserved": cohorts * COHORT_WIDTH * PROMPT_TOKENS,
        "queue_p50_seconds": percentile(queue_values, 0.50),
        "queue_p95_seconds": percentile(queue_values, 0.95),
        "queue_p95_gate_pass": (
            percentile(queue_values, 0.95) <= QUEUE_P95_GATE_SECONDS
        ),
        "selected_width_request_fraction": selected_requests / measured_requests,
        "steady_arrival_accounted_seconds_per_request": (
            1 / offered_requests_per_second
        ),
        "weighted_service_seconds_per_request": weighted_service,
        "warmup_and_drain_cohorts_excluded_per_side": burn_cohorts,
    }


def memory_screen(parent: dict[str, Any], width: int) -> dict[str, Any]:
    memory = parent["memory_and_topology"]
    static_bytes = memory["online_fp8_static_model_bytes_upper_bound"]
    kv_bytes = memory["fp8_resident_kv_c32_bytes"] * width // COHORT_WIDTH
    target_extra = (
        memory["target_depth_12_extra_fp8_kv_bytes"] * width // COHORT_WIDTH
    )
    source_bound = static_bytes + kv_bytes + target_extra
    envelope = 2 * source_bound
    capacity = memory["mi355x_decimal_capacity_bytes"]
    return {
        "conservative_two_x_runtime_fragmentation_envelope_bytes": envelope,
        "fits_with_two_x_envelope": envelope <= capacity,
        "fp8_resident_kv_bytes": kv_bytes,
        "mi355x_decimal_capacity_bytes": capacity,
        "online_fp8_static_model_bytes_upper_bound": static_bytes,
        "source_bound_resident_bytes": source_bound,
        "target_depth_12_extra_fp8_kv_bytes": target_extra,
        "two_x_envelope_margin_bytes": capacity - envelope,
    }


def build_artifact(
    parent: dict[str, Any],
    bindings: dict[str, Any],
    source_checks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if sha256(PARENT_SCREEN) != bindings["parent_screen"]["sha256"]:
        raise RuntimeError("parent screen hash mismatch")
    scope = parent["scope"]
    if (
        scope["model"] != MODEL_ID
        or scope["revision"] != MODEL_REVISION
        or scope["workload"]["prompt_tokens"] != PROMPT_TOKENS
        or scope["workload"]["output_tokens"] != OUTPUT_TOKENS
        or scope["workload"]["cache_fraction"] != CACHE_FRACTION
        or scope["workload"]["concurrency"] != COHORT_WIDTH
    ):
        raise RuntimeError("parent workload identity mismatch")

    parent_rows = {
        row["name"]: row for row in parent["physical_cost_screen"]["line_items"]
    }
    width32 = width_screen(32, parent_rows)
    width64 = width_screen(64, parent_rows)
    width96 = width_screen(96, parent_rows)
    parent_seconds = parent["physical_cost_screen"][
        "conservative_screen_seconds_per_request"
    ]
    if not math.isclose(
        width32["full_width_service_seconds_per_request"],
        parent_seconds,
        rel_tol=0,
        abs_tol=1e-15,
    ):
        raise RuntimeError("c32 cost reproduction failed")
    if width64["pass_economic_service_gate"]:
        raise RuntimeError("c64 unexpectedly passes preselection")
    if not width96["pass_economic_service_gate"]:
        raise RuntimeError("c96 unexpectedly fails preselection")

    service_seconds = {
        32: width32["full_width_service_seconds_per_request"],
        96: width96["full_width_service_seconds_per_request"],
    }
    simulation = simulate_timeout_policy(
        service_seconds,
        offered_requests_per_second=OFFERED_REQUESTS_PER_SECOND,
        cohorts=SIMULATION_COHORTS,
        burn_cohorts=SIMULATION_BURN_COHORTS,
    )
    memory = memory_screen(parent, SELECTED_WIDTH)

    maximum_c96_throughput = 1 / service_seconds[96]
    minimum_rate_for_queue_gate = (
        (SELECTED_WIDTH - COHORT_WIDTH) / QUEUE_P95_GATE_SECONDS
    )
    no_fallback_queue_lower_bound = (
        (SELECTED_WIDTH - COHORT_WIDTH) / maximum_c96_throughput
    )
    economic_gate = (
        simulation["steady_arrival_accounted_seconds_per_request"]
        <= TARGET_SECONDS_PER_REQUEST
    )
    terminal = "typed_none"
    reasons = [
        "c64 full-width service cost exceeds the locked target before fill, queue, fallback, or policy overhead.",
        "c96 is the only full-width economic preselection, but its 6.4 req/s minimum fill rate for a 10-second oldest-cohort wait exceeds its 2.126 req/s maximum service capacity.",
        "At the finite 2.0 req/s planning point, the exact timeout policy charges c32 fallback and reaches the economic and completion gates, but queue p95 exceeds 10 seconds.",
    ]
    return {
        "charged_cost_categories": {
            "attention": True,
            "compute": True,
            "fallback": True,
            "fill": True,
            "kv_read_write_and_capacity": True,
            "launch": True,
            "memory": True,
            "padding_and_sequence_divergence": True,
            "queue": True,
            "scheduler_and_service": True,
            "weights_fp8_and_bf16": True,
        },
        "classification": terminal,
        "decision": {
            "completion_p95_gate_pass": simulation[
                "completion_p95_gate_pass"
            ],
            "economic_gate_pass_at_stated_load": economic_gate,
            "memory_gate_pass": memory["fits_with_two_x_envelope"],
            "queue_p95_gate_pass": simulation["queue_p95_gate_pass"],
            "reasons": reasons,
            "result": terminal,
            "source_binding_pass": all(
                row["pass"] for row in source_checks.values()
            ),
        },
        "generated_from_observation_utc": "2026-07-26T14:16:02Z",
        "identity": {
            "bindings": {
                "path": str(BINDINGS_PATH),
                "sha256": sha256(BINDINGS_PATH),
            },
            "calculator": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256(Path(__file__).resolve()),
            },
            "campaign": {
                "path": str(LAB_DIR / "CAMPAIGN.md"),
                "sha256": sha256(LAB_DIR / "CAMPAIGN.md"),
            },
            "parent_screen": {
                "path": str(PARENT_SCREEN),
                "sha256": sha256(PARENT_SCREEN),
            },
            "project": {
                "path": str(PROJECT_DIR / "PROJECT.md"),
                "sha256": sha256(PROJECT_DIR / "PROJECT.md"),
            },
            "source_checks": source_checks,
        },
        "memory": memory,
        "physical_hypothesis": {
            "falsifier": "The route fails if exact c96 weight/launch amortization cannot coexist with a stable finite arrival rate and queue p95 <=10 seconds.",
            "mechanism": "c64/c96 remain one M-tile for ordinary decode at tile-M 128, so N-grid wave counts do not increase; wider batches amortize one FP8 transformer stream, one BF16 head stream, and launches across more requests while exact compute, KV, attention, and non-GEMM bytes/request remain charged.",
            "resource_expected_to_move": "FP8/BF16 HBM weight bytes and device launches per request.",
        },
        "planning_latency_and_fallback_simulation": simulation,
        "policy": {
            "admission": "FCFS over independent immutable c32 cohorts; dispatch exactly three cohorts as c96 when all are waiting.",
            "drain": "When the oldest waiting c32 cohort reaches 10 seconds without three cohorts present, dispatch that cohort unchanged as c32.",
            "graph_and_padding": "Use enforce_eager for the screen, charge every launch, and execute exact unpadded token rows. Current generated graph sizes include 96, but no graph or padding credit is taken.",
            "implementation_binding": "SchedulerConfig.scheduler_cls resolves a custom class; Scheduler owns FCFS waiting/running queues and max_num_seqs; GPUModelRunner consumes the emitted per-request token map and recognizes an exact uniform decode when total tokens equal query length times requests.",
            "max_num_batched_tokens": 8192,
            "max_num_seqs": SELECTED_WIDTH,
            "prefill_decode_barrier": "The adapter must hold already-prefilled members at the cohort boundary until all 96 prompts complete, because stock Scheduler prioritizes RUNNING before WAITING and otherwise forms mixed prefill/decode steps.",
            "sampling_and_semantics": "Unchanged per-request sampling and output ownership; no request, token, layer, parameter, KV row, attention pair, or head row is shared or dropped.",
            "selected_policy_count": 1,
            "selected_width": SELECTED_WIDTH,
            "source_complete_status": "source_bound_negative; the adapter contract and exact consumer path are complete enough to evaluate, but no runtime patch is promoted because the planning queue gate is physically impossible.",
        },
        "queue_impossibility_bound": {
            "c32_cohort_arrival_interval_at_maximum_c96_throughput_seconds": (
                COHORT_WIDTH / maximum_c96_throughput
            ),
            "maximum_c96_service_throughput_requests_per_second": (
                maximum_c96_throughput
            ),
            "minimum_no_fallback_queue_p95_seconds": (
                no_fallback_queue_lower_bound
            ),
            "minimum_requests_per_second_for_10s_oldest_cohort_fill": (
                minimum_rate_for_queue_gate
            ),
            "proof": "Three c32 cohorts are required. At any stable rate lambda <= c96 capacity, the first cohort waits at least 64/lambda >= 64/capacity; satisfying 64/lambda <=10 requires lambda >=6.4, which is above capacity.",
        },
        "scope": {
            "accelerator": "one AMD Instinct MI355X, TP1",
            "cache_fraction": CACHE_FRACTION,
            "mode": "text_only_non_reasoning",
            "model": MODEL_ID,
            "output_tokens_per_request": OUTPUT_TOKENS,
            "prompt_tokens_per_request": PROMPT_TOKENS,
            "provider_spend_usd": 0.0,
            "revision": MODEL_REVISION,
            "tokens_per_request": TOTAL_TOKENS,
        },
        "semantic_and_padding_accounting": {
            "all_60_layers_preserved": True,
            "all_checkpoint_parameters_preserved": True,
            "all_requests_and_tokens_preserved": simulation[
                "all_requests_and_tokens_preserved"
            ],
            "attention_pairs_per_request": "unchanged exact parent rows",
            "bf16_tied_head_preserved": True,
            "decode_padding_tokens_per_full_or_fallback_batch": 0,
            "feature_and_sampling_semantics_preserved": True,
            "fp8_kv_reads_per_request": "unchanged exact parent rows",
            "fp8_kv_writes": "included within the parent non-GEMM conversion/write byte ledger and resident KV capacity; no write is credited away",
            "sequence_length_divergence_tokens": 0,
        },
        "terminal": terminal,
        "width_preselection": {
            "c64": width64,
            "c96": width96,
            "rule": "Analytically eliminate c64 at the locked economic gate, then select only c96 for the deterministic policy simulation.",
            "selected_width_count": 1,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--vllm-root", type=Path)
    args = parser.parse_args()

    bindings = load_json(BINDINGS_PATH)
    parent = load_json(PARENT_SCREEN)
    if args.vllm_root is not None:
        source_checks = verify_sources(bindings, args.vllm_root)
        artifact = build_artifact(parent, bindings, source_checks)
    else:
        with tempfile.TemporaryDirectory(prefix="mi355x-batching-vllm-") as temp:
            root = Path(temp)
            fetch_vllm(root, bindings)
            source_checks = verify_sources(bindings, root)
            artifact = build_artifact(parent, bindings, source_checks)
    atomic_json(args.output, artifact)
    print(
        json.dumps(
            {
                "classification": artifact["classification"],
                "completion_p95_seconds": artifact[
                    "planning_latency_and_fallback_simulation"
                ]["completion_p95_seconds"],
                "fallback_request_fraction": artifact[
                    "planning_latency_and_fallback_simulation"
                ]["fallback_request_fraction"],
                "output": str(args.output),
                "queue_p95_seconds": artifact[
                    "planning_latency_and_fallback_simulation"
                ]["queue_p95_seconds"],
                "selected_width": SELECTED_WIDTH,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
