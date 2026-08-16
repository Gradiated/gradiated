#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import statistics
from pathlib import Path
from typing import Any, Callable

import torch
import triton
import triton.language as tl
from safetensors.torch import load_file


K = 21504
N = 5376
FP8_MAX = 448.0


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def source_sha256(function: Callable[..., Any]) -> str:
    return hashlib.sha256(inspect.getsource(function).encode()).hexdigest()


@triton.jit
def static_fp8_quant_kernel(
    source,
    output,
    inverse_scale: tl.constexpr,
    elements: tl.constexpr,
    block: tl.constexpr,
):
    offsets = tl.program_id(0) * block + tl.arange(0, block)
    values = tl.load(source + offsets, mask=offsets < elements, other=0.0)
    tl.store(output + offsets, values * inverse_scale, mask=offsets < elements)


def static_fp8_quant(source: torch.Tensor, inverse_scale: float) -> torch.Tensor:
    output = torch.empty(source.shape, device=source.device, dtype=torch.float8_e4m3fn)
    elements = source.numel()
    static_fp8_quant_kernel[(triton.cdiv(elements, 1024),)](
        source,
        output,
        inverse_scale=inverse_scale,
        elements=elements,
        block=1024,
    )
    return output


def cuda_samples(function: Callable[[], torch.Tensor], repetitions: int = 25) -> tuple[torch.Tensor, list[float]]:
    output = function()
    torch.cuda.synchronize()
    values = []
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        values.append(start.elapsed_time(end))
    return output, values


def kernel_names(function: Callable[[], torch.Tensor]) -> list[str]:
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CUDA]) as profile:
        output = function()
        output.float().abs().mean().item()
    return sorted(
        {
            event.name
            for event in profile.events()
            if str(event.device_type).lower().endswith("cuda")
        }
    )


def summarize(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median_ms": statistics.median(values),
        "min_ms": ordered[0],
        "p90_ms": ordered[int(0.9 * (len(ordered) - 1))],
        "max_ms": ordered[-1],
    }


def peak_allocation(function: Callable[[], torch.Tensor]) -> dict[str, float]:
    torch.cuda.synchronize()
    baseline = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    output = function()
    output.float().abs().mean().item()
    peak = torch.cuda.max_memory_allocated()
    return {
        "baseline_bytes": baseline,
        "peak_bytes": peak,
        "incremental_peak_bytes": peak - baseline,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bf16", type=Path, required=True)
    parser.add_argument("--representation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    state_path = args.output / "INVOCATION_STATE.json"
    state = {
        "schema_version": 1,
        "candidate_cuda_invocation_started": False,
        "scientific_invocation_started": False,
        "completed_rows": [],
    }
    atomic_json(state_path, state)

    from sglang.srt.layers.quantization.fp8_kernel import sglang_per_token_quant_fp8
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    properties = torch.cuda.get_device_properties(0)
    if "H200" not in properties.name:
        raise RuntimeError(f"exact H200 required, observed {properties.name}")

    bf16 = load_file(str(args.bf16), device="cpu")["weight"]
    representation = load_file(str(args.representation), device="cpu")
    if bf16.dtype != torch.bfloat16 or tuple(bf16.shape) != (N, K):
        raise RuntimeError(f"BF16 tensor mismatch: {bf16.dtype} {tuple(bf16.shape)}")
    if representation["weight"].dtype != torch.float8_e4m3fn:
        raise RuntimeError(f"static FP8 tensor mismatch: {representation['weight'].dtype}")

    weight_bf16 = bf16.cuda().t()
    weight = representation["weight"].cuda().t()
    weight_scale = representation["weight_scale"].cuda()
    activation_scale_host = float(representation["activation_scale"].item())
    activation_scale = representation["activation_scale"].cuda()
    activation_inverse_scale = 1.0 / activation_scale_host
    if weight.stride() != (1, K) or weight_scale.numel() != N or activation_scale.numel() != 1:
        raise RuntimeError(
            f"consumer layout mismatch: weight={weight.stride()} ws={weight_scale.shape} as={activation_scale.shape}"
        )

    rows = []
    for tokens in (32, 2048):
        generator = torch.Generator(device="cuda").manual_seed(2026072300 + tokens)
        activation = torch.empty((tokens, K), device="cuda", dtype=torch.bfloat16)
        activation.normal_(mean=0.0, std=0.7, generator=generator)
        static_activation_scales = activation_scale.expand(tokens, 1).contiguous()
        if tuple(static_activation_scales.shape) != (tokens, 1):
            raise RuntimeError(
                f"static activation scale ABI mismatch: {static_activation_scales.shape}"
            )

        def control_quant() -> tuple[torch.Tensor, torch.Tensor]:
            return sglang_per_token_quant_fp8(activation)

        def control_component() -> torch.Tensor:
            quantized, scale = control_quant()
            return fp8_scaled_mm(
                quantized,
                weight,
                scale,
                weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        def candidate_component() -> torch.Tensor:
            quantized = static_fp8_quant(activation, activation_inverse_scale)
            return fp8_scaled_mm(
                quantized,
                weight,
                static_activation_scales,
                weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        state["candidate_cuda_invocation_started"] = True
        state["scientific_invocation_started"] = True
        atomic_json(state_path, state)
        candidate_output = candidate_component()
        control_output = control_component()
        torch.cuda.synchronize()
        reference = torch.matmul(activation.float(), weight_bf16.float()).to(torch.bfloat16)
        torch.cuda.synchronize()

        _, control_component_ms = cuda_samples(control_component)
        candidate_output, candidate_component_ms = cuda_samples(candidate_component)
        _, control_quant_ms = cuda_samples(lambda: control_quant()[0])
        _, candidate_quant_ms = cuda_samples(
            lambda: static_fp8_quant(activation, activation_inverse_scale)
        )
        control_delta = control_output.float() - reference.float()
        candidate_delta = candidate_output.float() - reference.float()
        control_l2 = (
            torch.linalg.vector_norm(control_delta)
            / torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
        ).item()
        candidate_l2 = (
            torch.linalg.vector_norm(candidate_delta)
            / torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
        ).item()
        candidate_cosine = torch.nn.functional.cosine_similarity(
            candidate_output.float().flatten(), reference.float().flatten(), dim=0
        ).item()
        saturation = (
            (activation.float().abs() / activation_scale).ge(FP8_MAX).float().mean().item()
        )
        control_timing = summarize(control_component_ms)
        candidate_timing = summarize(candidate_component_ms)
        row = {
            "tokens": tokens,
            "shape": [tokens, K, N],
            "control": {
                "representation": "dynamic_per_token_activation_fp8_static_per_channel_weight_fp8",
                "component_timing": control_timing,
                "quantization_timing": summarize(control_quant_ms),
                "relative_l2_error_vs_bf16": control_l2,
                "kernel_names": kernel_names(control_component),
                "allocation": peak_allocation(control_component),
            },
            "candidate": {
                "representation": "static_per_tensor_activation_fp8_static_per_channel_weight_fp8",
                "component_timing": candidate_timing,
                "quantization_timing": summarize(candidate_quant_ms),
                "relative_l2_error_vs_bf16": candidate_l2,
                "cosine_similarity_vs_bf16": candidate_cosine,
                "activation_saturation_fraction": saturation,
                "kernel_names": kernel_names(candidate_component),
                "allocation": peak_allocation(candidate_component),
            },
            "speedup_fraction": 1.0
            - candidate_timing["median_ms"] / control_timing["median_ms"],
            "numerical_pass": candidate_l2 <= 0.03 and candidate_cosine >= 0.999,
            "output_checksum": candidate_output.float().abs().mean().item(),
        }
        atomic_json(args.output / f"ROW_M{tokens}.json", row)
        rows.append(row)
        state["completed_rows"].append(tokens)
        atomic_json(state_path, state)

    decode = rows[0]
    terminal = {
        "schema_version": 1,
        "kind": "serialized_static_fp8_real_consumer_component",
        "consumer_symbol": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
        "candidate_quantizer_symbol": "static_fp8_quant_kernel",
        "runtime": {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": properties.name,
            "compute_capability": [properties.major, properties.minor],
            "fp8_scaled_mm_source_sha256": source_sha256(fp8_scaled_mm),
            "dynamic_quantizer_source_sha256": source_sha256(sglang_per_token_quant_fp8),
            "device_total_memory_bytes": properties.total_memory,
        },
        "serialized_representation": {
            "bf16_reference_bytes": args.bf16.stat().st_size,
            "static_fp8_representation_bytes": args.representation.stat().st_size,
            "size_reduction_fraction": 1.0
            - args.representation.stat().st_size / args.bf16.stat().st_size,
        },
        "rows": rows,
        "decode_component_speedup_fraction": decode["speedup_fraction"],
        "numerical_pass": all(row["numerical_pass"] for row in rows),
    }
    terminal["classification"] = (
        "component_positive"
        if terminal["numerical_pass"] and terminal["decode_component_speedup_fraction"] > 0
        else "component_negative"
    )
    terminal["pass"] = terminal["classification"] == "component_positive"
    atomic_json(args.output / "TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 20


if __name__ == "__main__":
    raise SystemExit(main())
