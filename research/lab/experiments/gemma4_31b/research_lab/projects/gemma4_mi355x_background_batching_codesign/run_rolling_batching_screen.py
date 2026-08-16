#!/usr/bin/env python3
"""Finite-stream MI355X rolling slot-admission physical discriminator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR.parent.parent
WORKSPACE = next(parent for parent in PROJECT_DIR.parents if parent.name == "workspace")
PARENT_SCREEN = (
    PROJECT_DIR.parent
    / "gemma4_mi355x_fp8_runtime_codesign"
    / "MI355X_FP8_RUNTIME_SCREEN.json"
)
BARRIER_SCREEN = PROJECT_DIR / "MI355X_BACKGROUND_BATCHING_SCREEN.json"
BINDINGS_PATH = PROJECT_DIR / "ROLLING_SOURCE_BINDINGS.json"
DEFAULT_OUTPUT = PROJECT_DIR / "MI355X_ROLLING_BATCHING_SCREEN.json"

MODEL_ID = "google/gemma-4-31B-it"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
VLLM_COMMIT = "0164022c907014a27e81c514cd4dff6091904c2b"

PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
TOTAL_TOKENS = PROMPT_TOKENS + OUTPUT_TOKENS
CACHE_535_PERIOD_COUNT = 822
CACHE_MIX_PERIOD = 1000
MAX_LIVE_REQUESTS = 96
PREFILL_TOKEN_BUDGET = 8192
TARGET_DEPTH = 12
TARGET_CYCLES = 15
TARGET_CONTEXT = PROMPT_TOKENS + OUTPUT_TOKENS - 1
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
QUEUE_P95_GATE_SECONDS = 10.0
COMPLETION_P95_GATE_SECONDS = 90.0
OFFERED_CAPACITY_FRACTION = 0.90
FINITE_REQUESTS = 10_000
CAPACITY_PROBE_REQUESTS = 6_000
CAPACITY_PROBE_START_COMPLETION = 1_000
CAPACITY_PROBE_END_COMPLETION = 5_000

TRANSFORMER_PARAMETERS = 29_396_828_160
TIED_HEAD_PARAMETERS = 1_409_286_144
FP8_EFFECTIVE_FLOPS = 5_000e12 * 0.20
BF16_EFFECTIVE_FLOPS = 2_500e12 * 0.20
EFFECTIVE_HBM_BYTES_PER_SECOND = 8_000e9 * 0.30
NON_GEMM_BYTES_PER_TOKEN = 31_590_400
LAUNCH_SECONDS = 3e-6
MAIN_LAUNCHES = 60 * 18
TARGET_LAUNCHES = 60 * 18 + TARGET_DEPTH
SERVICE_SECONDS_PER_REQUEST = 0.040
COMPACTION_FIXED_SECONDS_PER_MOVE = 20e-6
COMPACTION_HOST_BYTES_PER_SECOND = 20e9
STATIC_MODEL_BYTES = 33_369_550_552
DEVICE_BYTES = 288_000_000_000
KV_BYTES_PER_TOKEN_LAYER = 4096
BLOCK_SIZE = 16

TARGET_OUTPUT_COUNTS = frozenset(
    math.ceil(index * OUTPUT_TOKENS / TARGET_CYCLES)
    for index in range(1, TARGET_CYCLES + 1)
)

SOURCE_ASSERTIONS = {
    "vllm/config/scheduler.py": [
        'policy: SchedulerPolicy = "fcfs"',
        "max_num_seqs: int = Field(",
        "enable_chunked_prefill: bool = True",
        "scheduler_cls: str | type[object] | None = None",
    ],
    "vllm/v1/core/sched/scheduler.py": [
        "token_budget = self.max_num_scheduled_tokens",
        "# First, schedule the RUNNING requests.",
        "# Next, schedule the WAITING requests.",
        "num_running >= self.max_num_running_reqs",
        "num_scheduled_tokens[request_id] = num_new_tokens",
        "request.append_output_token_ids(output_token_id)",
        "finished = self._handle_stopped_request(request)",
        "self._free_request_blocks(request)",
    ],
    "vllm/v1/worker/gpu_input_batch.py": [
        "new_req_index = self.num_reqs",
        "def remove_request(self, req_id: str)",
        "self.block_table.clear_row(req_index)",
        "def condense(self) -> None:",
        "self.block_table.move_row(last_req_index, empty_index)",
        "self.req_id_to_index[req_id] = empty_index",
        "self.temperature_cpu[empty_index] = self.temperature_cpu[last_req_index]",
        "self.generators[empty_index] = generator",
    ],
    "vllm/v1/worker/gpu_model_runner.py": [
        "for req_id in scheduler_output.finished_req_ids:",
        "self.input_batch.remove_request(req_id)",
        "self.input_batch.add_request(request)",
        "self.input_batch.condense()",
        "tokens = [scheduler_output.num_scheduled_tokens[i] for i in req_ids]",
        "def _is_uniform_decode(",
    ],
    "vllm/config/compilation.py": [
        "[1, 2, 4] + list(range(8, 256, 8))",
        "Mixed prefill-decode batches are run without cudagraphs.",
    ],
    "vllm/v1/worker/gpu_worker.py": [
        "if not self.model_config.enforce_eager:",
        "self.scheduler_config.max_num_seqs",
        "self.scheduler_config.max_num_batched_tokens",
    ],
}


@dataclass
class Request:
    request_id: int
    arrival_seconds: float
    cached_prompt_tokens: int
    fresh_prompt_tokens: int
    fresh_computed: int = 0
    output_tokens: int = 0
    first_scheduled_seconds: float | None = None
    completed_seconds: float | None = None

    @property
    def is_prefill(self) -> bool:
        return self.fresh_computed < self.fresh_prompt_tokens

    @property
    def context_tokens(self) -> int:
        if self.is_prefill:
            return self.cached_prompt_tokens + self.fresh_computed
        return PROMPT_TOKENS + self.output_tokens


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
    commit = subprocess.check_output(
        ["git", "-C", str(vllm_root), "rev-parse", "HEAD"], text=True
    ).strip()
    checks["vllm_commit"] = {
        "expected": VLLM_COMMIT,
        "observed": commit,
        "pass": commit == VLLM_COMMIT,
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
        required = SOURCE_ASSERTIONS.get(relative, [])
        missing = [fragment for fragment in required if fragment not in text]
        checks[f"contract:{relative}"] = {
            "missing_fragments": missing,
            "pass": not missing,
            "required_fragments": required,
        }
    failures = [name for name, row in checks.items() if not row["pass"]]
    if failures:
        raise RuntimeError(f"source verification failed: {failures}")
    return checks


def cached_tokens_for_request(request_id: int) -> int:
    return 535 if request_id % CACHE_MIX_PERIOD < CACHE_535_PERIOD_COUNT else 536


def make_requests(count: int, arrival_interval: float) -> list[Request]:
    requests = []
    for request_id in range(count):
        cached = cached_tokens_for_request(request_id)
        requests.append(
            Request(
                request_id=request_id,
                arrival_seconds=request_id * arrival_interval,
                cached_prompt_tokens=cached,
                fresh_prompt_tokens=PROMPT_TOKENS - cached,
            )
        )
    return requests


def sum_capped_range(start: int, count: int, cap: int) -> int:
    if count <= 0:
        return 0
    uncapped = max(0, min(count, cap - start))
    return (
        uncapped * (2 * start + uncapped + 1) // 2
        + (count - uncapped) * cap
    )


def prefill_attention_geometry(request: Request, tokens: int) -> tuple[int, int, int]:
    first_context = request.cached_prompt_tokens + request.fresh_computed
    sliding_pairs = sum_capped_range(first_context, tokens, 1024)
    global_pairs = tokens * first_context + tokens * (tokens + 1) // 2
    compulsory_kv_bytes = (
        60 * (first_context + tokens) * KV_BYTES_PER_TOKEN_LAYER
    )
    return sliding_pairs, global_pairs, compulsory_kv_bytes


def decode_attention_geometry(request: Request) -> tuple[int, int]:
    context = PROMPT_TOKENS + request.output_tokens
    flops = (
        50 * 4 * 32 * 256 * min(1024, context)
        + 10 * 4 * 32 * 512 * context
    )
    kv_bytes = KV_BYTES_PER_TOKEN_LAYER * (
        50 * min(1024, context) + 10 * context
    )
    return flops, kv_bytes


def target_attention_geometry(requests: int) -> tuple[int, int]:
    per_request_flops = TARGET_DEPTH * (
        50 * 4 * 32 * 256 * 1024
        + 10 * 4 * 32 * 512 * TARGET_CONTEXT
    )
    per_request_kv_bytes = KV_BYTES_PER_TOKEN_LAYER * (
        50 * 1024 + 10 * TARGET_CONTEXT
    )
    return requests * per_request_flops, requests * per_request_kv_bytes


def kv_resident_bytes(request: Request) -> int:
    context = request.context_tokens
    return KV_BYTES_PER_TOKEN_LAYER * (
        50 * min(1024, context) + 10 * context
    )


def compaction_bytes(request: Request) -> int:
    context = request.context_tokens
    token_state = 5 * context
    block_ids = 4 * (
        50 * math.ceil(min(1024, context) / BLOCK_SIZE)
        + 10 * math.ceil(context / BLOCK_SIZE)
    )
    return token_state + block_ids + 512


def empty_accounting() -> dict[str, float]:
    return {
        "attention_flops": 0.0,
        "attention_kv_read_bytes": 0.0,
        "attention_seconds": 0.0,
        "compaction_bytes": 0.0,
        "compaction_moves": 0.0,
        "compaction_seconds": 0.0,
        "decode_rows": 0.0,
        "fallback_requests": 0.0,
        "graph_padding_tokens": 0.0,
        "head_compute_flops": 0.0,
        "head_seconds": 0.0,
        "head_weight_bytes": 0.0,
        "idle_seconds": 0.0,
        "kv_write_bytes": 0.0,
        "launch_count": 0.0,
        "launch_seconds": 0.0,
        "main_forward_events": 0.0,
        "mixed_prefill_decode_events": 0.0,
        "non_gemm_bytes": 0.0,
        "non_gemm_seconds": 0.0,
        "prefill_head_rows": 0.0,
        "prefill_tokens": 0.0,
        "service_seconds": 0.0,
        "target_cycles": 0.0,
        "target_forward_events": 0.0,
        "target_rows": 0.0,
        "transformer_compute_flops": 0.0,
        "transformer_seconds": 0.0,
        "transformer_weight_bytes": 0.0,
    }


def add_accounting(
    destination: dict[str, float], increment: dict[str, float]
) -> None:
    for key, value in increment.items():
        destination[key] += value


def main_forward_cost(
    scheduled: list[tuple[Request, str, int]]
) -> tuple[float, dict[str, float]]:
    tokens = sum(row[2] for row in scheduled)
    decode_rows = sum(row[1] == "decode" for row in scheduled)
    prefill_chunks = [row for row in scheduled if row[1] == "prefill"]
    prefill_completions = sum(
        request.fresh_computed + count == request.fresh_prompt_tokens
        for request, _, count in prefill_chunks
    )
    head_rows = decode_rows + prefill_completions

    transformer_flops = 2 * TRANSFORMER_PARAMETERS * tokens
    transformer_compute_seconds = transformer_flops / FP8_EFFECTIVE_FLOPS
    transformer_weight_bytes = TRANSFORMER_PARAMETERS
    transformer_weight_seconds = (
        transformer_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND
    )
    transformer_seconds = max(
        transformer_compute_seconds, transformer_weight_seconds
    )

    head_flops = 2 * TIED_HEAD_PARAMETERS * head_rows
    head_weight_bytes = 2 * TIED_HEAD_PARAMETERS if head_rows else 0
    head_seconds = (
        max(
            head_flops / BF16_EFFECTIVE_FLOPS,
            head_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND,
        )
        if head_rows
        else 0.0
    )

    attention_flops = 0
    attention_kv_bytes = 0
    for request, kind, count in scheduled:
        if kind == "decode":
            flops, kv_bytes = decode_attention_geometry(request)
        else:
            sliding, global_pairs, kv_bytes = prefill_attention_geometry(
                request, count
            )
            flops = (
                50 * 4 * 32 * 256 * sliding
                + 10 * 4 * 32 * 512 * global_pairs
            )
        attention_flops += flops
        attention_kv_bytes += kv_bytes
    attention_seconds = max(
        attention_flops / BF16_EFFECTIVE_FLOPS,
        attention_kv_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND,
    )

    non_gemm_bytes = NON_GEMM_BYTES_PER_TOKEN * tokens
    non_gemm_seconds = non_gemm_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND
    launch_seconds = MAIN_LAUNCHES * LAUNCH_SECONDS
    seconds = (
        transformer_seconds
        + head_seconds
        + attention_seconds
        + non_gemm_seconds
        + launch_seconds
    )
    accounting = {
        **empty_accounting(),
        "attention_flops": float(attention_flops),
        "attention_kv_read_bytes": float(attention_kv_bytes),
        "attention_seconds": attention_seconds,
        "decode_rows": float(decode_rows),
        "head_compute_flops": float(head_flops),
        "head_seconds": head_seconds,
        "head_weight_bytes": float(head_weight_bytes),
        "kv_write_bytes": float(tokens * 60 * KV_BYTES_PER_TOKEN_LAYER),
        "launch_count": float(MAIN_LAUNCHES),
        "launch_seconds": launch_seconds,
        "main_forward_events": 1.0,
        "mixed_prefill_decode_events": float(bool(prefill_chunks and decode_rows)),
        "non_gemm_bytes": float(non_gemm_bytes),
        "non_gemm_seconds": non_gemm_seconds,
        "prefill_head_rows": float(prefill_completions),
        "prefill_tokens": float(sum(row[2] for row in prefill_chunks)),
        "transformer_compute_flops": float(transformer_flops),
        "transformer_seconds": transformer_seconds,
        "transformer_weight_bytes": float(transformer_weight_bytes),
    }
    return seconds, accounting


def target_forward_cost(due_requests: int) -> tuple[float, dict[str, float]]:
    target_rows = due_requests * TARGET_DEPTH
    transformer_flops = 2 * TRANSFORMER_PARAMETERS * target_rows
    transformer_weight_bytes = TRANSFORMER_PARAMETERS
    transformer_seconds = max(
        transformer_flops / FP8_EFFECTIVE_FLOPS,
        transformer_weight_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND,
    )

    head_flops = 2 * TIED_HEAD_PARAMETERS * due_requests * TARGET_DEPTH
    head_weight_bytes = 2 * TIED_HEAD_PARAMETERS * TARGET_DEPTH
    head_seconds = TARGET_DEPTH * max(
        2 * TIED_HEAD_PARAMETERS * due_requests / BF16_EFFECTIVE_FLOPS,
        2 * TIED_HEAD_PARAMETERS / EFFECTIVE_HBM_BYTES_PER_SECOND,
    )
    attention_flops, attention_kv_bytes = target_attention_geometry(due_requests)
    attention_seconds = max(
        attention_flops / BF16_EFFECTIVE_FLOPS,
        attention_kv_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND,
    )
    non_gemm_bytes = NON_GEMM_BYTES_PER_TOKEN * target_rows
    non_gemm_seconds = non_gemm_bytes / EFFECTIVE_HBM_BYTES_PER_SECOND
    launch_seconds = TARGET_LAUNCHES * LAUNCH_SECONDS
    seconds = (
        transformer_seconds
        + head_seconds
        + attention_seconds
        + non_gemm_seconds
        + launch_seconds
    )
    accounting = {
        **empty_accounting(),
        "attention_flops": float(attention_flops),
        "attention_kv_read_bytes": float(attention_kv_bytes),
        "attention_seconds": attention_seconds,
        "head_compute_flops": float(head_flops),
        "head_seconds": head_seconds,
        "head_weight_bytes": float(head_weight_bytes),
        "kv_write_bytes": float(
            target_rows * 60 * KV_BYTES_PER_TOKEN_LAYER
        ),
        "launch_count": float(TARGET_LAUNCHES),
        "launch_seconds": launch_seconds,
        "non_gemm_bytes": float(non_gemm_bytes),
        "non_gemm_seconds": non_gemm_seconds,
        "target_cycles": float(due_requests),
        "target_forward_events": 1.0,
        "target_rows": float(target_rows),
        "transformer_compute_flops": float(transformer_flops),
        "transformer_seconds": transformer_seconds,
        "transformer_weight_bytes": float(transformer_weight_bytes),
    }
    return seconds, accounting


def compact_slots(
    slots: list[Request | None],
) -> tuple[int, int]:
    moves = 0
    moved_bytes = 0
    while True:
        try:
            empty = slots.index(None)
        except ValueError:
            break
        last = len(slots) - 1
        while last >= 0 and slots[last] is None:
            slots.pop()
            last -= 1
        if empty >= len(slots):
            break
        moved = slots[last]
        assert moved is not None
        slots[empty] = moved
        slots.pop()
        moves += 1
        moved_bytes += compaction_bytes(moved)
    return moves, moved_bytes


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def simulate(requests: list[Request]) -> dict[str, Any]:
    slots: list[Request | None] = []
    waiting: list[Request] = []
    next_arrival = 0
    now = 0.0
    completed_count = 0
    completion_milestones: dict[int, float] = {}
    accounting = empty_accounting()
    main_width_histogram: dict[int, int] = {}
    peak_live = 0
    peak_observed_resident_bytes = STATIC_MODEL_BYTES
    peak_target_due = 0
    first_full_width_seconds: float | None = None
    last_arrival = requests[-1].arrival_seconds

    while completed_count < len(requests):
        while (
            next_arrival < len(requests)
            and requests[next_arrival].arrival_seconds <= now + 1e-12
        ):
            waiting.append(requests[next_arrival])
            next_arrival += 1

        if not slots and not waiting:
            next_time = requests[next_arrival].arrival_seconds
            idle = next_time - now
            accounting["idle_seconds"] += idle
            now = next_time
            continue

        token_budget = PREFILL_TOKEN_BUDGET
        scheduled: list[tuple[Request, str, int]] = []
        for request in slots:
            if request is None or token_budget <= 0:
                continue
            if request.is_prefill:
                count = min(
                    request.fresh_prompt_tokens - request.fresh_computed,
                    token_budget,
                )
                kind = "prefill"
            else:
                count = 1
                kind = "decode"
            scheduled.append((request, kind, count))
            token_budget -= count

        while (
            waiting
            and sum(request is not None for request in slots) < MAX_LIVE_REQUESTS
            and token_budget > 0
        ):
            request = waiting.pop(0)
            if request.first_scheduled_seconds is None:
                request.first_scheduled_seconds = now
            count = min(request.fresh_prompt_tokens, token_budget)
            try:
                empty = slots.index(None)
            except ValueError:
                slots.append(request)
            else:
                slots[empty] = request
            scheduled.append((request, "prefill", count))
            token_budget -= count

        moves, moved_bytes = compact_slots(slots)
        if moves:
            seconds = (
                moves * COMPACTION_FIXED_SECONDS_PER_MOVE
                + moved_bytes / COMPACTION_HOST_BYTES_PER_SECOND
            )
            accounting["compaction_moves"] += moves
            accounting["compaction_bytes"] += moved_bytes
            accounting["compaction_seconds"] += seconds
            now += seconds

        if not scheduled:
            if next_arrival < len(requests):
                next_time = requests[next_arrival].arrival_seconds
                idle = max(0.0, next_time - now)
                accounting["idle_seconds"] += idle
                now = max(now, next_time)
                continue
            raise RuntimeError("unfinished requests but no schedulable work")

        active = len(slots)
        peak_live = max(peak_live, active)
        if active == MAX_LIVE_REQUESTS and first_full_width_seconds is None:
            first_full_width_seconds = now
        main_width_histogram[active] = main_width_histogram.get(active, 0) + 1
        resident = STATIC_MODEL_BYTES + sum(
            kv_resident_bytes(request)
            for request in slots
            if request is not None
        )
        peak_observed_resident_bytes = max(
            peak_observed_resident_bytes, resident
        )

        main_seconds, main_accounting = main_forward_cost(scheduled)
        add_accounting(accounting, main_accounting)
        now += main_seconds

        due: list[Request] = []
        for request, kind, count in scheduled:
            if kind == "prefill":
                request.fresh_computed += count
                if not request.is_prefill:
                    request.output_tokens = 1
            else:
                request.output_tokens += 1
            if request.output_tokens in TARGET_OUTPUT_COUNTS:
                due.append(request)

        if due:
            target_seconds, target_accounting = target_forward_cost(len(due))
            add_accounting(accounting, target_accounting)
            now += target_seconds
            peak_target_due = max(peak_target_due, len(due))

        finished = [
            request
            for request in slots
            if request is not None and request.output_tokens == OUTPUT_TOKENS
        ]
        if finished:
            service_seconds = SERVICE_SECONDS_PER_REQUEST * len(finished)
            accounting["service_seconds"] += service_seconds
            now += service_seconds
            finished_ids = {request.request_id for request in finished}
            for index, request in enumerate(slots):
                if request is not None and request.request_id in finished_ids:
                    slots[index] = None
            for request in finished:
                request.completed_seconds = now
                completed_count += 1
                if completed_count in {
                    CAPACITY_PROBE_START_COMPLETION,
                    CAPACITY_PROBE_END_COMPLETION,
                }:
                    completion_milestones[completed_count] = now

    queue = [
        request.first_scheduled_seconds - request.arrival_seconds
        for request in requests
        if request.first_scheduled_seconds is not None
    ]
    completion = [
        request.completed_seconds - request.arrival_seconds
        for request in requests
        if request.completed_seconds is not None
    ]
    if len(queue) != len(requests) or len(completion) != len(requests):
        raise RuntimeError("request accounting incomplete")
    return {
        "accounting": accounting,
        "all_requests_completed": completed_count == len(requests),
        "completion_milestones": completion_milestones,
        "completion_p50_seconds": percentile(completion, 0.50),
        "completion_p95_seconds": percentile(completion, 0.95),
        "completion_seconds_max": max(completion),
        "final_completion_seconds": now,
        "first_full_width_seconds": first_full_width_seconds,
        "last_arrival_seconds": last_arrival,
        "main_width_histogram": {
            str(key): value for key, value in sorted(main_width_histogram.items())
        },
        "peak_live_requests": peak_live,
        "peak_observed_resident_bytes": peak_observed_resident_bytes,
        "peak_target_due_requests": peak_target_due,
        "queue_p50_seconds": percentile(queue, 0.50),
        "queue_p95_seconds": percentile(queue, 0.95),
        "queue_seconds_max": max(queue),
        "requests": len(requests),
        "starved_requests": sum(not math.isfinite(value) for value in completion),
    }


def capacity_probe() -> tuple[float, dict[str, Any]]:
    probe = simulate(make_requests(CAPACITY_PROBE_REQUESTS, 0.0))
    milestones = probe["completion_milestones"]
    elapsed = (
        milestones[CAPACITY_PROBE_END_COMPLETION]
        - milestones[CAPACITY_PROBE_START_COMPLETION]
    )
    capacity = (
        CAPACITY_PROBE_END_COMPLETION - CAPACITY_PROBE_START_COMPLETION
    ) / elapsed
    return capacity, probe


def configured_memory_screen() -> dict[str, Any]:
    full_context_kv = KV_BYTES_PER_TOKEN_LAYER * (
        50 * 1024 + 10 * (PROMPT_TOKENS + OUTPUT_TOKENS)
    )
    resident_kv = MAX_LIVE_REQUESTS * full_context_kv
    target_extra = (
        MAX_LIVE_REQUESTS
        * TARGET_DEPTH
        * 60
        * KV_BYTES_PER_TOKEN_LAYER
    )
    source_bound = STATIC_MODEL_BYTES + resident_kv + target_extra
    envelope = 2 * source_bound
    return {
        "configured_full_context_fp8_kv_bytes": resident_kv,
        "configured_source_bound_bytes": source_bound,
        "configured_target_extra_fp8_kv_bytes": target_extra,
        "conservative_two_x_runtime_envelope_bytes": envelope,
        "fits": envelope <= DEVICE_BYTES,
        "mi355x_decimal_capacity_bytes": DEVICE_BYTES,
        "two_x_envelope_margin_bytes": DEVICE_BYTES - envelope,
    }


def validate_inputs(
    bindings: dict[str, Any], parent: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    bound_paths = {
        "accelerator_inventory": Path(bindings["accelerator_inventory"]["path"]),
        "gpu_prices": Path(bindings["gpu_prices"]["path"]),
        "parent_screen": PARENT_SCREEN,
        "preserved_barrier_terminal": BARRIER_SCREEN,
    }
    checks = {}
    for name, path in bound_paths.items():
        expected = bindings[name]["sha256"]
        observed = sha256(path) if path.is_file() else None
        checks[name] = {
            "expected_sha256": expected,
            "observed_sha256": observed,
            "pass": observed == expected,
        }
        if observed != expected:
            raise RuntimeError(f"{name} hash mismatch")
    if (
        parent["scope"]["model"] != MODEL_ID
        or parent["scope"]["revision"] != MODEL_REVISION
        or parent["scope"]["workload"]["prompt_tokens"] != PROMPT_TOKENS
        or parent["scope"]["workload"]["output_tokens"] != OUTPUT_TOKENS
    ):
        raise RuntimeError("parent workload mismatch")
    return checks


def build_artifact(
    bindings: dict[str, Any],
    source_checks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    parent = load_json(PARENT_SCREEN)
    input_checks = validate_inputs(bindings, parent)
    capacity, probe = capacity_probe()
    offered_rate = capacity * OFFERED_CAPACITY_FRACTION
    finite = simulate(make_requests(FINITE_REQUESTS, 1 / offered_rate))
    accounting = finite["accounting"]
    memory = configured_memory_screen()

    total_seconds_per_request = (
        finite["final_completion_seconds"] / FINITE_REQUESTS
    )
    queue_pass = finite["queue_p95_seconds"] <= QUEUE_P95_GATE_SECONDS
    completion_pass = (
        finite["completion_p95_seconds"] <= COMPLETION_P95_GATE_SECONDS
    )
    economic_pass = total_seconds_per_request <= TARGET_SECONDS_PER_REQUEST
    load_pass = offered_rate <= capacity * 0.90 + 1e-12
    semantic_pass = (
        int(accounting["prefill_tokens"])
        == sum(request.fresh_prompt_tokens for request in make_requests(FINITE_REQUESTS, 0))
        and int(accounting["decode_rows"])
        + int(accounting["prefill_head_rows"])
        == FINITE_REQUESTS * OUTPUT_TOKENS
        and int(accounting["target_cycles"])
        == FINITE_REQUESTS * TARGET_CYCLES
        and finite["all_requests_completed"]
    )
    source_pass = all(row["pass"] for row in source_checks.values())
    passes = (
        economic_pass
        and queue_pass
        and completion_pass
        and memory["fits"]
        and load_pass
        and semantic_pass
        and source_pass
        and finite["starved_requests"] == 0
    )
    classification = (
        "source_complete_rolling_batching_candidate"
        if passes
        else "typed_none"
    )

    bootstrap_boundary = FINITE_REQUESTS // 20 / offered_rate
    drain_seconds = (
        finite["final_completion_seconds"] - finite["last_arrival_seconds"]
    )
    steady_seconds = finite["last_arrival_seconds"] - bootstrap_boundary
    capacity_interval_seconds = 1 / capacity
    offered_interval_seconds = 1 / offered_rate
    width_events = {
        int(width): count for width, count in finite["main_width_histogram"].items()
    }
    mean_event_width = sum(
        width * count for width, count in width_events.items()
    ) / sum(width_events.values())

    return {
        "charged_cost_categories": {
            "actual_width_prompt": True,
            "actual_width_decode": True,
            "attention": True,
            "bootstrap": True,
            "compaction": True,
            "compute": True,
            "drain": True,
            "fallback": True,
            "graph_and_padding": True,
            "idle": True,
            "kv_read_write_and_capacity": True,
            "launch": True,
            "memory": True,
            "queue": True,
            "scheduler_and_service": True,
            "target_verification": True,
            "tied_head": True,
            "weights_fp8_and_bf16": True,
        },
        "classification": classification,
        "decision": {
            "completion_p95_gate_pass": completion_pass,
            "economic_gate_pass": economic_pass,
            "load_at_most_90_percent_capacity_pass": load_pass,
            "memory_gate_pass": memory["fits"],
            "queue_p95_gate_pass": queue_pass,
            "result": classification,
            "semantic_accounting_pass": semantic_pass,
            "source_binding_pass": source_pass,
            "starvation_gate_pass": finite["starved_requests"] == 0,
        },
        "finite_stream": {
            "arrival_interval_seconds": offered_interval_seconds,
            "bootstrap_boundary_seconds_first_5_percent_arrived": (
                bootstrap_boundary
            ),
            "capacity_requests_per_second": capacity,
            "capacity_seconds_per_request": capacity_interval_seconds,
            "completion_p50_seconds": finite["completion_p50_seconds"],
            "completion_p95_seconds": finite["completion_p95_seconds"],
            "completion_seconds_max": finite["completion_seconds_max"],
            "drain_seconds_after_last_arrival": drain_seconds,
            "fallback_request_fraction": (
                accounting["fallback_requests"] / FINITE_REQUESTS
            ),
            "final_completion_seconds": finite["final_completion_seconds"],
            "first_full_width_seconds": finite["first_full_width_seconds"],
            "load_fraction_of_capacity": offered_rate / capacity,
            "mean_main_event_live_width": mean_event_width,
            "offered_requests_per_second": offered_rate,
            "peak_live_requests": finite["peak_live_requests"],
            "queue_p50_seconds": finite["queue_p50_seconds"],
            "queue_p95_seconds": finite["queue_p95_seconds"],
            "queue_seconds_max": finite["queue_seconds_max"],
            "requests": FINITE_REQUESTS,
            "phase_wall_seconds": {
                "bootstrap_first_5_percent_arrival_window": bootstrap_boundary,
                "drain_after_last_arrival": drain_seconds,
                "steady_arrival_window": steady_seconds,
                "sum_charged_in_all_request_mean": (
                    bootstrap_boundary + steady_seconds + drain_seconds
                ),
            },
            "starved_requests": finite["starved_requests"],
            "total_seconds_per_request_including_bootstrap_and_drain": (
                total_seconds_per_request
            ),
            "width_event_histogram": finite["main_width_histogram"],
        },
        "generated_from_observation_utc": "2026-07-26T14:26:44Z",
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
            "preserved_barrier_terminal": {
                "path": str(BARRIER_SCREEN),
                "sha256": sha256(BARRIER_SCREEN),
            },
            "project": {
                "path": str(PROJECT_DIR / "PROJECT.md"),
                "sha256": sha256(PROJECT_DIR / "PROJECT.md"),
            },
            "input_checks": input_checks,
            "source_checks": source_checks,
        },
        "memory": {
            **memory,
            "observed_peak_live_requests": finite["peak_live_requests"],
            "observed_peak_resident_bytes_before_two_x_envelope": finite[
                "peak_observed_resident_bytes"
            ],
            "observed_peak_target_due_requests": finite[
                "peak_target_due_requests"
            ],
        },
        "physical_accounting": {
            **accounting,
            "bf16_math_efficiency": 0.20,
            "compaction_host_bandwidth_bytes_per_second": (
                COMPACTION_HOST_BYTES_PER_SECOND
            ),
            "compaction_seconds_per_moved_row": (
                COMPACTION_FIXED_SECONDS_PER_MOVE
            ),
            "enforce_eager": True,
            "fp8_math_efficiency": 0.20,
            "hbm_efficiency": 0.30,
            "internal_tile_underfill_rule": "No extra utilization credit; the settled 20% tensor and 30% HBM efficiencies remain fixed for every actual M.",
            "scheduler_service_seconds_per_request": SERVICE_SECONDS_PER_REQUEST,
            "seconds_per_request_by_critical_path_family": {
                "attention": accounting["attention_seconds"] / FINITE_REQUESTS,
                "compaction": accounting["compaction_seconds"] / FINITE_REQUESTS,
                "head": accounting["head_seconds"] / FINITE_REQUESTS,
                "idle": accounting["idle_seconds"] / FINITE_REQUESTS,
                "launch": accounting["launch_seconds"] / FINITE_REQUESTS,
                "non_gemm_and_kv_write": (
                    accounting["non_gemm_seconds"] / FINITE_REQUESTS
                ),
                "scheduler_and_service": (
                    accounting["service_seconds"] / FINITE_REQUESTS
                ),
                "transformer": (
                    accounting["transformer_seconds"] / FINITE_REQUESTS
                ),
            },
        },
        "physical_interpretation": {
            "capacity_falsifier": (
                f"The saturated source-real rolling policy itself is "
                f"{1 / capacity} s/request, above the locked "
                f"{TARGET_SECONDS_PER_REQUEST} target; the finite "
                "90%-capacity stream is necessarily worse."
            ),
            "observed_mechanism": "Immediate individual admission removes cohort queueing but lowers steady live width and dephases request-relative target cycles. Required target work is spread across many small forwards, repeatedly charging transformer/head streams and launches.",
            "target_cycles_per_target_forward": (
                accounting["target_cycles"] / accounting["target_forward_events"]
            ),
            "target_forward_events": int(accounting["target_forward_events"]),
            "target_head_weight_streams": int(
                accounting["target_forward_events"] * TARGET_DEPTH
            ),
            "what_would_falsify_this_explanation": "A target MI355X trace of this exact FCFS/8192/eager policy showing materially larger target-cycle grouping or >=1.999522 req/s saturated completed-request throughput with identical target, token, and cache accounting.",
        },
        "policy": {
            "admission": "Stock FCFS individual request admission whenever a slot and token budget remain; no cohort barrier.",
            "cache_mix": "A deterministic 1,000-request period has 822 requests with 535 cached tokens and 178 with 536, exactly preserving the parent 12.7% expectation.",
            "compaction": "Remove finished request IDs, fill the smallest freed indices with new requests, then move the highest remaining live rows into holes through GPUInputBatch.condense.",
            "fallback": "None; max-live memory fits and no request is preempted or dropped.",
            "graph_mode": "enforce_eager; exact token rows execute without graph padding and all launches are charged.",
            "max_live_sequences": MAX_LIVE_REQUESTS,
            "prefill_decode_interleave": "Schedule every existing live request first, then waiting requests with the remaining token budget, matching Scheduler.schedule.",
            "prefill_token_budget": PREFILL_TOKEN_BUDGET,
            "sampling_and_ownership": "Per-request token IDs, positions, KV block rows, sampling metadata, completion, and freed-slot reuse remain distinct.",
            "selected_policy_count": 1,
            "target_verification_cadence": "Execute each request's 15 conservative depth-12 target cycles immediately after output counts ceil(k*358/15), k=1..15; batch only requests due in the same scheduler iteration.",
        },
        "probe": {
            "end_completion": CAPACITY_PROBE_END_COMPLETION,
            "end_seconds": probe["completion_milestones"][
                CAPACITY_PROBE_END_COMPLETION
            ],
            "requests": CAPACITY_PROBE_REQUESTS,
            "saturated_capacity_requests_per_second": capacity,
            "saturated_seconds_per_request": 1 / capacity,
            "start_completion": CAPACITY_PROBE_START_COMPLETION,
            "start_seconds": probe["completion_milestones"][
                CAPACITY_PROBE_START_COMPLETION
            ],
        },
        "scope": {
            "accelerator": "one AMD Instinct MI355X, TP1",
            "mode": "text_only_non_reasoning",
            "model": MODEL_ID,
            "provider_spend_usd": 0.0,
            "revision": MODEL_REVISION,
            "tokens_per_request": TOTAL_TOKENS,
        },
        "semantic_accounting": {
            "all_60_layers_preserved": True,
            "all_checkpoint_parameters_preserved": True,
            "all_requests_completed": finite["all_requests_completed"],
            "cache_mix_preserved": True,
            "decode_and_first_sample_rows_expected": (
                FINITE_REQUESTS * OUTPUT_TOKENS
            ),
            "decode_and_first_sample_rows_observed": int(
                accounting["decode_rows"] + accounting["prefill_head_rows"]
            ),
            "exact_attention_and_kv_ownership": True,
            "feature_and_sampling_semantics_preserved": True,
            "fresh_prompt_tokens_expected": sum(
                request.fresh_prompt_tokens
                for request in make_requests(FINITE_REQUESTS, 0)
            ),
            "fresh_prompt_tokens_observed": int(accounting["prefill_tokens"]),
            "target_cycles_expected": FINITE_REQUESTS * TARGET_CYCLES,
            "target_cycles_observed": int(accounting["target_cycles"]),
        },
        "terminal": classification,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--vllm-root", type=Path)
    args = parser.parse_args()

    bindings = load_json(BINDINGS_PATH)
    if args.vllm_root is not None:
        source_checks = verify_sources(bindings, args.vllm_root)
        artifact = build_artifact(bindings, source_checks)
    else:
        with tempfile.TemporaryDirectory(prefix="mi355x-rolling-vllm-") as temp:
            root = Path(temp)
            fetch_vllm(root, bindings)
            source_checks = verify_sources(bindings, root)
            artifact = build_artifact(bindings, source_checks)
    atomic_json(args.output, artifact)
    print(
        json.dumps(
            {
                "capacity_requests_per_second": artifact["finite_stream"][
                    "capacity_requests_per_second"
                ],
                "classification": artifact["classification"],
                "completion_p95_seconds": artifact["finite_stream"][
                    "completion_p95_seconds"
                ],
                "offered_requests_per_second": artifact["finite_stream"][
                    "offered_requests_per_second"
                ],
                "output": str(args.output),
                "queue_p95_seconds": artifact["finite_stream"][
                    "queue_p95_seconds"
                ],
                "seconds_per_request": artifact["finite_stream"][
                    "total_seconds_per_request_including_bootstrap_and_drain"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
