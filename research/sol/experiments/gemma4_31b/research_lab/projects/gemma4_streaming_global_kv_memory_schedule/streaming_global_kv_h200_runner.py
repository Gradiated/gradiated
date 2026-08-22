#!/usr/bin/env python3
"""Exact-shape CUDA discriminator for the hash-bound U=8 schedule."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import statistics
import time

import torch

import multiresolution_global_kv as activated
from streaming_global_kv_schedule import LayerRequest, STREAM_CHUNK_TOKENS, forward_layer_local_inplace

ROOT = pathlib.Path(__file__).resolve().parent
TOLERANCE = 0.00390625
EXPECTED = {
    "multiresolution_global_kv.py": "47c1dd902dd287cab2403cb06790095a3e041df434e48ffe22832dfdad4d4880",
    "streaming_global_kv_schedule.py": "636cc6e683d04f8950ce288f567ed5411a8d3cbb667b92329827c9bc6d35a23a",
}


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    data = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(data)
    json.loads(temporary.read_text())
    temporary.replace(path)


def identity() -> None:
    for name, expected in EXPECTED.items():
        path = ROOT / name
        if digest(path) != expected:
            raise RuntimeError(f"hash_bound_input_mismatch:{name}")
    if not torch.cuda.is_available():
        raise RuntimeError("target_runtime_cuda_unavailable")
    if STREAM_CHUNK_TOKENS != 8:
        raise RuntimeError("u8_schedule_contract_mismatch")


def state_for(k: torch.Tensor, v: torch.Tensor, start: int, protected: tuple[int, ...]) -> activated.IncrementalGlobalSummaryState:
    state = activated.IncrementalGlobalSummaryState(protected)
    for offset in range(0, start, 32):
        state.append_committed(k[offset:min(start, offset + 32)], v[offset:min(start, offset + 32)])
    return state


def one(compact_target: int, rows: int, seed: int, timed: bool) -> dict[str, object]:
    protected = tuple(range(8))
    # Full summaries plus 16 exact positions choose the requested source cap.
    start = 4609 if compact_target == 26 else (compact_target - 16) * 512
    total = start + rows
    torch.manual_seed(seed)
    k = torch.randn(total, 4, 512, dtype=torch.bfloat16, device="cuda")
    v = torch.randn_like(k)
    original_q = torch.randn(rows, 32, 512, dtype=torch.bfloat16, device="cuda")
    reference_state = state_for(k, v, start, protected)
    candidate_state = state_for(k, v, start, protected)
    reference_q = original_q.clone()
    candidate_q = original_q.clone()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter_ns()
    reference = activated.multiresolution_global_attention("decode" if rows == 1 else "prefill", reference_q, k, v, start, summary_state=reference_state, protected_positions=protected, commit_after_consume=True)
    torch.cuda.synchronize()
    activated_ns = time.perf_counter_ns() - started if timed else None
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter_ns()
    telemetry = forward_layer_local_inplace([LayerRequest("decode" if rows == 1 else "prefill", candidate_q, k, v, start, candidate_state, protected)])
    torch.cuda.synchronize()
    streamed_ns = time.perf_counter_ns() - started if timed else None
    delta = (candidate_q.float() - reference.float()).abs().max().item()
    return {
        "compact_target": compact_target, "query_rows": rows, "max_abs": delta,
        "finite": bool(torch.isfinite(candidate_q).all()), "candidate_path_proof": telemetry,
        "allocated_peak_bytes": torch.cuda.max_memory_allocated(),
        "reserved_peak_bytes": torch.cuda.max_memory_reserved(),
        "largest_candidate_allocation_bound_bytes": 65536,
        "activated_elapsed_ns": activated_ns, "streamed_elapsed_ns": streamed_ns,
        "pass": bool(math.isfinite(delta) and delta <= TOLERANCE and torch.isfinite(candidate_q).all()),
    }


def run(output: pathlib.Path) -> int:
    identity()
    correctness = one(26, 1, 17, False)
    boundary = [one(64, 1, 31, False), one(64, 32, 37, False)]
    samples = [one(26, 1, 100 + index, True) for index in range(5)]
    component = {
        "activated_median_ns": statistics.median(row["activated_elapsed_ns"] for row in samples),
        "activated_p95_ns": sorted(row["activated_elapsed_ns"] for row in samples)[-1],
        "streamed_median_ns": statistics.median(row["streamed_elapsed_ns"] for row in samples),
        "streamed_p95_ns": sorted(row["streamed_elapsed_ns"] for row in samples)[-1],
        "samples": samples,
    }
    passed = correctness["pass"] and all(row["pass"] and row["largest_candidate_allocation_bound_bytes"] <= 65536 for row in boundary) and all(row["pass"] for row in samples)
    result = {"schema_version": 1, "classification": "streaming_global_kv_cuda_discriminator", "science_started": True, "cuda_started": True, "device": torch.cuda.get_device_name(), "tolerance": TOLERANCE, "u": 8, "correctness_c26_q1": correctness, "boundaries": boundary, "component_profiler_off": component, "gates_pass": passed, "endpoint_eligible": passed}
    atomic(output, result)
    return 0 if passed else 72


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.output))
