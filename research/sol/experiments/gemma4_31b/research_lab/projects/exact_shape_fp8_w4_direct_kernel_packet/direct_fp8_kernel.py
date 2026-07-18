#!/usr/bin/env python3
import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import time
from pathlib import Path

import torch
import vllm
from vllm import _custom_ops as ops
from vllm.model_executor.kernels.linear.scaled_mm.cutlass import CutlassFP8ScaledMMLinearKernel

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
VLLM = "0.19.1.dev6+g6d4a8e6d2"
SOURCE_SHA = {
    "CutlassFP8ScaledMMLinearKernel": "57e51a4f4879ed5cec4fb2d5059693ec1f9f487fde76350b551625de12ed7ff7",
    "vllm._custom_ops.cutlass_scaled_mm": "510359907f2bc614eeb14dc671f0a50d484fe0dbe0e9d4bcb943f538e189d5bd",
    "vllm._custom_ops.scaled_fp8_quant": "530b9bdac543dc51b11622f6c673b7bacab0694406fc7f297cd0dad2004db643",
}
CASES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("global_qkv", 5376, 20480, 10),
    ("sliding_output", 8192, 5376, 50),
    ("global_output", 16384, 5376, 10),
    ("merged_gate_up", 5376, 43008, 60),
    ("down", 21504, 5376, 60),
)
M_DECODE = 12
M_PREFILL = 3679
OUTPUT_TOKENS = 358
RESIDUAL = 0.1646315388888889
PLANNING_CEILING = 1.3945806410831811
CONSERVATIVE_CEILING = 0.8632931049626701


def atomic(path: Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def sha_source(value: object) -> str:
    return hashlib.sha256(inspect.getsource(value).encode()).hexdigest()


def identity() -> dict[str, object]:
    observed = {
        "CutlassFP8ScaledMMLinearKernel": sha_source(CutlassFP8ScaledMMLinearKernel),
        "vllm._custom_ops.cutlass_scaled_mm": sha_source(ops.cutlass_scaled_mm),
        "vllm._custom_ops.scaled_fp8_quant": sha_source(ops.scaled_fp8_quant),
    }
    image = os.environ.get("RUNTIME_IMAGE_IDENTITY")
    return {
        "runtime_image": image,
        "vllm": vllm.__version__,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(),
        "capability": list(torch.cuda.get_device_capability()),
        "source_sha256": observed,
        "raw_path": "Fp8OnlineLinearMethod -> CutlassFP8ScaledMMLinearKernel.apply_scaled_mm -> vllm._custom_ops.cutlass_scaled_mm -> torch.ops._C.cutlass_scaled_mm",
        "producer": "vllm._custom_ops.scaled_fp8_quant",
        "pass": bool(image == IMAGE and vllm.__version__ == VLLM and torch.cuda.get_device_name() == "NVIDIA L40S" and tuple(torch.cuda.get_device_capability()) == (8, 9) and observed == SOURCE_SHA),
    }


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return {"raw_ms": values, "p50_ms": p50, "p95_ms": p95, "positive_finite": all(math.isfinite(x) and x > 0 for x in values), "p95_p50": p95 / p50 if p50 > 0 else math.inf}


def timed(fn, warmups: int, iterations: int) -> tuple[dict[str, object], torch.Tensor]:
    out = None
    for _ in range(warmups):
        out = fn()
    torch.cuda.synchronize()
    events, walls = [], []
    for _ in range(iterations):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record(); wall = time.perf_counter(); out = fn(); end.record(); end.synchronize()
        events.append(start.elapsed_time(end)); walls.append((time.perf_counter() - wall) * 1000)
    assert out is not None
    return {"warmups": warmups, "iterations": iterations, "cuda_event": distribution(events), "synchronized_wall": distribution(walls)}, out


def stable(value: dict[str, object]) -> bool:
    return bool(value["positive_finite"] and value["p95_p50"] <= 4.0)


def error_metrics(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    c, r = candidate.float(), reference.float()
    d = c - r
    rmse = float(torch.sqrt(torch.mean(d * d)))
    reference_rms = float(torch.sqrt(torch.mean(r * r)))
    normalized_rmse = rmse / max(reference_rms, 1e-12)
    max_absolute = float(d.abs().max())
    cosine = float(torch.nn.functional.cosine_similarity(c.flatten(), r.flatten(), dim=0))
    finite = bool(torch.isfinite(c).all() and torch.isfinite(r).all())
    nontrivial = bool(float(c.abs().max()) > 1e-6 and reference_rms > 1e-6)
    return {"finite": finite, "nontrivial": nontrivial, "maximum_absolute": max_absolute, "rmse": rmse, "reference_rms": reference_rms, "normalized_rmse": normalized_rmse, "cosine_similarity": cosine}


def dual_oracle(candidate: torch.Tensor, dequantized_fp32: torch.Tensor, original_bf16: torch.Tensor) -> dict[str, object]:
    kernel = error_metrics(candidate, dequantized_fp32)
    representation = error_metrics(dequantized_fp32, original_bf16)
    kernel_tolerance = {"maximum_absolute": 0.02, "normalized_rmse": 0.02, "minimum_cosine_similarity": 0.999}
    representation_tolerance = {"normalized_rmse": 0.08, "minimum_cosine_similarity": 0.99}
    kernel["tolerance"] = kernel_tolerance
    kernel["pass"] = bool(kernel["finite"] and kernel["nontrivial"] and kernel["maximum_absolute"] <= kernel_tolerance["maximum_absolute"] and kernel["normalized_rmse"] <= kernel_tolerance["normalized_rmse"] and kernel["cosine_similarity"] >= kernel_tolerance["minimum_cosine_similarity"])
    representation["tolerance"] = representation_tolerance
    representation["pass"] = bool(representation["finite"] and representation["nontrivial"] and representation["normalized_rmse"] <= representation_tolerance["normalized_rmse"] and representation["cosine_similarity"] >= representation_tolerance["minimum_cosine_similarity"])
    return {"kernel_correctness_actual_vs_dequantized_quantized_fp32": kernel, "representation_loss_dequantized_quantized_vs_original_bf16": representation, "pass": bool(kernel["pass"] and representation["pass"])}


def run_row(case: tuple[str, int, int, int], m: int, seed: int) -> dict[str, object]:
    name, k, n, multiplicity = case
    torch.manual_seed(seed + m * 17 + k * 3 + n)
    torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()
    x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    weight = torch.randn((n, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    xq, xs = ops.scaled_fp8_quant(x, scale=None)
    wq, ws = ops.scaled_fp8_quant(weight, scale=None)
    b = wq.t()
    candidate_timing, candidate = timed(lambda: ops.cutlass_scaled_mm(xq, b, scale_a=xs, scale_b=ws, out_dtype=torch.bfloat16), 2, 5)
    reference_timing, reference = timed(lambda: torch.mm(x, weight.t()), 2, 5)
    dequantized_fp32 = torch.mm(xq.float() * xs.float(), b.float() * ws.float())
    check = dual_oracle(candidate, dequantized_fp32, reference)
    passed = check["pass"] and stable(candidate_timing["cuda_event"]) and stable(candidate_timing["synchronized_wall"]) and stable(reference_timing["cuda_event"]) and stable(reference_timing["synchronized_wall"])
    row = {"case": name, "m": m, "k": k, "n": n, "architecture_multiplicity": multiplicity, "candidate_symbol": "vllm._custom_ops.cutlass_scaled_mm", "candidate_dtypes": {"a": str(xq.dtype), "b": str(b.dtype), "scale_a": str(xs.dtype), "scale_b": str(ws.dtype), "out": str(candidate.dtype)}, "layout": {"a_shape": list(xq.shape), "b_shape": list(b.shape), "b_stride": list(b.stride())}, "candidate_timing": candidate_timing, "bf16_comparator_timing": reference_timing, "oracle_from_timed_outputs": check, "allocator": {"peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()}, "pass": passed}
    del x, weight, xq, wq, b, candidate, reference, dequantized_fp32
    torch.cuda.empty_cache()
    return row


def aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    decode = [r for r in rows if r["m"] == M_DECODE]
    prefill = [r for r in rows if r["m"] == M_PREFILL]
    if len(decode) != 6 or len(prefill) != 6:
        raise RuntimeError("expected exactly six decode and six prefill rows")
    prefill_s = sum(r["architecture_multiplicity"] * r["candidate_timing"]["cuda_event"]["p50_ms"] for r in prefill) / 1000
    decode_s = sum(r["architecture_multiplicity"] * r["candidate_timing"]["cuda_event"]["p50_ms"] for r in decode) * OUTPUT_TOKENS / M_DECODE / 1000
    linear_s = prefill_s + decode_s
    combined = linear_s + RESIDUAL
    return {"prefill_linear_seconds_per_request": prefill_s, "decode_linear_seconds_per_request": decode_s, "linear_seconds_per_request": linear_s, "attention_kv_residual_floor_seconds_per_request": RESIDUAL, "linear_plus_residual_floor_seconds_per_request": combined, "planning_service_ceiling_seconds_per_request": PLANNING_CEILING, "conservative_service_ceiling_seconds_per_request": CONSERVATIVE_CEILING, "planning_falsified_by_lower_bound": combined > PLANNING_CEILING, "conservative_falsified_by_lower_bound": combined > CONSERVATIVE_CEILING, "decode_normalization": "architecture weighting, multiply by 358, divide by c12 exactly once", "prefill_normalization": "architecture weighting, no concurrency division", "omissions": ["vocabulary head", "KV cache writer", "norm/rotary/activation/sampling/scheduler/service overhead"], "admission_permitted_if_below": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("primary", "conditional"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260717)
    args = parser.parse_args()
    result = {"schema_version": 1, "type": "gemma4_exact_shape_direct_cutlass_fp8", "stage": args.stage, "semantics": "checkpoint-free deterministic cost-mechanism proxy; no model quality or endpoint claim", "identity": identity(), "rows": [], "pass": False}
    try:
        if not result["identity"]["pass"]:
            raise RuntimeError("exact runtime/source/GPU identity mismatch")
        selected = ((CASES[0], M_DECODE),) if args.stage == "primary" else tuple((case, m) for case in CASES for m in (M_DECODE, M_PREFILL))
        result["rows"] = [run_row(case, m, args.seed) for case, m in selected]
        result["all_rows_pass"] = all(row["pass"] for row in result["rows"])
        if args.stage == "primary":
            result["sentinel"] = {"pass": result["all_rows_pass"], "required_retrieval_before_sweep": True, "row": result["rows"][0]}
            result["pass"] = result["all_rows_pass"]
        else:
            result["aggregation"] = aggregate(result["rows"])
            result["pass"] = result["all_rows_pass"]
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
