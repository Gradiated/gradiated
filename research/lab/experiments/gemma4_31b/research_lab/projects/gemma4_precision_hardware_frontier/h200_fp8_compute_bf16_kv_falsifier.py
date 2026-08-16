#!/usr/bin/env python3
import argparse
import time
from pathlib import Path

import torch

from h200_fp8_exact_shape_falsifier import (
    CASES,
    DECODE_M,
    FP8_MARGIN_TARGET,
    H200_PLANNING_USD_PER_HOUR,
    MODEL,
    OUTPUT_TOKENS,
    PREFILL_M,
    atomic_json,
    attention_row,
    distribution,
    error_metrics,
    linear_row,
    timed,
)


def bf16_kv_writer_row(case, context, heads, head_dim, multiplicity, seed):
    torch.manual_seed(seed + context + heads)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    source = torch.randn((DECODE_M, 2, heads, head_dim), device="cuda", dtype=torch.bfloat16)
    source = source / (head_dim ** 0.5)
    slots = torch.arange(DECODE_M, device="cuda")
    cache = torch.empty((context, 2, heads, head_dim), device="cuda", dtype=torch.bfloat16)
    timing, _ = timed(lambda: cache.index_copy_(0, slots, source), iterations=7)
    oracle = error_metrics(cache.index_select(0, slots), source)
    passed = bool(
        oracle["finite"]
        and oracle["nontrivial"]
        and oracle["normalized_rmse"] == 0.0
        and oracle["cosine_similarity"] >= 0.999999
        and timing["cuda_event"]["positive_finite"]
        and timing["cuda_event"]["p95_p50"] <= 4.0
    )
    row = {
        "kind": "kv_writer_bf16_shared",
        "case": case,
        "m": DECODE_M,
        "context": context,
        "heads": heads,
        "head_dim": head_dim,
        "architecture_multiplicity": multiplicity,
        "timing": timing,
        "oracle": {**oracle, "pass": passed},
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": passed,
    }
    del source, slots, cache
    torch.cuda.empty_cache()
    return row


def linear_p50(row, candidate):
    return float(row["fp8_timing" if candidate else "bf16_timing"]["cuda_event"]["p50_ms"])


def shared_p50(row):
    return float(row["timing"]["cuda_event"]["p50_ms"])


def aggregate(linears, head, attention, kv, candidate):
    prefill_ms = sum(row["architecture_multiplicity"] * linear_p50(row, candidate) for row in linears if row["m"] == PREFILL_M)
    decode_ms = sum(row["architecture_multiplicity"] * linear_p50(row, candidate) for row in linears if row["m"] == DECODE_M)
    head_ms = linear_p50(head, candidate)
    attention_ms = sum(row["architecture_multiplicity"] * shared_p50(row) for row in attention)
    kv_ms = sum(row["architecture_multiplicity"] * shared_p50(row) for row in kv)
    decode_scale = OUTPUT_TOKENS / DECODE_M / 1000
    components = {
        "prefill_linears_seconds_per_request": prefill_ms / 1000,
        "decode_linears_seconds_per_request": decode_ms * decode_scale,
        "tied_head_seconds_per_request": head_ms * decode_scale,
        "shared_bf16_attention_seconds_per_request": attention_ms * decode_scale,
        "shared_bf16_kv_writer_seconds_per_request": kv_ms * decode_scale,
    }
    total = sum(components.values())
    return {
        **components,
        "component_floor_seconds_per_request": total,
        "planning_usd_per_million_requests": total / 3600 * H200_PLANNING_USD_PER_HOUR * 1_000_000,
        "planning_rate_usd_per_gpu_hour": H200_PLANNING_USD_PER_HOUR,
        "shared_kv_accounting": "identical measured BF16 KV-write cost is charged to control and candidate",
        "claim_scope": "measured component proxy only; not full-model throughput or endpoint cost",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260718)
    args = parser.parse_args()
    started = time.perf_counter()
    result = {
        "schema_version": 1,
        "type": "gemma4_h200_e4m3_compute_bf16_kv_exact_shape_falsifier",
        "model": MODEL,
        "semantics": "checkpoint-free exact-shape component proxy; E4M3 only for linears/head and BF16 attention/KV shared in both arms",
        "hypothesis": "supported E4M3 compute with unchanged BF16 state is at least 20% below all-BF16 component floor",
        "rows": {"linears": [], "head": [], "attention": [], "kv_writer": []},
        "pass": False,
    }
    useful_gpu_ms = 0.0
    try:
        if not torch.cuda.is_available() or torch.cuda.get_device_capability()[0] < 9:
            raise RuntimeError("CUDA SM90+ unavailable")
        result["identity"] = {"gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability()), "torch": torch.__version__, "cuda": torch.version.cuda, "candidate_symbol": "torch._scaled_mm"}
        first = CASES[0]
        sentinel = linear_row(first[0], DECODE_M, first[1], first[2], first[3], args.seed)
        result["rows"]["linears"].append(sentinel)
        atomic_json(args.output.parent / "SENTINEL.json", sentinel)
        if not sentinel["pass"]:
            raise RuntimeError("first exact-shape E4M3 kernel sentinel failed")
        for case in CASES:
            if case != first:
                result["rows"]["linears"].append(linear_row(case[0], DECODE_M, case[1], case[2], case[3], args.seed))
            result["rows"]["linears"].append(linear_row(case[0], PREFILL_M, case[1], case[2], case[3], args.seed))
        head = linear_row("tied_head", DECODE_M, 5376, 262144, 1, args.seed)
        result["rows"]["head"].append(head)
        result["rows"]["attention"] = [attention_row("local_decode", 1024, 16, 256, 50, args.seed), attention_row("global_decode_peak", 4571, 4, 512, 10, args.seed)]
        result["rows"]["kv_writer"] = [bf16_kv_writer_row("local_decode", 1024, 16, 256, 50, args.seed), bf16_kv_writer_row("global_decode_peak", 4571, 4, 512, 10, args.seed)]
        rows = sum(result["rows"].values(), [])
        result["all_rows_pass"] = all(row["pass"] for row in rows)
        result["frontier"] = {"h200_all_bf16": aggregate(result["rows"]["linears"], head, result["rows"]["attention"], result["rows"]["kv_writer"], False), "h200_e4m3_compute_bf16_state": aggregate(result["rows"]["linears"], head, result["rows"]["attention"], result["rows"]["kv_writer"], True)}
        control = result["frontier"]["h200_all_bf16"]["component_floor_seconds_per_request"]
        candidate = result["frontier"]["h200_e4m3_compute_bf16_state"]["component_floor_seconds_per_request"]
        margin = 1.0 - candidate / control
        result["decision"] = {"measured_component_margin_vs_all_bf16": margin, "target_margin": FP8_MARGIN_TARGET, "target_met": margin >= FP8_MARGIN_TARGET, "component_proxy_nominee": "H200 E4M3 compute / BF16 state" if result["all_rows_pass"] and margin >= FP8_MARGIN_TARGET else None, "endpoint_nominee": None}
        for row in rows:
            for key in ("fp8_timing", "bf16_timing", "timing"):
                if key in row:
                    useful_gpu_ms += sum(row[key]["cuda_event"]["raw_ms"])
        result["pass"] = result["all_rows_pass"]
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    result["useful_gpu_seconds"] = useful_gpu_ms / 1000
    result["scientific_wall_seconds"] = time.perf_counter() - started
    atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
