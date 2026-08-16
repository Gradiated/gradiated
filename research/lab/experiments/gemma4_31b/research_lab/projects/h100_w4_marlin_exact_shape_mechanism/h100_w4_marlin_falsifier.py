#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import time
from pathlib import Path

try:
    import torch
except ModuleNotFoundError:
    torch = None

from h100_w4_contract import analytic_row, paired_aggregate, selected


IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
VLLM = "0.19.1.dev6+g6d4a8e6d2"
GPU = "NVIDIA H100 80GB HBM3"
AWQ_MARLIN_CLASS_SHA256 = "721bb23b98cd678232b87a24757317cc9066bfa13f983ca2bf71a3afbaf6ed97"
MARLIN_KERNEL_CLASS_SHA256 = "58f5a0b17741584f419d002965de0f0f30660241521e8f88e69c9faaa4de1e27"
MARLIN_GEMM_WRAPPER_SHA256 = "c022167a5f7b1b3a4e3d7a0dda588cdf6c88151d789541e88599691108aef2cc"
QUANTIZE_WEIGHTS_SHA256 = "0409ddc9ed6deaad58512a5bde2ce767b71427d8a899c7b52aec8a2b859f4b43"
AWQ_PACK_SHA256 = "2038812ad218d4c11b3267b72c4600d2c298696ee4c55354476ceccbeebeb82e"
GROUP_SIZE = 128
WARMUPS = 2
ITERATIONS = 5
COLD_ITERATIONS = 3
EVICTION_BYTES = 128 * 1024**2


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def source_sha(value: object) -> str:
    return hashlib.sha256(inspect.getsource(value).encode()).hexdigest()


def require_torch() -> None:
    if torch is None:
        raise RuntimeError("the exact CUDA image with torch and vLLM is required")


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return {
        "raw_ms": values,
        "p50_ms": p50,
        "p95_ms": p95,
        "positive_finite": all(math.isfinite(value) and value > 0 for value in values),
        "p95_p50": p95 / p50 if p50 else math.inf,
    }


def timed(fn, iterations: int, evict=None):
    output = None
    for _ in range(WARMUPS):
        output = fn()
    torch.cuda.synchronize()
    events, walls = [], []
    for _ in range(iterations):
        if evict is not None:
            evict()
            torch.cuda.synchronize()
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        wall = time.perf_counter()
        output = fn()
        end.record()
        end.synchronize()
        events.append(start.elapsed_time(end))
        walls.append((time.perf_counter() - wall) * 1000)
    return {
        "warmups": WARMUPS,
        "iterations": iterations,
        "cuda_event": distribution(events),
        "synchronized_wall": distribution(walls),
    }, output


def metrics(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    candidate_fp32 = candidate.float()
    reference_fp32 = reference.float()
    delta = candidate_fp32 - reference_fp32
    rmse = float(torch.sqrt(torch.mean(delta * delta)))
    reference_rms = float(torch.sqrt(torch.mean(reference_fp32 * reference_fp32)))
    return {
        "finite": bool(torch.isfinite(candidate_fp32).all() and torch.isfinite(reference_fp32).all()),
        "nontrivial": bool(float(candidate_fp32.abs().max()) > 1e-6 and reference_rms > 1e-6),
        "maximum_absolute": float(delta.abs().max()),
        "normalized_rmse": rmse / max(reference_rms, 1e-12),
        "cosine_similarity": float(torch.nn.functional.cosine_similarity(candidate_fp32.flatten(), reference_fp32.flatten(), dim=0)),
    }


def dual_oracle(candidate, dequantized_output, original_output):
    kernel = metrics(candidate, dequantized_output)
    representation = metrics(dequantized_output, original_output)
    kernel["tolerance"] = {"normalized_rmse": 0.03, "minimum_cosine_similarity": 0.999}
    representation["tolerance"] = {"normalized_rmse": 0.16, "minimum_cosine_similarity": 0.98}
    kernel["pass"] = bool(kernel["finite"] and kernel["nontrivial"] and kernel["normalized_rmse"] <= 0.03 and kernel["cosine_similarity"] >= 0.999)
    representation["pass"] = bool(representation["finite"] and representation["nontrivial"] and representation["normalized_rmse"] <= 0.16 and representation["cosine_similarity"] >= 0.98)
    return {
        "kernel_correctness_actual_vs_dequantized_quantized": kernel,
        "representation_loss_dequantized_quantized_vs_original_bf16": representation,
        "pass": bool(kernel["pass"] and representation["pass"]),
    }


def runtime_imports():
    require_torch()
    import vllm
    from vllm.model_executor.layers.quantization.awq_marlin import AWQMarlinConfig, AWQMarlinLinearMethod
    from vllm.model_executor.layers.quantization.utils.quant_utils import awq_pack, quantize_weights
    from vllm.scalar_type import scalar_types

    return vllm, AWQMarlinConfig, AWQMarlinLinearMethod, awq_pack, quantize_weights, scalar_types


def runtime_identity(AWQMarlinLinearMethod, method, quantize_weights, awq_pack) -> dict[str, object]:
    require_torch()
    import vllm
    from vllm import _custom_ops as ops

    kernel = method.kernel
    observed = {
        "AWQMarlinLinearMethod": source_sha(AWQMarlinLinearMethod),
        "selected_kernel": source_sha(type(kernel)),
        "vllm._custom_ops.marlin_gemm": source_sha(ops.marlin_gemm),
        "quantize_weights": source_sha(quantize_weights),
        "awq_pack": source_sha(awq_pack),
    }
    image = os.environ.get("RUNTIME_IMAGE_IDENTITY")
    max_shared = torch.cuda.get_device_properties(0).shared_memory_per_block_optin
    return {
        "runtime_image": image,
        "vllm": vllm.__version__,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(),
        "capability": list(torch.cuda.get_device_capability()),
        "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
        "max_optin_shared_bytes_per_block": max_shared,
        "consumer": f"{type(method).__module__}.{type(method).__name__}.apply",
        "selected_kernel": f"{type(kernel).__module__}.{type(kernel).__name__}.apply_weights",
        "raw_symbol": "vllm._custom_ops.marlin_gemm -> torch.ops._C.marlin_gemm",
        "producer": "vllm.model_executor.layers.quantization.utils.quant_utils.quantize_weights + awq_pack",
        "source_sha256": observed,
        "pass": bool(
            image == IMAGE
            and vllm.__version__ == VLLM
            and torch.cuda.get_device_name() == GPU
            and tuple(torch.cuda.get_device_capability()) == (9, 0)
            and type(kernel).__name__ == "MarlinLinearKernel"
            and observed["AWQMarlinLinearMethod"] == AWQ_MARLIN_CLASS_SHA256
            and observed["selected_kernel"] == MARLIN_KERNEL_CLASS_SHA256
            and observed["vllm._custom_ops.marlin_gemm"] == MARLIN_GEMM_WRAPPER_SHA256
            and observed["quantize_weights"] == QUANTIZE_WEIGHTS_SHA256
            and observed["awq_pack"] == AWQ_PACK_SHA256
        ),
    }


def make_case(case, seed: int):
    _, k, n, _ = case
    vllm, Config, Method, awq_pack, quantize_weights, scalar_types = runtime_imports()
    del vllm
    torch.manual_seed(seed + k * 3 + n)
    column_scale = 0.5 + (torch.arange(n, device="cuda", dtype=torch.float32) % 17) / 16
    original = (torch.randn((k, n), device="cuda", dtype=torch.bfloat16) * column_scale / math.sqrt(k)).to(torch.bfloat16)
    dequantized, quantized, scales, zero_points = quantize_weights(original, scalar_types.uint4, GROUP_SIZE, zero_points=True)
    packed_weight = awq_pack(quantized, 4, k, n)
    packed_zero_points = awq_pack(zero_points, 4, k // GROUP_SIZE, n)
    config = Config(4, GROUP_SIZE, True, False, None, {})
    method = Method(config)
    layer = torch.nn.Module()
    with torch.device("cuda"):
        method.create_weights(layer, k, [n], k, n, torch.bfloat16)
    layer.qweight.data.copy_(packed_weight)
    layer.qzeros.data.copy_(packed_zero_points)
    layer.scales.data.copy_(scales)
    method.process_weights_after_loading(layer)
    return method, layer, original, dequantized, runtime_identity(Method, method, quantize_weights, awq_pack)


def stable(timing: dict[str, object]) -> bool:
    return bool(timing["cuda_event"]["positive_finite"] and timing["cuda_event"]["p95_p50"] <= 4.0)


def run_row(case, m: int, seed: int, prepared=None) -> dict[str, object]:
    require_torch()
    name, k, n, multiplicity = case
    torch.manual_seed(seed + m * 17 + k * 3 + n)
    torch.cuda.reset_peak_memory_stats()
    method, layer, original, dequantized, identity = prepared or make_case(case, seed)
    if not identity["pass"]:
        raise RuntimeError(f"exact runtime/source/H100 identity mismatch: {identity}")
    x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16)
    eviction = torch.empty((EVICTION_BYTES,), device="cuda", dtype=torch.uint8)

    def evict():
        eviction.random_(0, 256)

    def candidate_call():
        torch.cuda.nvtx.range_push("marlin_candidate")
        output = method.apply(layer, x)
        torch.cuda.nvtx.range_pop()
        return output

    def bf16_call():
        torch.cuda.nvtx.range_push("bf16_comparator")
        output = torch.mm(x, original)
        torch.cuda.nvtx.range_pop()
        return output

    warm_candidate, candidate = timed(candidate_call, ITERATIONS)
    cold_candidate, candidate_cold = timed(candidate_call, COLD_ITERATIONS, evict)
    warm_bf16, _ = timed(bf16_call, ITERATIONS)
    cold_bf16, original_output = timed(bf16_call, COLD_ITERATIONS, evict)
    dequantized_output = torch.mm(x.float(), dequantized.float())
    check = dual_oracle(candidate_cold, dequantized_output, original_output)
    passed = bool(check["pass"] and stable(warm_candidate) and stable(cold_candidate) and stable(cold_bf16))
    row = {
        "case": name,
        "m": m,
        "k": k,
        "n": n,
        "architecture_multiplicity": multiplicity,
        "identity": identity,
        "packing": {
            "bits": 4,
            "group_size": GROUP_SIZE,
            "zero_points": True,
            "checkpoint_layout": "AWQ int32-packed on output dim with [0,2,4,6,1,3,5,7] nibble interleave",
            "consumer_conversion": "AWQ output-packed -> standard input-packed -> gptq_marlin_repack + scale/zero-point permutation",
        },
        "warm_candidate_timing": warm_candidate,
        "cold_candidate_timing": cold_candidate,
        "warm_bf16_comparator_timing": warm_bf16,
        "cold_bf16_comparator_timing": cold_bf16,
        "warm_to_cold_candidate_ratio": float(warm_candidate["cuda_event"]["p50_ms"]) / float(cold_candidate["cuda_event"]["p50_ms"]),
        "dual_oracle_from_timed_outputs": check,
        "analytic_mechanism": analytic_row(case, m),
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": bool(passed and stable(warm_bf16)),
    }
    del x, eviction, candidate, candidate_cold, original_output, dequantized_output
    if prepared is None:
        del method, layer, original, dequantized
        torch.cuda.empty_cache()
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("sentinel", "sweep", "profile"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--case", choices=tuple(entry[0][0] for entry in selected("sweep")[::4]))
    parser.add_argument("--m", type=int, choices=(8, 16, 32, 3679))
    args = parser.parse_args()
    result = {
        "schema_version": 1,
        "type": "gemma4_h100_exact_shape_awq_marlin_w4a16",
        "stage": args.stage,
        "semantics": "checkpoint-free deterministic mechanism proxy; no checkpoint quality or endpoint claim",
        "rows": [],
        "pass": False,
    }
    try:
        chosen = selected(args.stage) if args.stage != "profile" else tuple(
            (case, args.m) for case in (entry[0] for entry in selected("sweep")[::4]) if case[0] == args.case
        )
        if args.stage == "profile" and (args.case is None or args.m is None or len(chosen) != 1):
            raise ValueError("profile stage requires one valid --case and --m")
        if args.stage == "sweep":
            for case in (entry[0] for entry in selected("sweep")[::4]):
                prepared = make_case(case, args.seed)
                for m in (8, 16, 32, 3679):
                    result["rows"].append(run_row(case, m, args.seed, prepared))
                del prepared
                torch.cuda.empty_cache()
        else:
            result["rows"] = [run_row(case, m, args.seed) for case, m in chosen]
        result["all_rows_pass"] = all(row["pass"] for row in result["rows"])
        if args.stage == "sentinel":
            result["sentinel"] = {"pass": result["all_rows_pass"], "row": result["rows"][0]}
        elif args.stage == "sweep":
            result["aggregation"] = paired_aggregate(result["rows"])
        result["pass"] = result["all_rows_pass"]
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
