#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import math
import os
import statistics
import tempfile
import time
from pathlib import Path

import torch

from sglang_gate_up_integration import (
    K,
    M,
    N,
    can_dispatch,
    dispatch_pre_ff_gate_up,
    load_sm120_dispatch,
)


ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "sglang": "0.5.16",
    "sglang-kernel": "0.4.5",
    "torch_prefix": "2.11.0",
    "torch_cuda": "13.0",
    "activation_source_sha256": (
        "5d2e8a2ec0bd0bbdfa4732633144f3c287914d5d04a5a54142c9c4b04c5109d7"
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        stream.write(encoded)
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def bitwise_equal(left: torch.Tensor, right: torch.Tensor) -> bool:
    if left.dtype == torch.bfloat16:
        return bool(torch.equal(left.view(torch.uint16), right.view(torch.uint16)))
    if left.dtype == torch.float8_e4m3fn:
        return bool(torch.equal(left.view(torch.uint8), right.view(torch.uint8)))
    if left.dtype == torch.float32:
        return bool(torch.equal(left.view(torch.int32), right.view(torch.int32)))
    return bool(torch.equal(left, right))


def error_metrics(candidate: torch.Tensor, reference: torch.Tensor) -> dict:
    candidate_f32 = candidate.float()
    reference_f32 = reference.float()
    delta = (candidate_f32 - reference_f32).abs()
    denominator = torch.linalg.vector_norm(reference_f32).clamp_min(1e-12)
    return {
        "bitwise_equal": bitwise_equal(candidate, reference),
        "max_abs_error": float(delta.max()),
        "relative_l2_error": float(torch.linalg.vector_norm(delta) / denominator),
        "candidate_finite": bool(torch.isfinite(candidate_f32).all()),
        "reference_finite": bool(torch.isfinite(reference_f32).all()),
    }


def runtime_identity() -> dict:
    import inspect
    import sglang.srt.layers.activation as activation_module

    activation_path = Path(inspect.getsourcefile(activation_module.GeluAndMul)).resolve()
    identity = {
        "created_at_utc": utc_now(),
        "device": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "sglang": metadata.version("sglang"),
        "sglang_kernel": metadata.version("sglang-kernel"),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "activation_source": str(activation_path),
        "activation_source_sha256": sha256(activation_path),
    }
    checks = {
        "compute_capability": identity["compute_capability"] == [12, 0],
        "sglang": identity["sglang"] == EXPECTED["sglang"],
        "sglang_kernel": identity["sglang_kernel"] == EXPECTED["sglang-kernel"],
        "torch": identity["torch"].startswith(EXPECTED["torch_prefix"]),
        "torch_cuda": identity["torch_cuda"] == EXPECTED["torch_cuda"],
        "activation_source": (
            identity["activation_source_sha256"]
            == EXPECTED["activation_source_sha256"]
        ),
    }
    identity["checks"] = checks
    if not all(checks.values()):
        raise RuntimeError(f"runtime_identity_mismatch:{identity}")
    return identity


def prepare_weight() -> tuple[torch.Tensor, torch.Tensor]:
    from sglang.kernels.ops.quantization.fp8_kernel import (
        per_token_group_quant_fp8,
    )

    raw = torch.randn((N, K), device="cuda", dtype=torch.bfloat16)
    quantized, scale = per_token_group_quant_fp8(raw, group_size=K)
    weight = quantized.t()
    weight_scale = scale.t().contiguous()
    del raw
    assert tuple(weight.shape) == (K, N)
    assert tuple(weight.stride()) == (1, K)
    assert weight.dtype == torch.float8_e4m3fn
    assert weight_scale.dtype == torch.float32
    assert weight_scale.numel() == N
    return weight, weight_scale


class GateUpLayer:
    def __init__(self, weight: torch.Tensor, weight_scale: torch.Tensor):
        self.weight = weight
        self.weight_scale = weight_scale
        self.bias = None


def stock_boundary(
    input_tensor,
    residual,
    norm,
    weight,
    weight_scale,
    consumer,
):
    from sglang.kernels.ops.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )

    normalized, residual = norm(input_tensor, residual)
    quantized, input_scale = sglang_per_token_quant_fp8(normalized)
    gate_up = torch.ops.sgl_kernel.fp8_scaled_mm(
        quantized,
        weight,
        input_scale,
        weight_scale,
        torch.bfloat16,
        None,
    )
    consumed = consumer(gate_up)
    return normalized, residual, quantized, input_scale, gate_up, consumed


def candidate_boundary(
    input_tensor,
    residual,
    norm,
    layer,
    consumer,
    normalized_debug=None,
):
    gate_up, quantized, input_scale = dispatch_pre_ff_gate_up(
        input_tensor,
        residual,
        norm,
        layer,
        normalized_debug=normalized_debug,
    )
    consumed = consumer(gate_up)
    return residual, quantized, input_scale, gate_up, consumed


def time_boundary(callable_, input_base, residual_base, repetitions: int) -> dict:
    input_work = input_base.clone()
    residual_work = residual_base.clone()
    starts = [torch.cuda.Event(enable_timing=True) for _ in range(repetitions)]
    stops = [torch.cuda.Event(enable_timing=True) for _ in range(repetitions)]
    outputs = []
    torch.cuda.synchronize()
    wall_start = time.perf_counter()
    for index in range(repetitions):
        input_work.copy_(input_base)
        residual_work.copy_(residual_base)
        starts[index].record()
        output = callable_(input_work, residual_work)
        stops[index].record()
        outputs.append(output)
    torch.cuda.synchronize()
    wall_seconds = time.perf_counter() - wall_start
    timings_us = [
        float(start.elapsed_time(stop) * 1000.0)
        for start, stop in zip(starts, stops)
    ]
    checksum = float(sum(output.float().sum() for output in outputs))
    ordered = sorted(timings_us)
    return {
        "repetitions": repetitions,
        "unit": "microseconds_per_M32_batch_call",
        "minimum": ordered[0],
        "median": statistics.median(ordered),
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "maximum": ordered[-1],
        "enqueue_wall_us_per_call_including_symmetric_resets": (
            wall_seconds * 1e6 / repetitions
        ),
        "consumed_checksum": checksum,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-directory", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=80)
    args = parser.parse_args()

    if args.repetitions < 20:
        raise ValueError("repetitions must be at least 20")
    torch.manual_seed(1785306000)
    identity = runtime_identity()
    atomic_json(args.output / "RUNTIME_IDENTITY.json", identity)

    import sgl_kernel  # noqa: F401
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.layernorm import RMSNorm
    from sglang.srt.layers.quantization.fp8_utils import apply_fp8_linear

    load_sm120_dispatch(args.build_directory)
    atomic_json(
        args.output / "BUILD_COMPLETE.json",
        {
            "created_at_utc": utc_now(),
            "source": str(ROOT / "sm120_pre_ff_gate_up_dispatch.cu"),
            "source_sha256": sha256(ROOT / "sm120_pre_ff_gate_up_dispatch.cu"),
            "target": "sm_120a",
        },
    )

    weight, weight_scale = prepare_weight()
    layer = GateUpLayer(weight, weight_scale)
    norm = RMSNorm(K, eps=1e-6).cuda().bfloat16()
    norm.weight.data.uniform_(-0.5, 1.5)
    consumer = GeluAndMul(approximate="tanh").cuda()
    input_base = torch.randn((M, K), device="cuda", dtype=torch.bfloat16)
    residual_base = torch.randn((M, K), device="cuda", dtype=torch.bfloat16)

    stock_input = input_base.clone()
    stock_residual = residual_base.clone()
    stock = stock_boundary(
        stock_input,
        stock_residual,
        norm,
        weight,
        weight_scale,
        consumer,
    )
    torch.cuda.synchronize()
    atomic_json(
        args.output / "STOCK_FIRST_CALL_COMPLETE.json",
        {
            "created_at_utc": utc_now(),
            "shape": [M, K, N],
            "consumer_shape": list(stock[-1].shape),
            "consumer_finite": bool(torch.isfinite(stock[-1].float()).all()),
        },
    )

    production_apply = apply_fp8_linear(
        input=stock[0],
        weight=weight,
        weight_scale=weight_scale,
        input_scale=None,
        bias=None,
        cutlass_fp8_supported=True,
    )
    if not bitwise_equal(production_apply, stock[4]):
        raise RuntimeError("manual_stock_path_does_not_match_apply_fp8_linear")

    candidate_input = input_base.clone()
    candidate_residual = residual_base.clone()
    candidate_normalized = torch.empty_like(candidate_input)
    candidate = candidate_boundary(
        candidate_input,
        candidate_residual,
        norm,
        layer,
        consumer,
        normalized_debug=candidate_normalized,
    )
    torch.cuda.synchronize()
    atomic_json(
        args.output / "CANDIDATE_FIRST_CALL_COMPLETE.json",
        {
            "created_at_utc": utc_now(),
            "shape": [M, K, N],
            "consumer_shape": list(candidate[-1].shape),
            "consumer_finite": bool(torch.isfinite(candidate[-1].float()).all()),
        },
    )

    oracle = {
        "normalized_bf16": error_metrics(candidate_normalized, stock[0]),
        "residual_bf16": error_metrics(candidate[0], stock[1]),
        "activation_e4m3": error_metrics(candidate[1], stock[2]),
        "activation_scale_fp32": error_metrics(candidate[2], stock[3]),
        "gate_up_bf16": error_metrics(candidate[3], stock[4]),
        "gelu_and_mul_bf16": error_metrics(candidate[4], stock[5]),
        "production_apply_gate_up_bf16": error_metrics(production_apply, stock[4]),
        "contract_rejects_m31": not can_dispatch(
            layer,
            torch.empty((31, K), device="cuda", dtype=torch.bfloat16),
            torch.empty((31, K), device="cuda", dtype=torch.bfloat16),
        ),
        "contract_rejects_m33": not can_dispatch(
            layer,
            torch.empty((33, K), device="cuda", dtype=torch.bfloat16),
            torch.empty((33, K), device="cuda", dtype=torch.bfloat16),
        ),
    }
    required_exact = [
        "normalized_bf16",
        "residual_bf16",
        "activation_e4m3",
        "activation_scale_fp32",
        "gate_up_bf16",
        "gelu_and_mul_bf16",
        "production_apply_gate_up_bf16",
    ]
    oracle_pass = (
        all(oracle[name]["bitwise_equal"] for name in required_exact)
        and oracle["contract_rejects_m31"]
        and oracle["contract_rejects_m33"]
    )
    if not oracle_pass:
        atomic_json(
            args.output / "ORACLE_FAILURE.json",
            {
                "created_at_utc": utc_now(),
                "classification": "candidate_numerical_mismatch",
                "oracle": oracle,
            },
        )
        raise RuntimeError(f"candidate_numerical_mismatch:{oracle}")

    stock_timing = time_boundary(
        lambda x, r: stock_boundary(
            x, r, norm, weight, weight_scale, consumer
        )[-1],
        input_base,
        residual_base,
        args.repetitions,
    )
    candidate_timing = time_boundary(
        lambda x, r: candidate_boundary(x, r, norm, layer, consumer)[-1],
        input_base,
        residual_base,
        args.repetitions,
    )
    median_speedup = stock_timing["median"] / candidate_timing["median"]
    terminal = {
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "classification": (
            "measured_component_positive"
            if median_speedup > 1.0
            else "measured_component_negative"
        ),
        "identity": identity,
        "shape": {
            "phase": "decode_c32",
            "M": M,
            "K": K,
            "N": N,
            "input": "BF16 row-major [32,5376]",
            "weight": "E4M3FN column-major logical [5376,43008], strides [1,5376]",
            "activation_scale": "FP32 [32,1], absmax(row)/448",
            "weight_scale": "FP32 [1,43008] per output channel",
            "output": "BF16 row-major [32,43008]",
            "consumer": "installed SGLang GeluAndMul.forward_native",
        },
        "oracle": oracle,
        "oracle_pass": oracle_pass,
        "timing": {
            "stock": stock_timing,
            "candidate": candidate_timing,
            "median_speedup": median_speedup,
            "median_delta_us_per_batch_call": (
                stock_timing["median"] - candidate_timing["median"]
            ),
        },
        "candidate_path": {
            "op": "sm120_fp8_linear_persistent_dispatch::gate_up_m32",
            "source_sha256": sha256(ROOT / "sm120_pre_ff_gate_up_dispatch.cu"),
            "stock_gemm_op": "sgl_kernel::fp8_scaled_mm",
            "first_bf16_consumer": "sglang.srt.layers.activation.GeluAndMul",
        },
    }
    atomic_json(args.output / "TERMINAL.json", terminal)
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
