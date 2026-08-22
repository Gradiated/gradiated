#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import torch
import vllm

from vllm import _custom_ops as ops
from vllm.model_executor.kernels.linear.scaled_mm import (
    CutlassFP8ScaledMMLinearKernel,
    FP8ScaledMMLinearLayerConfig,
)
from vllm.model_executor.layers.fusion.quant_activation import (
    QuantizedActivation,
    rms_norm_to_fp8_linear,
)
from vllm.model_executor.layers.layernorm import RMSNorm
from vllm.model_executor.layers.quantization.utils.quant_utils import (
    kFp8DynamicTokenSym,
    kFp8StaticTensorSym,
)
from vllm.platforms import current_platform


def timed_ms(fn, warmup: int, repeats: int) -> list[float]:
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    values = []
    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = fn()
        end.record()
        output.float().sum().item()
        end.synchronize()
        values.append(start.elapsed_time(end))
    return values


def run_case(m: int, k: int, n: int, warmup: int, repeats: int) -> dict:
    torch.manual_seed(7 + m + n)
    dtype = torch.bfloat16
    fp8_dtype = current_platform.fp8_dtype()
    x = (torch.randn((m, k), device="cuda", dtype=dtype) / k**0.5).contiguous()
    norm = RMSNorm(k, eps=1e-6, dtype=dtype).cuda()
    norm.weight.data.normal_(mean=1.0, std=0.1)

    weight_bf16 = (
        torch.randn((n, k), device="cuda", dtype=dtype) / k**0.5
    ).contiguous()
    weight_fp8, weight_scale = ops.scaled_fp8_quant(weight_bf16, scale=None)
    layer = SimpleNamespace(
        weight=weight_fp8.t().contiguous(),
        weight_scale=weight_scale,
        input_scale=None,
        input_scale_ub=None,
    )
    del weight_bf16

    config = FP8ScaledMMLinearLayerConfig(
        weight_quant_key=kFp8StaticTensorSym,
        activation_quant_key=kFp8DynamicTokenSym,
        weight_shape=(n, k),
        input_dtype=dtype,
        out_dtype=dtype,
    )
    kernel = CutlassFP8ScaledMMLinearKernel(
        config,
        ("weight", "weight_scale", "input_scale", "input_scale_ub"),
    )
    kernel.logical_output_size = n
    consumer = SimpleNamespace(input_quant_key=kernel.input_quant_key())

    normalized = norm(x)
    stock_data, stock_scale = ops.scaled_fp8_quant(
        normalized,
        scale=None,
        use_per_token_if_dynamic=True,
    )
    fused = rms_norm_to_fp8_linear(norm, x, consumer)
    assert isinstance(fused, QuantizedActivation)

    stock_output = kernel.apply_weights(layer, normalized)
    fused_output = kernel.apply_weights(layer, fused)
    torch.cuda.synchronize()

    stock_dequant = stock_data.float() * stock_scale
    fused_dequant = fused.data.float() * fused.scale
    scale_close = torch.allclose(stock_scale, fused.scale, rtol=1e-5, atol=1e-8)
    activation_close = torch.allclose(
        stock_dequant, fused_dequant, rtol=5e-2, atol=5e-2
    )
    output_close = torch.allclose(
        stock_output.float(), fused_output.float(), rtol=5e-2, atol=5e-2
    )

    def stock_path() -> torch.Tensor:
        return kernel.apply_weights(layer, norm(x))

    def fused_path() -> torch.Tensor:
        activation = rms_norm_to_fp8_linear(norm, x, consumer)
        return kernel.apply_weights(layer, activation)

    stock_times = timed_ms(stock_path, warmup, repeats)
    fused_times = timed_ms(fused_path, warmup, repeats)
    return {
        "shape": {"m": m, "k": k, "n": n},
        "consumer": "CutlassFP8ScaledMMLinearKernel.apply_weights",
        "gemm": "vllm._custom_ops.cutlass_scaled_mm",
        "activation_quant_key": str(kFp8DynamicTokenSym),
        "oracle": {
            "scale_close": scale_close,
            "activation_dequant_close": activation_close,
            "gemm_output_close": output_close,
            "scale_max_abs": (stock_scale - fused.scale).abs().max().item(),
            "activation_dequant_max_abs": (
                stock_dequant - fused_dequant
            ).abs().max().item(),
            "gemm_output_max_abs": (
                stock_output.float() - fused_output.float()
            ).abs().max().item(),
            "stock_nonfinite": (~torch.isfinite(stock_output)).sum().item(),
            "fused_nonfinite": (~torch.isfinite(fused_output)).sum().item(),
        },
        "warm_latency_ms": {
            "stock_median": statistics.median(stock_times),
            "stock_p95": sorted(stock_times)[int(0.95 * (len(stock_times) - 1))],
            "fused_median": statistics.median(fused_times),
            "fused_p95": sorted(fused_times)[int(0.95 * (len(fused_times) - 1))],
            "median_delta": statistics.median(stock_times)
            - statistics.median(fused_times),
            "warmup": warmup,
            "repeats": repeats,
            "unit": "one norm-to-qkv GEMM invocation over one batch",
        },
        "passed": (
            scale_close
            and activation_close
            and output_close
            and torch.isfinite(stock_output).all().item()
            and torch.isfinite(fused_output).all().item()
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", default="1,32,33,2048")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=50)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("The exact oracle requires CUDA")
    capability = torch.cuda.get_device_capability()
    if capability != (12, 0):
        raise RuntimeError(f"Expected sm_120, observed {capability}")
    if not vllm.__version__.startswith("0.26.0"):
        raise RuntimeError(f"Expected vLLM 0.26.0, observed {vllm.__version__}")
    if torch.__version__ != "2.11.0+cu130":
        raise RuntimeError(
            f"Expected Torch 2.11.0+cu130, observed {torch.__version__}"
        )

    rows = [int(value) for value in args.rows.split(",")]
    shapes = [
        (m, 5376, n)
        for m in rows
        for n in (16384, 20480)
        if not (m > 33 and n == 20480)
    ]
    started = time.time()
    results = [
        run_case(m, k, n, args.warmup, args.repeats) for m, k, n in shapes
    ]
    payload = {
        "schema_version": 1,
        "classification": "measured_sm120_framework_oracle",
        "device": torch.cuda.get_device_name(),
        "device_capability": capability,
        "torch_version": torch.__version__,
        "vllm_version": vllm.__version__,
        "elapsed_seconds": time.time() - started,
        "rows": results,
        "passed": all(row["passed"] for row in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(args.output)
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
