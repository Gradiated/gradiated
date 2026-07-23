from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import pathlib
import statistics


FP8_UTILS_SHA256 = "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9"
GATE_UP_K = 5376
GATE_UP_N = 43008


def append(row: dict[str, object]) -> None:
    path = pathlib.Path(os.environ["GATE_UP_AUDIT"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def timings(callable, warmups: int = 5, repetitions: int = 30) -> list[float]:
    import torch

    for _ in range(warmups):
        callable()
    torch.cuda.synchronize()
    samples = []
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        callable()
        end.record()
        end.synchronize()
        samples.append(float(start.elapsed_time(end)) * 1000.0)
    return samples


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "minimum_us": min(values),
        "median_us": statistics.median(values),
        "p90_us": percentile(values, 0.9),
        "maximum_us": max(values),
        "mean_us": statistics.fmean(values),
    }


def load_candidate():
    path = pathlib.Path(os.environ["GATE_UP_MODULE"])
    spec = importlib.util.spec_from_file_location("gemma4_fp8_gate_up_multicast", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"candidate module cannot be loaded:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metrics(torch, reference, output) -> dict[str, float | int]:
    reference_float = reference.float()
    output_float = output.float()
    difference = output_float - reference_float
    denominator = torch.linalg.vector_norm(reference_float)
    return {
        "relative_l2": float((torch.linalg.vector_norm(difference) / denominator).item()),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                reference_float.flatten(), output_float.flatten(), dim=0
            ).item()
        ),
        "max_absolute_error": float(difference.abs().max().item()),
        "reference_nonfinite": int((~torch.isfinite(reference_float)).sum().item()),
        "candidate_nonfinite": int((~torch.isfinite(output_float)).sum().item()),
    }


def install() -> None:
    import torch
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization import fp8_utils

    source = pathlib.Path(fp8_utils.__file__)
    observed = hashlib.sha256(source.read_bytes()).hexdigest()
    if observed != FP8_UTILS_SHA256:
        raise RuntimeError(f"pinned FP8 consumer mismatch:{observed}")
    candidate = load_candidate()
    stock = fp8_utils.fp8_scaled_mm
    activation = GeluAndMul()
    mode = os.environ.get("GATE_UP_MODE", "component")
    if mode not in {"component", "endpoint"}:
        raise RuntimeError(f"invalid GATE_UP_MODE:{mode}")
    observed_shapes: set[tuple[int, int, int]] = set()

    def measured(mat_a, mat_b, scales_a, scales_b, out_dtype, bias=None):
        m, k = mat_a.shape
        n = mat_b.shape[1]
        shape = (m, n, k)
        if k != GATE_UP_K or n != GATE_UP_N or out_dtype != torch.bfloat16 or bias is not None:
            return stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias)
        if m <= 128:
            if shape not in observed_shapes:
                append(
                    {
                        "phase": "decode_fallback_runtime_invocation",
                        "shape_mnk": list(shape),
                        "consumer": "MergedColumnParallelLinear(gate_up_proj)->GeluAndMul",
                        "path": "stock_cutlass",
                        "stock_launches_per_layer": 1,
                    }
                )
                observed_shapes.add(shape)
            return stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias)
        if mode == "component":
            append({"phase": "target_path_call", "shape_mnk": list(shape)})
        if shape in observed_shapes:
            return candidate.fp8_gate_up_multicast(mat_a, mat_b, scales_a, scales_b)
        if mode == "endpoint":
            append(
                {
                    "phase": "prefill_endpoint_runtime_invocation",
                    "shape_mnk": list(shape),
                    "candidate_symbol": "gemma4_fp8_gate_up_multicast.fp8_gate_up_multicast",
                    "returned_to_unchanged_gelu_and_mul": True,
                }
            )
            observed_shapes.add(shape)
            return candidate.fp8_gate_up_multicast(mat_a, mat_b, scales_a, scales_b)

        reference = stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias)
        output = candidate.fp8_gate_up_multicast(mat_a, mat_b, scales_a, scales_b)
        torch.cuda.synchronize()
        projection_metrics = metrics(torch, reference, output)
        activation_metrics = metrics(torch, activation(reference), activation(output))
        stock_us = timings(lambda: stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias))
        candidate_us = timings(
            lambda: candidate.fp8_gate_up_multicast(mat_a, mat_b, scales_a, scales_b)
        )
        append(
            {
                "phase": "prefill_real_consumer_measurement",
                "shape_mnk": list(shape),
                "consumer": "MergedColumnParallelLinear(gate_up_proj)->GeluAndMul",
                "candidate_symbol": "gemma4_fp8_gate_up_multicast.fp8_gate_up_multicast",
                "physical_change": "cluster_2x1x1_to_2x2x1_with_same_128x128x128_tile_and_pingpong_schedule",
                "stock_launches_per_layer": 1,
                "candidate_launches_per_layer": 1,
                "projection": projection_metrics,
                "unchanged_gelu_and_mul": activation_metrics,
                "activation_saturation_fraction": float(
                    (mat_a.float().abs() == torch.finfo(torch.float8_e4m3fn).max)
                    .float()
                    .mean()
                    .item()
                ),
                "weight_saturation_fraction": float(
                    (mat_b.float().abs() == torch.finfo(torch.float8_e4m3fn).max)
                    .float()
                    .mean()
                    .item()
                ),
                "stock": summarize(stock_us),
                "candidate": summarize(candidate_us),
                "candidate_speedup_fraction": 1.0
                - statistics.median(candidate_us) / statistics.median(stock_us),
                "repetitions": len(candidate_us),
                "returned_to_unchanged_gelu_and_mul": True,
            }
        )
        observed_shapes.add(shape)
        return output

    fp8_utils.fp8_scaled_mm = measured
