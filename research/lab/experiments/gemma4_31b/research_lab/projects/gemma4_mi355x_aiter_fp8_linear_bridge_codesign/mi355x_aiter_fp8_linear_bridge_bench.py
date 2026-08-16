from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

from bridge_contract import (
    CONVERSION_AMORTIZATION_REQUESTS,
    LINEAR_SHAPES,
    PHASES,
    TARGET_SECONDS_PER_REQUEST,
    aggregate_runtime_seconds,
    unchanged_seconds_per_request,
)


VLLM_COMMIT = "0164022c907014a27e81c514cd4dff6091904c2b"


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--samples", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    required_environment = {
        "VLLM_ROCM_USE_AITER": "1",
        "VLLM_ROCM_USE_AITER_LINEAR": "1",
        "VLLM_ROCM_USE_AITER_LINEAR_HIPBMM": "1",
    }
    wrong_environment = {
        key: os.environ.get(key)
        for key, expected in required_environment.items()
        if os.environ.get(key) != expected
    }
    if wrong_environment:
        raise SystemExit(f"required environment not bound: {wrong_environment}")
    sys.path.insert(0, str(args.vllm_root))

    import torch
    from torch import nn

    if not torch.cuda.is_available() or torch.version.hip is None:
        raise SystemExit("typed_external_blocker: target ROCm accelerator unavailable")
    properties = torch.cuda.get_device_properties(0)
    architecture = getattr(properties, "gcnArchName", "") or ",".join(
        torch.cuda.get_arch_list()
    )
    if "gfx950" not in architecture:
        raise SystemExit(f"typed_external_blocker: expected gfx950, observed {architecture}")

    from vllm.model_executor.kernels.linear.scaled_mm.ScaledMMLinearKernel import (
        FP8ScaledMMLinearLayerConfig,
    )
    from vllm.model_executor.kernels.linear.scaled_mm.aiter import (
        AiterHipbMMPerTokenFp8ScaledMMLinearKernel,
    )
    from vllm.model_executor.kernels.linear.scaled_mm.rocm import (
        ROCmFP8ScaledMMLinearKernel,
    )
    from vllm.model_executor.layers.quantization.online.fp8 import (
        AiterFp8PtpcOnlineLinearMethod,
        Fp8PerTensorOnlineLinearMethod,
    )
    from vllm.model_executor.layers.quantization.utils.quant_utils import (
        kFp8DynamicTensorSym,
        kFp8DynamicTokenSym,
        kFp8StaticChannelSym,
        kFp8StaticTensorSym,
    )

    commit = (
        __import__("subprocess")
        .check_output(
            ["git", "-C", str(args.vllm_root), "rev-parse", "HEAD"], text=True
        )
        .strip()
    )
    if commit != VLLM_COMMIT:
        raise SystemExit(f"vLLM identity mismatch: {commit}")

    result = {
        "schema_version": 1,
        "classification": "running",
        "identity": {
            "vllm_commit": commit,
            "torch_version": torch.__version__,
            "torch_hip": torch.version.hip,
            "device_name": properties.name,
            "gcn_arch": architecture,
            "device_total_memory": properties.total_memory,
            "environment": required_environment,
        },
        "science_started": False,
        "smoke": None,
        "timing_rows": [],
        "conversion_rows": [],
    }
    atomic_json(args.output, result)

    def kernel_config(weight_key, activation_key, n: int, k: int):
        return FP8ScaledMMLinearLayerConfig(
            weight_quant_key=weight_key,
            activation_quant_key=activation_key,
            weight_shape=(n, k),
            input_dtype=torch.bfloat16,
            out_dtype=torch.bfloat16,
        )

    layer_parameters = ["weight", "weight_scale", "input_scale", "input_scale_ub"]

    def make_method(arm: str, weight: torch.Tensor):
        layer = nn.Module()
        layer.register_parameter(
            "weight", nn.Parameter(weight, requires_grad=False)
        )
        if arm == "candidate":
            kernel = AiterHipbMMPerTokenFp8ScaledMMLinearKernel(
                kernel_config(
                    kFp8StaticChannelSym,
                    kFp8DynamicTokenSym,
                    weight.shape[0],
                    weight.shape[1],
                ),
                layer_parameters,
            )
            method = AiterFp8PtpcOnlineLinearMethod.__new__(
                AiterFp8PtpcOnlineLinearMethod
            )
        else:
            kernel = ROCmFP8ScaledMMLinearKernel(
                kernel_config(
                    kFp8StaticTensorSym,
                    kFp8DynamicTensorSym,
                    weight.shape[0],
                    weight.shape[1],
                ),
                layer_parameters,
            )
            method = Fp8PerTensorOnlineLinearMethod.__new__(
                Fp8PerTensorOnlineLinearMethod
            )
            method.use_marlin = False
        method.fp8_linear = kernel
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        method.process_weights_after_loading(layer)
        end.record()
        end.synchronize()
        conversion_ms = start.elapsed_time(end)
        return method, layer, conversion_ms

    init_start = time.perf_counter()
    smoke_weight = torch.randn(
        (16, 16), device="cuda", dtype=torch.bfloat16
    )
    smoke_method, smoke_layer, _ = make_method("candidate", smoke_weight)
    smoke_x = torch.randn((1, 16), device="cuda", dtype=torch.bfloat16)
    smoke_output = smoke_method.apply(smoke_layer, smoke_x)
    smoke_finite = bool(torch.isfinite(smoke_output).all().item())
    init_seconds = time.perf_counter() - init_start
    if not smoke_finite:
        raise SystemExit("candidate smoke produced a nonfinite output")
    result["smoke"] = {
        "shape": [1, 16, 16],
        "consumer": type(smoke_method.fp8_linear).__name__,
        "finite": smoke_finite,
        "consumed_checksum": float(smoke_output.float().sum().item()),
        "aiter_initialization_seconds": init_seconds,
    }
    result["science_started"] = True
    atomic_json(args.output, result)

    def timed_apply(method, layer, x: torch.Tensor) -> tuple[dict, torch.Tensor]:
        for _ in range(args.warmups):
            output = method.apply(layer, x)
        torch.cuda.synchronize()
        samples_ms = []
        last_output = output
        for _ in range(args.samples):
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            last_output = method.apply(layer, x)
            end.record()
            end.synchronize()
            samples_ms.append(start.elapsed_time(end))
        return (
            {
                "samples_us": [value * 1000 for value in samples_ms],
                "p50_us": statistics.median(samples_ms) * 1000,
                "p95_us": percentile(samples_ms, 0.95) * 1000,
                "min_us": min(samples_ms) * 1000,
                "max_us": max(samples_ms) * 1000,
            },
            last_output,
        )

    for shape_index, shape in enumerate(LINEAR_SHAPES):
        torch.cuda.reset_peak_memory_stats()
        torch.manual_seed(40_000 + shape_index)
        weight = torch.randn(
            (shape.n, shape.k), device="cuda", dtype=torch.bfloat16
        )
        methods = {}
        for arm in ("control", "candidate"):
            method, layer, conversion_ms = make_method(arm, weight)
            methods[arm] = (method, layer)
            result["conversion_rows"].append(
                {
                    "arm": arm,
                    "shape": shape.name,
                    "n": shape.n,
                    "k": shape.k,
                    "layers": shape.layers,
                    "conversion_ms": conversion_ms,
                    "consumer": type(method.fp8_linear).__name__,
                    "weight_layout": list(layer.weight.shape),
                    "weight_scale_layout": list(layer.weight_scale.shape),
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                }
            )
            atomic_json(args.output, result)

        for phase_index, (phase_name, phase) in enumerate(PHASES.items()):
            torch.manual_seed(50_000 + shape_index * 10 + phase_index)
            x = torch.randn(
                (phase["m"], shape.k), device="cuda", dtype=torch.bfloat16
            )
            reference = torch.nn.functional.linear(x, weight)
            for arm in ("control", "candidate"):
                method, layer = methods[arm]
                timing, output = timed_apply(method, layer, x)
                difference = output.float() - reference.float()
                relative_l2 = (
                    torch.linalg.vector_norm(difference)
                    / torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
                ).item()
                cosine = torch.nn.functional.cosine_similarity(
                    output.float().flatten(),
                    reference.float().flatten(),
                    dim=0,
                    eps=1e-12,
                ).item()
                finite = bool(torch.isfinite(output).all().item())
                row = {
                    "arm": arm,
                    "phase": phase_name,
                    "shape": shape.name,
                    "m": phase["m"],
                    "n": shape.n,
                    "k": shape.k,
                    "layers": shape.layers,
                    "consumer": type(method.fp8_linear).__name__,
                    "activation_scale": (
                        "per_token_fp32"
                        if arm == "candidate"
                        else "per_tensor_fp32"
                    ),
                    "weight_scale": (
                        "per_channel_fp32"
                        if arm == "candidate"
                        else "per_tensor_fp32"
                    ),
                    **timing,
                    "relative_l2": relative_l2,
                    "cosine": cosine,
                    "finite": finite,
                    "consumed_checksum": float(output.float().sum().item()),
                }
                result["timing_rows"].append(row)
                atomic_json(args.output, result)

    candidate_rows = [
        row for row in result["timing_rows"] if row["arm"] == "candidate"
    ]
    control_rows = [
        row for row in result["timing_rows"] if row["arm"] == "control"
    ]
    candidate_runtime = aggregate_runtime_seconds(candidate_rows, "p95_us")
    control_runtime = aggregate_runtime_seconds(control_rows, "p95_us")
    candidate_conversion = sum(
        row["conversion_ms"] / 1000 * row["layers"]
        for row in result["conversion_rows"]
        if row["arm"] == "candidate"
    )
    conversion_amortized = (
        candidate_conversion + init_seconds
    ) / CONVERSION_AMORTIZATION_REQUESTS
    candidate_full_request = (
        unchanged_seconds_per_request()
        + candidate_runtime
        + conversion_amortized
    )
    correctness_pass = all(
        row["finite"]
        and row["relative_l2"] <= 0.02
        and row["cosine"] >= 0.995
        for row in candidate_rows
    )
    consumer_pass = all(
        row["consumer"] == "AiterHipbMMPerTokenFp8ScaledMMLinearKernel"
        for row in candidate_rows
    )
    result["accounting"] = {
        "control_runtime_seconds_per_request": control_runtime,
        "candidate_runtime_seconds_per_request": candidate_runtime,
        "candidate_conversion_seconds_all_layers": candidate_conversion,
        "aiter_initialization_seconds": init_seconds,
        "conversion_amortization_requests": CONVERSION_AMORTIZATION_REQUESTS,
        "conversion_amortized_seconds_per_request": conversion_amortized,
        "all_unchanged_components_seconds_per_request": (
            unchanged_seconds_per_request()
        ),
        "candidate_full_request_seconds": candidate_full_request,
        "target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
    }
    result["gates"] = {
        "correctness": correctness_pass,
        "exact_consumer_no_fallback": consumer_pass,
        "economic": candidate_full_request <= TARGET_SECONDS_PER_REQUEST,
    }
    result["classification"] = (
        "pass"
        if correctness_pass
        and consumer_pass
        and candidate_full_request <= TARGET_SECONDS_PER_REQUEST
        else "none"
    )
    result["science_complete"] = True
    result["artifact_sha256_before_final_write"] = hashlib.sha256(
        json.dumps(result, sort_keys=True).encode()
    ).hexdigest()
    atomic_json(args.output, result)


if __name__ == "__main__":
    main()
