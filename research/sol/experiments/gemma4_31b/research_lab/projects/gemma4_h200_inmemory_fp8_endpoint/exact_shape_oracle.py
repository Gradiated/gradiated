#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import pathlib
import time

import torch
from sglang.srt.layers.quantization import fp8_utils
from sglang.srt.layers.quantization.fp8 import Fp8Config, Fp8LinearMethod


M, K, N = 32, 5376, 43008


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def errors(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, float | bool]:
    candidate_float = candidate.float()
    reference_float = reference.float()
    difference = candidate_float - reference_float
    rmse = float(torch.sqrt(torch.mean(difference.square())))
    reference_rms = float(torch.sqrt(torch.mean(reference_float.square())))
    return {
        "finite": bool(torch.isfinite(candidate_float).all() and torch.isfinite(reference_float).all()),
        "nontrivial": bool(float(candidate_float.abs().max()) > 1e-6 and reference_rms > 1e-6),
        "maximum_absolute": float(difference.abs().max()),
        "normalized_rmse": rmse / max(reference_rms, 1e-12),
        "cosine_similarity": float(torch.nn.functional.cosine_similarity(candidate_float.flatten(), reference_float.flatten(), dim=0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result: dict[str, object] = {
        "schema_version": 1,
        "classification": "exact_shape_oracle",
        "shape": {"family": "fused_gate_up", "m": M, "k": K, "n": N},
        "pass": False,
    }
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        capability = tuple(torch.cuda.get_device_capability())
        if capability != (9, 0) or "H200" not in torch.cuda.get_device_name():
            raise RuntimeError(f"expected H200 sm90, got {torch.cuda.get_device_name()} {capability}")
        torch.manual_seed(20260720)
        torch.cuda.manual_seed_all(20260720)
        config = Fp8Config(is_checkpoint_fp8_serialized=False, activation_scheme="dynamic")
        method = Fp8LinearMethod(config)
        layer = torch.nn.Module()
        with torch.device("cuda"):
            method.create_weights(layer, K, [N], K, N, torch.bfloat16)
        original_weight = torch.randn((N, K), device="cuda", dtype=torch.bfloat16) / math.sqrt(K)
        layer._parameters["weight"] = torch.nn.Parameter(original_weight, requires_grad=False)
        activation = torch.randn((M, K), device="cuda", dtype=torch.bfloat16) / math.sqrt(K)
        method.process_weights_after_loading(layer)
        calls = 0
        original_scaled_mm = fp8_utils.fp8_scaled_mm

        def counted_scaled_mm(*call_args, **call_kwargs):
            nonlocal calls
            calls += 1
            return original_scaled_mm(*call_args, **call_kwargs)

        fp8_utils.fp8_scaled_mm = counted_scaled_mm
        try:
            torch.cuda.synchronize()
            started = time.perf_counter()
            candidate = method.apply(layer, activation)
            torch.cuda.synchronize()
            elapsed_ms = (time.perf_counter() - started) * 1000
        finally:
            fp8_utils.fp8_scaled_mm = original_scaled_mm
        reference = torch.nn.functional.linear(activation, original_weight)
        observed = errors(candidate, reference)
        tolerance = {"normalized_rmse": 0.08, "minimum_cosine_similarity": 0.99}
        numeric_pass = bool(
            observed["finite"]
            and observed["nontrivial"]
            and observed["normalized_rmse"] <= tolerance["normalized_rmse"]
            and observed["cosine_similarity"] >= tolerance["minimum_cosine_similarity"]
        )
        result.update(
            {
                "runtime": {
                    "gpu": torch.cuda.get_device_name(),
                    "capability": list(capability),
                    "torch": torch.__version__,
                    "cuda": torch.version.cuda,
                },
                "producer": {
                    "method": f"{type(method).__module__}.{type(method).__name__}",
                    "source_sha256": hashlib.sha256(inspect.getsource(Fp8LinearMethod.process_weights_after_loading).encode()).hexdigest(),
                    "weight_dtype": str(layer.weight.dtype),
                    "weight_shape": list(layer.weight.shape),
                    "weight_scale_dtype": str(layer.weight_scale.dtype),
                    "weight_scale_shape": list(layer.weight_scale.shape),
                    "serialized": False,
                },
                "consumer": {
                    "required_symbol": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
                    "call_count": calls,
                    "output_dtype": str(candidate.dtype),
                    "elapsed_ms_single_observed_call": elapsed_ms,
                },
                "numeric": {**observed, "tolerance": tolerance, "pass": numeric_pass},
            }
        )
        result["pass"] = bool(
            numeric_pass
            and calls >= 1
            and layer.weight.dtype == torch.float8_e4m3fn
            and list(layer.weight.shape) == [K, N]
            and candidate.dtype == torch.bfloat16
            and method.cutlass_fp8_supported
        )
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
