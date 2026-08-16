#!/usr/bin/env python3
import argparse
import json
import math
import os
import statistics
import time
from pathlib import Path

import torch
import torch.nn.functional as F


MODEL = "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
CASES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("global_qkv", 5376, 20480, 10),
    ("sliding_output", 8192, 5376, 50),
    ("global_output", 16384, 5376, 10),
    ("merged_gate_up", 5376, 43008, 60),
    ("down", 21504, 5376, 60),
)
DECODE_M = 12
PREFILL_M = 3679
OUTPUT_TOKENS = 358
H200_PLANNING_USD_PER_HOUR = 3.25
FP8_MARGIN_TARGET = 0.20


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return {
        "raw_ms": values,
        "p50_ms": p50,
        "p95_ms": p95,
        "p95_p50": p95 / p50,
        "positive_finite": all(math.isfinite(value) and value > 0 for value in values),
    }


def timed(call, warmups: int = 2, iterations: int = 5):
    output = None
    for _ in range(warmups):
        output = call()
    torch.cuda.synchronize()
    events = []
    walls = []
    for _ in range(iterations):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        wall_start = time.perf_counter()
        output = call()
        end.record()
        end.synchronize()
        events.append(start.elapsed_time(end))
        walls.append((time.perf_counter() - wall_start) * 1000)
    return {
        "warmups": warmups,
        "iterations": iterations,
        "cuda_event": distribution(events),
        "synchronized_wall": distribution(walls),
    }, output


def error_metrics(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    candidate_float = candidate.float()
    reference_float = reference.float()
    delta = candidate_float - reference_float
    rmse = float(torch.sqrt(torch.mean(delta * delta)))
    reference_rms = float(torch.sqrt(torch.mean(reference_float * reference_float)))
    normalized_rmse = rmse / max(reference_rms, 1e-12)
    cosine = float(F.cosine_similarity(candidate_float.flatten(), reference_float.flatten(), dim=0))
    return {
        "finite": bool(torch.isfinite(candidate_float).all() and torch.isfinite(reference_float).all()),
        "nontrivial": bool(reference_rms > 1e-6 and float(candidate_float.abs().max()) > 1e-6),
        "maximum_absolute": float(delta.abs().max()),
        "normalized_rmse": normalized_rmse,
        "cosine_similarity": cosine,
    }


def scaled_fp8(value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    scale = value.abs().max().float().clamp_min(1e-12) / 448.0
    quantized = (value.float() / scale).clamp(-448.0, 448.0).to(torch.float8_e4m3fn)
    return quantized, scale


def scaled_mm(a: torch.Tensor, b: torch.Tensor, scale_a: torch.Tensor, scale_b: torch.Tensor) -> torch.Tensor:
    result = torch._scaled_mm(a, b, scale_a=scale_a, scale_b=scale_b, out_dtype=torch.bfloat16)
    return result[0] if isinstance(result, tuple) else result


def linear_row(name: str, m: int, k: int, n: int, multiplicity: int, seed: int) -> dict[str, object]:
    torch.manual_seed(seed + m * 17 + k * 3 + n)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    activation = torch.randn((m, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    weight = torch.randn((n, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    activation_fp8, activation_scale = scaled_fp8(activation)
    weight_fp8, weight_scale = scaled_fp8(weight)
    weight_fp8_t = weight_fp8.t()
    fp8_timing, fp8_output = timed(
        lambda: scaled_mm(activation_fp8, weight_fp8_t, activation_scale, weight_scale)
    )
    bf16_timing, bf16_output = timed(lambda: torch.mm(activation, weight.t()))
    dequantized_output = torch.mm(
        activation_fp8.float() * activation_scale,
        weight_fp8_t.float() * weight_scale,
    )
    kernel = error_metrics(fp8_output, dequantized_output)
    representation = error_metrics(dequantized_output, bf16_output)
    kernel_pass = bool(
        kernel["finite"]
        and kernel["nontrivial"]
        and kernel["normalized_rmse"] <= 0.02
        and kernel["cosine_similarity"] >= 0.999
    )
    representation_pass = bool(
        representation["finite"]
        and representation["nontrivial"]
        and representation["normalized_rmse"] <= 0.08
        and representation["cosine_similarity"] >= 0.99
    )
    stable = all(
        timing[distribution_name]["positive_finite"]
        and timing[distribution_name]["p95_p50"] <= 4.0
        for timing in (fp8_timing, bf16_timing)
        for distribution_name in ("cuda_event", "synchronized_wall")
    )
    row = {
        "kind": "linear",
        "case": name,
        "m": m,
        "k": k,
        "n": n,
        "architecture_multiplicity": multiplicity,
        "candidate_symbol": "torch._scaled_mm",
        "candidate_format": "E4M3FN per-tensor scaled inputs, BF16 output",
        "fp8_timing": fp8_timing,
        "bf16_timing": bf16_timing,
        "oracle": {
            "kernel_actual_vs_dequantized_fp32": {**kernel, "pass": kernel_pass},
            "representation_vs_original_bf16": {**representation, "pass": representation_pass},
            "pass": kernel_pass and representation_pass,
        },
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": bool(stable and kernel_pass and representation_pass),
    }
    del activation, weight, activation_fp8, weight_fp8, weight_fp8_t
    del fp8_output, bf16_output, dequantized_output
    torch.cuda.empty_cache()
    return row


def attention_row(case: str, context: int, kv_heads: int, head_dim: int, multiplicity: int, seed: int) -> dict[str, object]:
    torch.manual_seed(seed + context + head_dim)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    query_heads = 32
    query = torch.randn((DECODE_M, query_heads, 1, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)
    key = torch.randn((DECODE_M, kv_heads, context, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)
    value = torch.randn((DECODE_M, kv_heads, context, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)
    call = lambda: F.scaled_dot_product_attention(query, key, value, enable_gqa=True)
    timing, output = timed(call)
    repeat = query_heads // kv_heads
    key_reference = key.repeat_interleave(repeat, dim=1).float()
    value_reference = value.repeat_interleave(repeat, dim=1).float()
    scores = torch.matmul(query.float(), key_reference.transpose(-2, -1)) / math.sqrt(head_dim)
    reference = torch.matmul(torch.softmax(scores, dim=-1), value_reference)
    oracle = error_metrics(output, reference)
    passed = bool(
        oracle["finite"]
        and oracle["nontrivial"]
        and oracle["normalized_rmse"] <= 0.02
        and oracle["cosine_similarity"] >= 0.999
        and timing["cuda_event"]["positive_finite"]
        and timing["cuda_event"]["p95_p50"] <= 4.0
    )
    row = {
        "kind": "attention_shared_bf16_residual",
        "case": case,
        "m": DECODE_M,
        "context": context,
        "query_heads": query_heads,
        "kv_heads": kv_heads,
        "head_dim": head_dim,
        "architecture_multiplicity": multiplicity,
        "consumer": "torch.nn.functional.scaled_dot_product_attention(enable_gqa=True)",
        "timing": timing,
        "oracle": {**oracle, "pass": passed},
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": passed,
    }
    del query, key, value, output, key_reference, value_reference, scores, reference
    torch.cuda.empty_cache()
    return row


def kv_writer_row(case: str, context: int, heads: int, head_dim: int, multiplicity: int, seed: int) -> dict[str, object]:
    torch.manual_seed(seed + context + heads)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    source = torch.randn((DECODE_M, 2, heads, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)
    slots = torch.arange(DECODE_M, device="cuda")
    bf16_cache = torch.empty((context, 2, heads, head_dim), device="cuda", dtype=torch.bfloat16)
    fp8_cache = torch.empty((context, 2, heads, head_dim), device="cuda", dtype=torch.float8_e5m2)
    bf16_timing, _ = timed(lambda: bf16_cache.index_copy_(0, slots, source), iterations=7)
    fp8_timing, _ = timed(lambda: fp8_cache.index_copy_(0, slots, source.to(torch.float8_e5m2)), iterations=7)
    oracle = error_metrics(fp8_cache.index_select(0, slots).bfloat16(), source)
    passed = bool(
        oracle["finite"]
        and oracle["nontrivial"]
        and oracle["normalized_rmse"] <= 0.16
        and oracle["cosine_similarity"] >= 0.98
        and all(
            timing["cuda_event"]["positive_finite"] and timing["cuda_event"]["p95_p50"] <= 4.0
            for timing in (bf16_timing, fp8_timing)
        )
    )
    row = {
        "kind": "kv_writer",
        "case": case,
        "m": DECODE_M,
        "context": context,
        "heads": heads,
        "head_dim": head_dim,
        "architecture_multiplicity": multiplicity,
        "bf16_timing": bf16_timing,
        "fp8_e5m2_timing": fp8_timing,
        "oracle": {**oracle, "pass": passed},
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": passed,
    }
    del source, slots, bf16_cache, fp8_cache
    torch.cuda.empty_cache()
    return row


def p50(row: dict[str, object], precision: str) -> float:
    if row["kind"] == "linear":
        return float(row[f"{precision}_timing"]["cuda_event"]["p50_ms"])
    if row["kind"] == "kv_writer":
        key = "fp8_e5m2_timing" if precision == "fp8" else "bf16_timing"
        return float(row[key]["cuda_event"]["p50_ms"])
    return float(row["timing"]["cuda_event"]["p50_ms"])


def aggregate(linears: list[dict[str, object]], head: dict[str, object], attention: list[dict[str, object]], kv: list[dict[str, object]], precision: str) -> dict[str, object]:
    prefill_ms = sum(row["architecture_multiplicity"] * p50(row, precision) for row in linears if row["m"] == PREFILL_M)
    decode_ms = sum(row["architecture_multiplicity"] * p50(row, precision) for row in linears if row["m"] == DECODE_M)
    head_ms = p50(head, precision)
    attention_ms = sum(row["architecture_multiplicity"] * p50(row, precision) for row in attention)
    kv_ms = sum(row["architecture_multiplicity"] * p50(row, precision) for row in kv)
    decode_scale = OUTPUT_TOKENS / DECODE_M / 1000
    components = {
        "prefill_linears_seconds_per_request": prefill_ms / 1000,
        "decode_linears_seconds_per_request": decode_ms * decode_scale,
        "tied_head_seconds_per_request": head_ms * decode_scale,
        "shared_bf16_attention_seconds_per_request": attention_ms * decode_scale,
        "kv_writer_seconds_per_request": kv_ms * decode_scale,
    }
    total = sum(components.values())
    return {
        **components,
        "component_floor_seconds_per_request": total,
        "planning_usd_per_million_requests": total / 3600 * H200_PLANNING_USD_PER_HOUR * 1_000_000,
        "planning_rate_usd_per_gpu_hour": H200_PLANNING_USD_PER_HOUR,
        "decode_normalization": "architecture weighting, multiply by 358, divide by c12 exactly once",
        "omissions": ["prefill attention", "norm/rotary/activation/sampling/scheduler/service overhead", "FP8 KV attention consumer", "queueing and headroom"],
        "claim_scope": "measured component lower bound, not full-model throughput or endpoint cost",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260718)
    args = parser.parse_args()
    started = time.perf_counter()
    result = {
        "schema_version": 1,
        "type": "gemma4_h200_bf16_fp8_exact_shape_falsifier",
        "model": MODEL,
        "semantics": "checkpoint-free deterministic component-cost falsifier; no endpoint or model-quality claim",
        "hypothesis": "H200 native E4M3 exact-shape component floor is at least 20% below BF16 with passing numerical oracles",
        "rows": {"linears": [], "head": [], "attention": [], "kv_writer": []},
        "pass": False,
    }
    useful_gpu_ms = 0.0
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")
        capability = torch.cuda.get_device_capability()
        if capability[0] < 9:
            raise RuntimeError(f"native FP8 requires SM90+, observed {capability}")
        result["identity"] = {
            "gpu": torch.cuda.get_device_name(),
            "capability": list(capability),
            "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "fp8_dtype": str(torch.float8_e4m3fn),
            "candidate_symbol": "torch._scaled_mm",
        }
        sentinel_case = CASES[0]
        sentinel = linear_row(
            sentinel_case[0], DECODE_M, sentinel_case[1], sentinel_case[2], sentinel_case[3], args.seed
        )
        result["rows"]["linears"].append(sentinel)
        atomic_json(args.output.parent / "SENTINEL.json", sentinel)
        if not sentinel["pass"]:
            raise RuntimeError("first exact-shape real FP8 kernel sentinel failed")
        for case in CASES:
            if case != CASES[0]:
                result["rows"]["linears"].append(
                    linear_row(case[0], DECODE_M, case[1], case[2], case[3], args.seed)
                )
            result["rows"]["linears"].append(
                linear_row(case[0], PREFILL_M, case[1], case[2], case[3], args.seed)
            )
        head = linear_row("tied_head", DECODE_M, 5376, 262144, 1, args.seed)
        result["rows"]["head"].append(head)
        result["rows"]["attention"] = [
            attention_row("local_decode", 1024, 16, 256, 50, args.seed),
            attention_row("global_decode_peak", 4571, 4, 512, 10, args.seed),
        ]
        result["rows"]["kv_writer"] = [
            kv_writer_row("local_decode", 1024, 16, 256, 50, args.seed),
            kv_writer_row("global_decode_peak", 4571, 4, 512, 10, args.seed),
        ]
        rows = sum(result["rows"].values(), [])
        result["all_rows_pass"] = all(row["pass"] for row in rows)
        result["frontier"] = {
            "h200_bf16": aggregate(result["rows"]["linears"], head, result["rows"]["attention"], result["rows"]["kv_writer"], "bf16"),
            "h200_fp8_e4m3_weights_activations_e5m2_kv_writer": aggregate(result["rows"]["linears"], head, result["rows"]["attention"], result["rows"]["kv_writer"], "fp8"),
        }
        bf16 = result["frontier"]["h200_bf16"]["component_floor_seconds_per_request"]
        fp8 = result["frontier"]["h200_fp8_e4m3_weights_activations_e5m2_kv_writer"]["component_floor_seconds_per_request"]
        margin = 1.0 - fp8 / bf16
        result["decision"] = {
            "measured_component_margin_vs_bf16": margin,
            "target_margin": FP8_MARGIN_TARGET,
            "target_met": margin >= FP8_MARGIN_TARGET,
            "endpoint_nominee": "H200 FP8" if result["all_rows_pass"] and margin >= FP8_MARGIN_TARGET else None,
        }
        for row in rows:
            for key in ("fp8_timing", "bf16_timing", "fp8_e5m2_timing", "timing"):
                if key in row:
                    useful_gpu_ms += sum(row[key]["cuda_event"]["raw_ms"])
        result["pass"] = bool(result["all_rows_pass"])
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    result["useful_gpu_seconds"] = useful_gpu_ms / 1000
    result["scientific_wall_seconds"] = time.perf_counter() - started
    atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
