#!/usr/bin/env python3
"""Exact Gemma 4 post-attention residual-to-gate-up FP8 discriminator."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path
from typing import Any, Callable

M = 32
K = 5376
N = 43008
LAYERS_PER_STEP = 60
DECODE_STEPS = 358
EPSILON = 1e-6
SEED = 20260728
COSINE_MIN = 0.99999
RELATIVE_L2_MAX = 0.005
MAX_ABS_MAX = 0.02
EXPECTED_VLLM_VERSION = "0.19.1.dev6+g6d4a8e6d2"
EXPECTED_SOURCE_HASHES = {
    "_custom_ops.py": "8990c0c4de5dadbb2d1ff57f02d6a7f9133df29bb9070179ada3363461b40093",
    "input_quant_fp8.py": "6d09f1b7f8191303c4ebcc454cbf2bfb6319fbec1cb12c9842720e2f8ef75a18",
    "layernorm.py": "8b4e0b93d1d76f0394bb28f40528bdfb250e16f22a83add184d3c2651f915623",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    json.loads(temporary.read_text())
    temporary.replace(path)


def describe() -> dict[str, Any]:
    calls = LAYERS_PER_STEP * DECODE_STEPS
    eliminated_bytes_per_call = M * K * 2
    return {
        "schema_version": 1,
        "operation": (
            "post_attention_norm_bf16 + residual_bf16 -> residual_out_bf16 + "
            "pre_feedforward_rmsnorm_dynamic_per_token_e4m3 -> "
            "gate_up_cutlass_scaled_mm_bf16"
        ),
        "shape": {"m": M, "k": K, "n": N},
        "calls_per_decode_step": LAYERS_PER_STEP,
        "calls_per_endpoint_batch": calls,
        "candidate_symbol": "vllm._custom_ops.rms_norm_dynamic_per_token_quant",
        "consumer_symbol": "vllm._custom_ops.cutlass_scaled_mm",
        "candidate_residual_argument": True,
        "eliminated_launches_upper_bound_per_endpoint_batch": calls,
        "eliminated_bf16_read_bytes_per_call": eliminated_bytes_per_call,
        "eliminated_bf16_read_bytes_per_endpoint_batch": (
            eliminated_bytes_per_call * calls
        ),
        "dispatcher_modified": False,
    }


def metrics(torch: Any, actual: Any, reference: Any) -> dict[str, float | bool]:
    actual_float = actual.float().flatten()
    reference_float = reference.float().flatten()
    difference = actual_float - reference_float
    relative_l2 = torch.linalg.vector_norm(difference) / torch.linalg.vector_norm(
        reference_float
    ).clamp_min(1e-12)
    return {
        "finite": bool(torch.isfinite(actual_float).all().item()),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                actual_float, reference_float, dim=0, eps=1e-12
            ).item()
        ),
        "relative_l2": float(relative_l2.item()),
        "max_abs": float(difference.abs().max().item()),
    }


def timed(
    torch: Any,
    call: Callable[[int], Any],
    warmup: int,
    repeats: int,
) -> list[float]:
    for index in range(warmup):
        call(index)
    torch.cuda.synchronize()
    values = []
    for index in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = call(warmup + index)
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
        del output
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--warmup", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=40)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(describe(), indent=2, sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--output is required unless --describe is used")
    if args.warmup < 3 or args.repeats < 10:
        parser.error("--warmup must be >=3 and --repeats must be >=10")
    args.output.mkdir(parents=True, exist_ok=False)

    import torch
    import vllm
    from vllm.config import VllmConfig, set_current_vllm_config
    from vllm import _custom_ops as ops
    from vllm.model_executor.layers import layernorm as layernorm_module
    from vllm.model_executor.layers.layernorm import RMSNorm
    from vllm.model_executor.layers.quantization import (
        input_quant_fp8 as input_quant_module,
    )
    from vllm.model_executor.layers.quantization.input_quant_fp8 import QuantFP8
    from vllm.model_executor.layers.quantization.utils.quant_utils import GroupShape

    config_context = set_current_vllm_config(VllmConfig())
    config_context.__enter__()

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    capability = torch.cuda.get_device_capability()
    if capability != (10, 0):
        raise RuntimeError(f"sm100_required:{capability}")
    if not hasattr(ops, "rms_norm_dynamic_per_token_quant"):
        raise RuntimeError("fused_rms_quant_symbol_missing")
    if vllm.__version__ != EXPECTED_VLLM_VERSION:
        raise RuntimeError(
            f"vllm_version_mismatch:{vllm.__version__}:{EXPECTED_VLLM_VERSION}"
        )
    source_paths = {
        "_custom_ops.py": Path(ops.__file__).resolve(),
        "input_quant_fp8.py": Path(input_quant_module.__file__).resolve(),
        "layernorm.py": Path(layernorm_module.__file__).resolve(),
    }
    observed_source_hashes = {
        name: sha256(path) for name, path in source_paths.items()
    }
    if observed_source_hashes != EXPECTED_SOURCE_HASHES:
        raise RuntimeError(
            f"pinned_source_mismatch:{observed_source_hashes}:"
            f"{EXPECTED_SOURCE_HASHES}"
        )

    extension_candidates = sorted(Path(ops.__file__).resolve().parent.glob("_C*.so"))
    if not extension_candidates:
        raise RuntimeError("vllm_custom_extension_missing")
    extension_path = extension_candidates[0]
    state = {
        "schema_version": 1,
        "phase": "validated_pre_science",
        "stock_first_call_complete": False,
        "candidate_first_call_complete": False,
        "candidate_science_started": False,
        "vllm_version": vllm.__version__,
        "source_paths": {name: str(path) for name, path in source_paths.items()},
        "source_hashes": observed_source_hashes,
        "custom_extension": str(extension_path),
        "custom_extension_sha256": sha256(extension_path),
        "runner_sha256": sha256(Path(__file__).resolve()),
    }
    atomic_json(args.output / "INVOCATION_STATE.json", state)

    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    post_attention_norm = (
        torch.randn((M, K), device="cuda", dtype=torch.bfloat16) * 0.02
    )
    residual_seed = (
        torch.randn((M, K), device="cuda", dtype=torch.bfloat16) * 0.02
    )
    norm_weight = (
        1.0
        + torch.randn((K,), device="cuda", dtype=torch.bfloat16) * 0.01
    )
    weight_bf16 = (
        torch.randn((N, K), device="cuda", dtype=torch.bfloat16) * 0.02
    )
    gate_up_weight, gate_up_scale = ops.scaled_fp8_quant(weight_bf16)
    gate_up_weight = gate_up_weight.t()
    fp8_dtype = gate_up_weight.dtype
    quantizer = QuantFP8(static=False, group_shape=GroupShape.PER_TOKEN)

    def stock_native_boundary(
        post_attention: Any, residual: Any, weight: Any
    ) -> tuple[Any, Any, Any]:
        residual_out = post_attention + residual
        normalized = RMSNorm.forward_static(
            residual_out,
            EPSILON,
            K,
            residual_out.dtype,
            weight,
            None,
            None,
        )
        quantized, scale = quantizer.forward_native(normalized)
        return quantized, scale, residual_out

    stock_compiled = torch.compile(
        stock_native_boundary,
        fullgraph=True,
        dynamic=False,
    )

    def consume(quantized: Any, scale: Any) -> Any:
        return ops.cutlass_scaled_mm(
            quantized,
            gate_up_weight,
            scale,
            gate_up_scale,
            out_dtype=torch.bfloat16,
        )

    generated_kernel_count = None
    try:
        from torch._inductor import metrics as inductor_metrics

        inductor_metrics.reset()
    except Exception:
        inductor_metrics = None
    stock_quantized, stock_scale, stock_residual = stock_compiled(
        post_attention_norm, residual_seed, norm_weight
    )
    stock_output = consume(stock_quantized, stock_scale)
    torch.cuda.synchronize()
    state["stock_first_call_complete"] = True
    atomic_json(args.output / "INVOCATION_STATE.json", state)
    if inductor_metrics is not None:
        generated_kernel_count = int(inductor_metrics.generated_kernel_count)

    candidate_residual = residual_seed.clone()
    state["candidate_science_started"] = True
    atomic_json(args.output / "INVOCATION_STATE.json", state)
    candidate_quantized, candidate_scale = ops.rms_norm_dynamic_per_token_quant(
        post_attention_norm,
        norm_weight,
        EPSILON,
        fp8_dtype,
        residual=candidate_residual,
    )
    candidate_output = consume(candidate_quantized, candidate_scale)
    torch.cuda.synchronize()
    state["candidate_first_call_complete"] = True
    state["phase"] = "first_calls_complete"
    atomic_json(args.output / "INVOCATION_STATE.json", state)

    def numeric_case(
        name: str,
        post_attention: Any,
        residual: Any,
        stock_values: tuple[Any, Any, Any, Any] | None = None,
    ) -> dict[str, Any]:
        if stock_values is None:
            stock_q, stock_s, stock_r = stock_compiled(
                post_attention, residual, norm_weight
            )
            stock_y = consume(stock_q, stock_s)
        else:
            stock_q, stock_s, stock_r, stock_y = stock_values
        candidate_r = residual.clone()
        candidate_q, candidate_s = ops.rms_norm_dynamic_per_token_quant(
            post_attention,
            norm_weight,
            EPSILON,
            fp8_dtype,
            residual=candidate_r,
        )
        candidate_y = consume(candidate_q, candidate_s)
        torch.cuda.synchronize()
        return {
            "name": name,
            "residual_out": metrics(torch, candidate_r, stock_r),
            "dequantized_activation": metrics(
                torch,
                candidate_q.float() * candidate_s,
                stock_q.float() * stock_s,
            ),
            "gate_up_output": metrics(torch, candidate_y, stock_y),
        }

    numeric = [
        numeric_case(
            "production_random",
            post_attention_norm,
            residual_seed,
            (
                stock_quantized,
                stock_scale,
                stock_residual,
                stock_output,
            ),
        ),
        numeric_case(
            "zero_residual",
            post_attention_norm,
            torch.zeros_like(residual_seed),
        ),
        numeric_case(
            "zero_post_attention",
            torch.zeros_like(post_attention_norm),
            residual_seed,
        ),
        numeric_case(
            "tiny_finite",
            post_attention_norm * 1e-3,
            residual_seed * 1e-3,
        ),
        numeric_case(
            "high_amplitude_finite",
            post_attention_norm * 4,
            residual_seed * 4,
        ),
    ]
    numeric_rows = [
        row
        for case in numeric
        for key, row in case.items()
        if key != "name"
    ]
    finite_and_structural = all(row["finite"] for row in numeric_rows)
    if not finite_and_structural:
        terminal = {
            "schema_version": 1,
            "classification": "exact_consumer_component_incorrect_nonfinite_or_structural",
            "contract": describe(),
            "numeric": numeric,
            "numeric_pass": False,
            "finite_and_structural": False,
            "measurement": None,
            "scope": {
                "dispatcher_modified": False,
                "endpoint_requests_submitted": False,
                "provider_operations": False,
            },
        }
        atomic_json(args.output / "TERMINAL.json", terminal)
        return 0
    numeric_pass = all(
        row["cosine"] >= COSINE_MIN
        and row["relative_l2"] <= RELATIVE_L2_MAX
        and row["max_abs"] <= MAX_ABS_MAX
        for row in numeric_rows
    )

    buffer_count = args.warmup + args.repeats
    candidate_buffers = [residual_seed.clone() for _ in range(buffer_count)]

    def stock_call(_: int) -> tuple[Any, Any]:
        quantized, scale, residual_out = stock_compiled(
            post_attention_norm, residual_seed, norm_weight
        )
        return consume(quantized, scale), residual_out

    def candidate_call(index: int) -> tuple[Any, Any]:
        residual = candidate_buffers[index]
        quantized, scale = ops.rms_norm_dynamic_per_token_quant(
            post_attention_norm,
            norm_weight,
            EPSILON,
            fp8_dtype,
            residual=residual,
        )
        return consume(quantized, scale), residual

    stock_ms = timed(torch, stock_call, args.warmup, args.repeats)
    candidate_ms = timed(torch, candidate_call, args.warmup, args.repeats)
    stock_p50 = statistics.median(stock_ms)
    candidate_p50 = statistics.median(candidate_ms)
    delta_us = (stock_p50 - candidate_p50) * 1000.0
    projected_service_delta = (
        LAYERS_PER_STEP * DECODE_STEPS * delta_us / 1e6 / M
    )
    terminal = {
        "schema_version": 1,
        "classification": "exact_consumer_component_measurement",
        "contract": describe(),
        "environment": {
            "device": torch.cuda.get_device_name(0),
            "compute_capability": list(capability),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "vllm": vllm.__version__,
        },
        "identities": {
            "custom_extension": str(extension_path),
            "custom_extension_sha256": sha256(extension_path),
            "runner_sha256": sha256(Path(__file__).resolve()),
            "source_hashes": observed_source_hashes,
        },
        "numeric": numeric,
        "numeric_pass": numeric_pass,
        "finite_and_structural": finite_and_structural,
        "measurement": {
            "scope": "compiled_default_native_boundary_plus_exact_gate_up_consumer",
            "warmup": args.warmup,
            "repeats": args.repeats,
            "stock_ms": stock_ms,
            "candidate_ms": candidate_ms,
            "stock_p50_ms": stock_p50,
            "candidate_p50_ms": candidate_p50,
            "candidate_delta_us_per_call": delta_us,
            "stock_compiled_generated_kernel_count": generated_kernel_count,
            "projected_service_delta_seconds_per_request": projected_service_delta,
        },
        "decision": {
            "reopen_integration": numeric_pass and projected_service_delta >= 0.002,
            "minimum_projected_service_delta_seconds_per_request": 0.002,
            "reject_if": (
                "nonfinite or structural failure stops before timing; finite "
                "out-of-envelope numerical differences retain paired timing; "
                "integration reopens only when numerical guards pass and the "
                "projection is at least 0.002 s/request"
            ),
        },
        "scope": {
            "dispatcher_modified": False,
            "endpoint_requests_submitted": False,
            "provider_operations": False,
        },
    }
    atomic_json(args.output / "TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
