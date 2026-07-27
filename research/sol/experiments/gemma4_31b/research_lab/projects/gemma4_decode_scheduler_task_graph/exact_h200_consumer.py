#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
import sys
import time
from types import SimpleNamespace
from typing import Any, Callable

import torch

from decode_scheduler_task_graph import DecodeSchedulerTaskGraph


MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
SGLANG_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
SCHEDULE_BATCH_HASHES = {
    "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874",
    "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459",
}
COMMON_SHA256 = "987c02d71dd773d32263d6d34d94d508b74c707e0ca3d918723e981088bb14a9"
DECODE_STEPS = 358
CONCURRENCY = 32
INITIAL_SEQUENCE_LENGTH = 4214
REQ_POOL_FACTORY: Callable[[int, int], Any] | None = None
SLOT_ALLOCATOR_FACTORY: Callable[[int], Any] | None = None


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def inputs(batch_size: int) -> dict[str, Any]:
    if REQ_POOL_FACTORY is None or SLOT_ALLOCATOR_FACTORY is None:
        raise RuntimeError("production_pool_types_not_loaded")
    torch.manual_seed(20260727 + batch_size)
    req_to_token_pool = REQ_POOL_FACTORY(
        batch_size,
        INITIAL_SEQUENCE_LENGTH + batch_size + DECODE_STEPS + 8,
    )
    pool = req_to_token_pool.req_to_token
    pool.fill_(-1)
    requests = [
        SimpleNamespace(
            req_pool_idx=None, inflight_middle_chunks=0, kv_committed_len=0
        )
        for _ in range(batch_size)
    ]
    allocated_rows = req_to_token_pool.alloc(requests)
    if allocated_rows is None:
        raise RuntimeError("production_req_to_token_pool_allocation_failed")
    permutation = torch.randperm(batch_size, dtype=torch.int64)
    req_rows = torch.tensor(allocated_rows, dtype=torch.int64)[permutation].to("cuda")
    seq = torch.arange(
        INITIAL_SEQUENCE_LENGTH,
        INITIAL_SEQUENCE_LENGTH + batch_size,
        device="cuda",
        dtype=torch.int64,
    )
    orig = seq.to(torch.int32)
    slot_allocator = SLOT_ALLOCATOR_FACTORY(DECODE_STEPS * batch_size + 8)
    slot_rows = [slot_allocator.alloc(batch_size) for _ in range(DECODE_STEPS)]
    if any(row is None for row in slot_rows):
        raise RuntimeError("production_token_to_kv_allocation_failed")
    slots = torch.stack(slot_rows)
    return {
        "req_rows": req_rows,
        "seq": seq,
        "orig": orig,
        "slots": slots,
        "pool": pool,
        "req_to_token_pool": req_to_token_pool,
        "slot_allocator": slot_allocator,
    }


def stock_chain(
    state: dict[str, Any],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    seq = state["seq"].clone()
    orig = state["orig"].clone()
    for slots in state["slots"]:
        state["req_to_token_pool"].write(
            (state["req_rows"], seq), slots.to(torch.int32)
        )
        seq = seq + 1
        orig = orig + 1
    consumed = state["pool"][state["req_rows"], seq - 1]
    return seq, orig, consumed


def candidate_chain(
    state: dict[str, Any],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    seq = state["seq"].clone()
    orig = state["orig"].clone()
    graph = DecodeSchedulerTaskGraph(seq, orig)
    for slots in state["slots"]:
        outputs = graph.commit(
            req_to_token=state["pool"],
            req_pool_indices=state["req_rows"],
            seq_lens=seq,
            orig_seq_lens=orig,
            out_cache_loc=slots,
        )
        seq, orig = outputs.seq_lens, outputs.orig_seq_lens
    consumed = state["pool"][state["req_rows"], seq - 1]
    return seq, orig, consumed


def correctness_case(batch_size: int) -> dict[str, object]:
    baseline = inputs(batch_size)
    candidate = inputs(batch_size)
    for name in ("req_rows", "seq", "orig", "slots"):
        candidate[name].copy_(baseline[name])
    stock_seq, stock_orig, stock_consumed = stock_chain(baseline)
    cand_seq, cand_orig, cand_consumed = candidate_chain(candidate)
    torch.cuda.synchronize()
    checks = {
        "seq_lens_equal": bool(torch.equal(stock_seq, cand_seq)),
        "orig_seq_lens_equal": bool(torch.equal(stock_orig, cand_orig)),
        "req_to_token_equal": bool(torch.equal(baseline["pool"], candidate["pool"])),
        "consumer_slots_equal": bool(torch.equal(stock_consumed, cand_consumed)),
        "consumer_slots_match_last_allocator_result": bool(
            torch.equal(cand_consumed.to(torch.int64), candidate["slots"][-1])
        ),
        "unique_request_ownership": bool(
            torch.unique(candidate["req_rows"]).numel() == batch_size
        ),
        "unique_slot_ownership": bool(
            torch.unique(candidate["slots"]).numel()
            == DECODE_STEPS * batch_size
        ),
    }
    return {
        "batch_size": batch_size,
        "decode_steps": DECODE_STEPS,
        "checks": checks,
        "passed": all(checks.values()),
        "consumed_checksum": int(cand_consumed.sum().item()),
    }


def timed_chain(
    candidate: bool, warmups: int, iterations: int
) -> dict[str, object]:
    samples = []
    checksums = []
    for sample in range(warmups + iterations):
        state = inputs(CONCURRENCY)
        begin = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        begin.record()
        if candidate:
            seq, orig, consumed = candidate_chain(state)
        else:
            seq, orig, consumed = stock_chain(state)
        end.record()
        end.synchronize()
        checksum = int(
            consumed.sum().item() + seq.sum().item() + orig.to(torch.int64).sum().item()
        )
        if sample >= warmups:
            samples.append(float(begin.elapsed_time(end)))
            checksums.append(checksum)
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "p10_ms": percentile(samples, 0.1),
        "p90_ms": percentile(samples, 0.9),
        "checksums": checksums,
    }


def main() -> None:
    global REQ_POOL_FACTORY, SLOT_ALLOCATOR_FACTORY
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--sglang-python", type=pathlib.Path, required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=15)
    args = parser.parse_args()

    invocation = args.output.with_name("INVOCATION_STATE.json")
    atomic_json(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "scientific_terminal_recorded": False,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    device = torch.cuda.get_device_properties(0)
    if device.major != 9 or "H200" not in device.name:
        raise RuntimeError(f"exact_h200_required:{device.name}:{device.major}.{device.minor}")
    candidate_source = pathlib.Path(__file__).with_name(
        "decode_scheduler_task_graph.py"
    )
    if sha256(candidate_source) != args.expected_candidate_sha256:
        raise RuntimeError("candidate_source_hash_mismatch")
    schedule_batch = args.sglang_python / "sglang/srt/managers/schedule_batch.py"
    common = args.sglang_python / "sglang/srt/mem_cache/common.py"
    schedule_hash = sha256(schedule_batch)
    common_hash = sha256(common)
    if schedule_hash not in SCHEDULE_BATCH_HASHES:
        raise RuntimeError(f"schedule_batch_source_mismatch:{schedule_hash}")
    if common_hash != COMMON_SHA256:
        raise RuntimeError(f"common_source_mismatch:{common_hash}")
    sys.path.insert(0, str(args.sglang_python))
    from sglang.srt.mem_cache.allocator.token import TokenToKVPoolAllocator
    from sglang.srt.mem_cache.memory_pool import ReqToTokenPool

    REQ_POOL_FACTORY = lambda size, context: ReqToTokenPool(
        size=size,
        max_context_len=context,
        device="cuda",
        enable_memory_saver=False,
    )
    SLOT_ALLOCATOR_FACTORY = lambda size: TokenToKVPoolAllocator(
        size=size,
        dtype=torch.float8_e5m2,
        device="cuda",
        kvcache=None,
        need_sort=False,
    )

    atomic_json(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": True,
            "scientific_terminal_recorded": False,
            "updated_unix_s": time.time(),
        },
    )
    cases = [correctness_case(batch_size) for batch_size in (1, 31, 32)]
    control = timed_chain(False, args.warmups, args.iterations)
    candidate = timed_chain(True, args.warmups, args.iterations)
    reduction = 1.0 - candidate["median_ms"] / control["median_ms"]
    passed = (
        all(case["passed"] for case in cases)
        and len(set(control["checksums"])) == 1
        and len(set(candidate["checksums"])) == 1
        and control["checksums"][0] == candidate["checksums"][0]
        and reduction > 0
    )
    terminal = {
        "schema_version": 1,
        "terminal_type": "decode_scheduler_task_graph_h200_component",
        "passed": passed,
        "scope": {
            "model": MODEL,
            "revision": REVISION,
            "sglang_commit": SGLANG_COMMIT,
            "device": device.name,
            "compute_capability": [device.major, device.minor],
            "concurrency": CONCURRENCY,
            "decode_steps": DECODE_STEPS,
            "seq_lens_dtype": "torch.int64",
            "orig_seq_lens_dtype": "torch.int32",
            "req_to_token_dtype": "torch.int32",
            "out_cache_loc_dtype": "torch.int64",
        },
        "source": {
            "candidate_sha256": sha256(candidate_source),
            "schedule_batch_sha256": schedule_hash,
            "common_sha256": common_hash,
        },
        "correctness": cases,
        "timing": {
            "control": control,
            "candidate": candidate,
            "median_reduction_fraction": reduction,
            "boundary": (
                "CUDA events around 358 allocator-result commit and immediate "
                "req_to_token consumer steps; end synchronization is outside elapsed time"
            ),
        },
        "launch_model": {
            "control_device_tasks_per_step": 4,
            "candidate_device_tasks_per_step": 1,
            "eliminated_device_tasks_per_358_step_request_window": 1074,
            "synchronization_credited_as_removable": False,
        },
    }
    atomic_json(args.output, terminal)
    atomic_json(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": True,
            "scientific_terminal_recorded": True,
            "terminal_sha256": sha256(args.output),
            "updated_unix_s": time.time(),
        },
    )
    if not passed:
        raise SystemExit(72)


if __name__ == "__main__":
    main()
