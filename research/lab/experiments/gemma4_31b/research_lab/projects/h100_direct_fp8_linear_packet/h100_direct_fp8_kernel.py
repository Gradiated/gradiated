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

from h100_contract import aggregate, selected

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
VLLM = "0.19.1.dev6+g6d4a8e6d2"
GPU = "NVIDIA H100 80GB HBM3"
SOURCE_SHA = {
    "CutlassFP8ScaledMMLinearKernel": "57e51a4f4879ed5cec4fb2d5059693ec1f9f487fde76350b551625de12ed7ff7",
    "vllm._custom_ops.cutlass_scaled_mm": "510359907f2bc614eeb14dc671f0a50d484fe0dbe0e9d4bcb943f538e189d5bd",
    "vllm._custom_ops.scaled_fp8_quant": "530b9bdac543dc51b11622f6c673b7bacab0694406fc7f297cd0dad2004db643",
}


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
    gpu = torch.cuda.get_device_name()
    capability = tuple(torch.cuda.get_device_capability())
    return {
        "runtime_image": image,
        "vllm": vllm.__version__,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": gpu,
        "capability": list(capability),
        "source_sha256": observed,
        "raw_path": "Fp8OnlineLinearMethod -> CutlassFP8ScaledMMLinearKernel.apply_scaled_mm -> vllm._custom_ops.cutlass_scaled_mm -> torch.ops._C.cutlass_scaled_mm",
        "producer": "vllm._custom_ops.scaled_fp8_quant",
        "pass": bool(
            image == IMAGE
            and vllm.__version__ == VLLM
            and gpu == GPU
            and capability == (9, 0)
            and observed == SOURCE_SHA
        ),
    }


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return {
        "raw_ms": values,
        "p50_ms": p50,
        "p95_ms": p95,
        "positive_finite": all(math.isfinite(x) and x > 0 for x in values),
        "p95_p50": p95 / p50 if p50 > 0 else math.inf,
    }


def timed(fn, warmups: int, iterations: int):
    out = None
    for _ in range(warmups):
        out = fn()
    torch.cuda.synchronize()
    events, walls = [], []
    for _ in range(iterations):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        wall = time.perf_counter()
        out = fn()
        end.record()
        end.synchronize()
        events.append(start.elapsed_time(end))
        walls.append((time.perf_counter() - wall) * 1000)
    assert out is not None
    return {
        "warmups": warmups,
        "iterations": iterations,
        "cuda_event": distribution(events),
        "synchronized_wall": distribution(walls),
    }, out


def stable(value: dict[str, object]) -> bool:
    return bool(value["positive_finite"] and value["p95_p50"] <= 4.0)


def error_metrics(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    c, r = candidate.float(), reference.float()
    delta = c - r
    rmse = float(torch.sqrt(torch.mean(delta * delta)))
    reference_rms = float(torch.sqrt(torch.mean(r * r)))
    return {
        "finite": bool(torch.isfinite(c).all() and torch.isfinite(r).all()),
        "nontrivial": bool(float(c.abs().max()) > 1e-6 and reference_rms > 1e-6),
        "maximum_absolute": float(delta.abs().max()),
        "rmse": rmse,
        "reference_rms": reference_rms,
        "normalized_rmse": rmse / max(reference_rms, 1e-12),
        "cosine_similarity": float(torch.nn.functional.cosine_similarity(c.flatten(), r.flatten(), dim=0)),
    }


def dual_oracle(candidate, dequantized_fp32, original_bf16):
    kernel = error_metrics(candidate, dequantized_fp32)
    representation = error_metrics(dequantized_fp32, original_bf16)
    kernel_tolerance = {
        "maximum_absolute": 0.02,
        "normalized_rmse": 0.02,
        "minimum_cosine_similarity": 0.999,
    }
    representation_tolerance = {
        "normalized_rmse": 0.08,
        "minimum_cosine_similarity": 0.99,
    }
    kernel["tolerance"] = kernel_tolerance
    kernel["pass"] = bool(
        kernel["finite"]
        and kernel["nontrivial"]
        and kernel["maximum_absolute"] <= kernel_tolerance["maximum_absolute"]
        and kernel["normalized_rmse"] <= kernel_tolerance["normalized_rmse"]
        and kernel["cosine_similarity"] >= kernel_tolerance["minimum_cosine_similarity"]
    )
    representation["tolerance"] = representation_tolerance
    representation["pass"] = bool(
        representation["finite"]
        and representation["nontrivial"]
        and representation["normalized_rmse"] <= representation_tolerance["normalized_rmse"]
        and representation["cosine_similarity"] >= representation_tolerance["minimum_cosine_similarity"]
    )
    return {
        "kernel_correctness_actual_vs_dequantized_quantized_fp32": kernel,
        "representation_loss_dequantized_quantized_vs_original_bf16": representation,
        "pass": bool(kernel["pass"] and representation["pass"]),
    }


def run_row(case, m: int, seed: int) -> dict[str, object]:
    name, k, n, multiplicity = case
    torch.manual_seed(seed + m * 17 + k * 3 + n)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    weight = torch.randn((n, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    xq, xs = ops.scaled_fp8_quant(x, scale=None)
    wq, ws = ops.scaled_fp8_quant(weight, scale=None)
    b = wq.t()
    candidate_timing, candidate = timed(
        lambda: ops.cutlass_scaled_mm(xq, b, scale_a=xs, scale_b=ws, out_dtype=torch.bfloat16),
        2,
        5,
    )
    reference_timing, reference = timed(lambda: torch.mm(x, weight.t()), 2, 5)
    dequantized_fp32 = torch.mm(xq.float() * xs.float(), b.float() * ws.float())
    check = dual_oracle(candidate, dequantized_fp32, reference)
    passed = bool(
        check["pass"]
        and stable(candidate_timing["cuda_event"])
        and stable(candidate_timing["synchronized_wall"])
        and stable(reference_timing["cuda_event"])
        and stable(reference_timing["synchronized_wall"])
    )
    row = {
        "case": name,
        "m": m,
        "k": k,
        "n": n,
        "architecture_multiplicity": multiplicity,
        "candidate_symbol": "vllm._custom_ops.cutlass_scaled_mm",
        "candidate_dtypes": {
            "a": str(xq.dtype),
            "b": str(b.dtype),
            "scale_a": str(xs.dtype),
            "scale_b": str(ws.dtype),
            "out": str(candidate.dtype),
        },
        "layout": {"a_shape": list(xq.shape), "b_shape": list(b.shape), "b_stride": list(b.stride())},
        "candidate_timing": candidate_timing,
        "bf16_comparator_timing": reference_timing,
        "oracle_from_timed_outputs": check,
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": passed,
    }
    del x, weight, xq, wq, b, candidate, reference, dequantized_fp32
    torch.cuda.empty_cache()
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("primary", "conditional"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260717)
    args = parser.parse_args()
    result = {
        "schema_version": 1,
        "type": "gemma4_h100_exact_shape_direct_cutlass_fp8",
        "stage": args.stage,
        "semantics": "checkpoint-free deterministic cost-mechanism proxy; no model quality or endpoint claim",
        "identity": identity(),
        "rows": [],
        "pass": False,
    }
    try:
        if not result["identity"]["pass"]:
            raise RuntimeError("exact runtime/source/H100 identity mismatch")
        result["rows"] = [run_row(case, m, args.seed) for case, m in selected(args.stage)]
        result["all_rows_pass"] = all(row["pass"] for row in result["rows"])
        if args.stage == "primary":
            result["sentinel"] = {
                "pass": result["all_rows_pass"],
                "required_retrieval_before_sweep": True,
                "row": result["rows"][0],
            }
        else:
            result["aggregation"] = aggregate(result["rows"])
        result["pass"] = result["all_rows_pass"]
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
