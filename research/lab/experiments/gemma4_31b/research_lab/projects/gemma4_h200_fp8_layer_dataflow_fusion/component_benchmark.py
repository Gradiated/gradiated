#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import time


EXACT_INTERMEDIATE = 21504
EXACT_GATE_UP = 43008
EXACT_HIDDEN = 5376
PROFILE_DOWN_INVOCATIONS = 3660
PROFILE_DOWN_TOKENS = 7316520
PROFILE_BYTES_REMOVED = 944006676480


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def event_samples(torch, function, groups: int, repetitions: int) -> list[float]:
    for _ in range(3):
        function()
    torch.cuda.synchronize()
    samples = []
    for _ in range(groups):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(repetitions):
            function()
        end.record()
        end.synchronize()
        samples.append(start.elapsed_time(end) / repetitions)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--groups", type=int, default=7)
    parser.add_argument("--repetitions", type=int, default=8)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    invocation = args.output / "INVOCATION_STATE.json"
    atomic(
        invocation,
        {
            "schema_version": 1,
            "compile_started": False,
            "candidate_cuda_started": False,
            "candidate_science_started": False,
        },
    )

    import torch

    from fused_gelu_quant import (
        fused_gelu_tanh_mul_quant,
        invocation_count,
        prepare,
    )
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import sglang_per_token_quant_fp8
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    if not torch.cuda.is_available():
        raise RuntimeError("H200 CUDA component benchmark requires CUDA")
    device = torch.cuda.get_device_properties(0)
    if "H200" not in device.name:
        raise RuntimeError(f"exact component requires H200, observed {device.name}")

    state = json.loads(invocation.read_text())
    state["compile_started"] = True
    atomic(invocation, state)
    prepare()
    state["candidate_cuda_started"] = True
    state["candidate_science_started"] = True
    atomic(invocation, state)

    torch.manual_seed(20260722)
    activation = GeluAndMul(approximate="tanh")
    weight_bf16 = torch.empty(
        (EXACT_INTERMEDIATE, EXACT_HIDDEN),
        device="cuda",
        dtype=torch.bfloat16,
    ).normal_(mean=0.0, std=0.02)
    weight_scale = torch.full(
        (EXACT_HIDDEN,), 0.02 / 32.0, device="cuda", dtype=torch.float32
    )
    weight = (weight_bf16 / weight_scale.unsqueeze(0)).clamp(-448, 448).to(
        torch.float8_e4m3fn
    )
    del weight_bf16

    rows = []
    for tokens in (32, 2048):
        gate_up = torch.empty(
            (tokens, EXACT_GATE_UP), device="cuda", dtype=torch.bfloat16
        ).normal_(mean=0.0, std=0.7)

        def control_boundary():
            activated = activation(gate_up)
            return sglang_per_token_quant_fp8(activated)

        def candidate_boundary():
            return fused_gelu_tanh_mul_quant(gate_up)

        control_quantized, control_scale = control_boundary()
        candidate_quantized, candidate_scale = candidate_boundary()
        control_dequantized = control_quantized.float() * control_scale
        candidate_dequantized = candidate_quantized.float() * candidate_scale
        activation_difference = candidate_dequantized - control_dequantized

        def control_component():
            quantized, scales = control_boundary()
            return fp8_scaled_mm(
                quantized,
                weight,
                scales,
                weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        def candidate_component():
            quantized, scales = candidate_boundary()
            return fp8_scaled_mm(
                quantized,
                weight,
                scales,
                weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        control_output = control_component().float()
        candidate_output = candidate_component().float()
        output_difference = candidate_output - control_output
        relative_l2 = (
            torch.linalg.vector_norm(output_difference)
            / torch.linalg.vector_norm(control_output).clamp_min(1e-12)
        ).item()
        cosine = torch.nn.functional.cosine_similarity(
            control_output.flatten(), candidate_output.flatten(), dim=0
        ).item()

        control_boundary_ms = event_samples(
            torch, control_boundary, args.groups, args.repetitions
        )
        candidate_boundary_ms = event_samples(
            torch, candidate_boundary, args.groups, args.repetitions
        )
        control_component_ms = event_samples(
            torch, control_component, args.groups, args.repetitions
        )
        candidate_component_ms = event_samples(
            torch, candidate_component, args.groups, args.repetitions
        )
        row = {
            "tokens": tokens,
            "gate_up_shape": [tokens, EXACT_GATE_UP],
            "down_weight_shape": [EXACT_INTERMEDIATE, EXACT_HIDDEN],
            "control_boundary_ms": control_boundary_ms,
            "candidate_boundary_ms": candidate_boundary_ms,
            "control_component_ms": control_component_ms,
            "candidate_component_ms": candidate_component_ms,
            "control_boundary_median_ms": statistics.median(control_boundary_ms),
            "candidate_boundary_median_ms": statistics.median(candidate_boundary_ms),
            "control_component_median_ms": statistics.median(control_component_ms),
            "candidate_component_median_ms": statistics.median(candidate_component_ms),
            "boundary_reduction_fraction": 1
            - statistics.median(candidate_boundary_ms)
            / statistics.median(control_boundary_ms),
            "component_reduction_fraction": 1
            - statistics.median(candidate_component_ms)
            / statistics.median(control_component_ms),
            "activation_dequantized_max_abs_error": activation_difference.abs()
            .max()
            .item(),
            "activation_dequantized_mean_abs_error": activation_difference.abs()
            .mean()
            .item(),
            "scale_max_abs_error": (candidate_scale - control_scale).abs().max().item(),
            "output_max_abs_error": output_difference.abs().max().item(),
            "output_relative_l2_error": relative_l2,
            "output_cosine_similarity": cosine,
            "quantized_exact_fraction": (
                candidate_quantized.float() == control_quantized.float()
            )
            .float()
            .mean()
            .item(),
            "bytes_removed_per_invocation": tokens * EXACT_INTERMEDIATE * 6,
            "launches_removed_per_invocation": 1,
        }
        row["numerical_pass"] = relative_l2 <= 0.01 and cosine >= 0.9999
        row["timing_pass"] = (
            row["candidate_boundary_median_ms"] < row["control_boundary_median_ms"]
            and row["candidate_component_median_ms"]
            < row["control_component_median_ms"]
        )
        rows.append(row)
        atomic(args.output / f"ROW_M{tokens}.json", row)
        del gate_up, control_output, candidate_output

    terminal = {
        "schema_version": 1,
        "kind": "gemma4_h200_fused_gelu_tanh_dynamic_fp8_down_component",
        "timestamp_unix_s": time.time(),
        "device": {
            "name": device.name,
            "sm_count": device.multi_processor_count,
            "major": device.major,
            "minor": device.minor,
        },
        "candidate_symbol": "fused_gelu_tanh_mul_quant_kernel",
        "stock_activation_symbol": "act_and_mul_kernel<...,ActivationKind=gelu_tanh>",
        "stock_quant_symbol": "per_token_quant_fp8_small_batch_kernel",
        "consumer_symbol": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
        "rows": rows,
        "candidate_invocations": invocation_count(),
        "profile_projection": {
            "down_quant_invocations": PROFILE_DOWN_INVOCATIONS,
            "down_quant_tokens": PROFILE_DOWN_TOKENS,
            "bf16_hbm_bytes_removed": PROFILE_BYTES_REMOVED,
            "launches_removed": PROFILE_DOWN_INVOCATIONS,
            "derivation": "six BF16 bytes per activated element: one output write plus two stock quant reads",
        },
        "numerical_pass": all(row["numerical_pass"] for row in rows),
        "timing_pass": all(row["timing_pass"] for row in rows),
    }
    terminal["pass"] = terminal["numerical_pass"] and terminal["timing_pass"]
    terminal["classification"] = (
        "component_positive" if terminal["pass"] else "component_negative"
    )
    atomic(args.output / "TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 20


if __name__ == "__main__":
    raise SystemExit(main())
