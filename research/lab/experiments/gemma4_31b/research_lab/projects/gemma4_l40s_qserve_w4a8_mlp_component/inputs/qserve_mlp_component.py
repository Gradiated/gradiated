#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
from typing import Any, Callable


MS = (1, 2, 4, 8, 12, 16, 24, 32)
HIDDEN = 5376
INTERMEDIATE = 21504
GATE_UP = 43008
GROUP_SIZE = 128
LAYERS = 60
DECODE_STEPS = 357
CONTROL_REQUEST_SECONDS = 0.6746877474374742
SEED = 20260724


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(project: pathlib.Path, manifest_path: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    failures = []
    for relative, expected in manifest["files"].items():
        path = project / relative
        observed = sha256(path) if path.is_file() else None
        if observed != expected:
            failures.append(
                {"path": relative, "expected_sha256": expected, "observed_sha256": observed}
            )
    if failures:
        raise RuntimeError(f"immutable_manifest_mismatch:{json.dumps(failures)}")
    return manifest


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "raw_ms": values,
        "minimum_ms": ordered[0],
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def timed(torch, function: Callable[[], Any], warmups: int, iterations: int):
    output = None
    for _ in range(warmups):
        output = function()
    torch.cuda.synchronize()
    values = []
    for _ in range(iterations):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
    return distribution(values), output


def error_metrics(torch, actual, reference) -> dict[str, Any]:
    actual32 = actual.float()
    reference32 = reference.float()
    delta = actual32 - reference32
    norm = torch.linalg.vector_norm(reference32).clamp_min(1e-12)
    return {
        "maximum_absolute": float(delta.abs().max()),
        "relative_l2": float(torch.linalg.vector_norm(delta) / norm),
        "cosine_similarity": float(
            torch.nn.functional.cosine_similarity(
                actual32.flatten(), reference32.flatten(), dim=0
            )
        ),
        "nonfinite_count": int((~torch.isfinite(actual32)).sum()),
        "nontrivial": bool(float(actual32.abs().max()) > 1e-8),
    }


def qserve_pack_codes(torch, codes):
    output_features, input_features = codes.shape
    reordered = (
        codes.reshape(
            output_features // 32,
            2,
            2,
            8,
            input_features // 32,
            2,
            4,
            4,
        )
        .permute(0, 4, 3, 6, 1, 5, 2, 7)
        .contiguous()
        .permute(0, 1, 2, 3, 5, 6, 7, 4)
        .contiguous()
    )
    packed = (
        (reordered[..., 1].to(torch.int16) << 4)
        | reordered[..., 0].to(torch.int16)
    )
    return packed.to(torch.uint8).view(torch.int8).reshape(
        output_features, input_features // 2
    )


def qserve_reorder_group_metadata(tensor):
    output_features, groups = tensor.shape
    return (
        tensor.transpose(0, 1)
        .contiguous()
        .reshape(groups, output_features // 32, 4, 8)
        .transpose(-2, -1)
        .contiguous()
        .reshape(groups, output_features)
    )


def progressive_weight(torch, output_features: int, input_features: int, seed: int):
    if output_features % 64 or input_features % GROUP_SIZE:
        raise ValueError("QServe layout requires N%64==0 and K%128==0")
    qweight_chunks = []
    scale_chunks = []
    zero_chunks = []
    oracle_chunks = []
    groups = input_features // GROUP_SIZE
    group_ids = torch.arange(groups, device="cuda", dtype=torch.int32)
    columns = torch.arange(input_features, device="cuda", dtype=torch.int32)
    chunk_size = 512
    for start in range(0, output_features, chunk_size):
        count = min(chunk_size, output_features - start)
        rows = torch.arange(start, start + count, device="cuda", dtype=torch.int32)
        codes = (
            (rows[:, None] * 13 + columns[None, :] * 7 + seed) & 15
        ).to(torch.int8)
        stage2 = (
            ((rows[:, None] + group_ids[None, :] * 3 + seed) % 3) + 1
        ).to(torch.int8)
        stage1_scale = (
            0.0015 + (rows % 17).float() * 0.00003
        ).to(torch.float16)
        expanded_stage2 = stage2.repeat_interleave(GROUP_SIZE, dim=1)
        stage1_values = (
            (codes.to(torch.int16) - 7) * expanded_stage2.to(torch.int16)
        )
        oracle = (
            stage1_values.float() * stage1_scale.float().unsqueeze(1)
        ).to(torch.float16)
        packed_stage2 = qserve_reorder_group_metadata(stage2)
        qweight_chunks.append(qserve_pack_codes(torch, codes))
        scale_chunks.append(packed_stage2)
        zero_chunks.append((-7 * packed_stage2.to(torch.int16)).to(torch.int8))
        oracle_chunks.append(oracle)
    qweight = torch.cat(qweight_chunks, dim=0).contiguous()
    scales_i8 = torch.cat(scale_chunks, dim=1).contiguous()
    zeros = torch.cat(zero_chunks, dim=1).contiguous()
    oracle = torch.cat(oracle_chunks, dim=0).contiguous()
    rows = torch.arange(output_features, device="cuda", dtype=torch.int32)
    weight_scales = (
        0.0015 + (rows % 17).float() * 0.00003
    ).to(torch.float16).contiguous()
    return {
        "qweight": qweight,
        "scales_i8": scales_i8,
        "zeros": zeros,
        "weight_scales": weight_scales,
        "oracle": oracle,
    }


def fp8_weight(torch, oracle):
    weight_bf16 = oracle.to(torch.bfloat16).t()
    scale = (
        weight_bf16.float().abs().amax(dim=0).div(448.0).clamp_min(1e-8).float()
    )
    return (weight_bf16 / scale).to(torch.float8_e4m3fn), scale


def chunked_reference_mm(torch, activation, weight, chunk: int = 2048):
    outputs = []
    for start in range(0, weight.size(0), chunk):
        stop = min(start + chunk, weight.size(0))
        outputs.append(torch.mm(activation.float(), weight[start:stop].t().float()))
    return torch.cat(outputs, dim=1)


def reference_chain(torch, xq, input_scales, gate_up_weight, down_weight):
    dequantized_input = xq.float() * input_scales.float().unsqueeze(1)
    gate_up = chunked_reference_mm(torch, dequantized_input, gate_up_weight).half()
    gate = gate_up[:, :INTERMEDIATE].float()
    up = gate_up[:, INTERMEDIATE:].float()
    activated = torch.nn.functional.gelu(gate, approximate="tanh") * up
    absolute_max = activated.abs().amax(dim=1)
    float_scales = torch.where(
        absolute_max > 0,
        absolute_max / 127.0,
        torch.ones_like(absolute_max),
    )
    quantized = torch.round(activated / float_scales[:, None]).clamp(-127, 127)
    half_scales = float_scales.half()
    dequantized = quantized.float() * half_scales.float().unsqueeze(1)
    return chunked_reference_mm(torch, dequantized, down_weight).half()


def profiler_kernel_names(torch, function: Callable[[], Any]) -> list[str]:
    with torch.profiler.profile(
        activities=[torch.profiler.ProfilerActivity.CUDA]
    ) as profile:
        output = function()
        output.float().square().sum().item()
    return sorted(
        {
            event.name
            for event in profile.events()
            if str(event.device_type).lower().endswith("cuda")
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=50)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    invocation_path = args.output / "INVOCATION_STATE.json"
    state = {
        "schema_version": 1,
        "candidate_cuda_started": False,
        "candidate_science_started": False,
        "control_science_started": False,
        "completed_m": [],
    }
    atomic_json(invocation_path, state)
    manifest = verify_manifest(args.project, args.manifest)

    import torch
    import qserve_sm89
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization import fp8_utils
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("typed_hardware_blocker:cuda_unavailable")
    properties = torch.cuda.get_device_properties(0)
    if "L40S" not in properties.name or (properties.major, properties.minor) != (8, 9):
        raise RuntimeError(
            f"typed_hardware_blocker:exact_l40s_sm89_required:{properties.name}:"
            f"{properties.major}.{properties.minor}"
        )

    torch.manual_seed(SEED)
    gate_up_candidate = progressive_weight(torch, GATE_UP, HIDDEN, SEED + 1)
    down_candidate = progressive_weight(torch, HIDDEN, INTERMEDIATE, SEED + 2)
    gate_up_fp8, gate_up_fp8_scale = fp8_weight(
        torch, gate_up_candidate["oracle"]
    )
    down_fp8, down_fp8_scale = fp8_weight(torch, down_candidate["oracle"])
    activation = GeluAndMul(approximate="tanh")

    rows = []
    m32_candidate = None
    m32_control = None
    m32_x = None
    m32_buffers = None
    for m in MS:
        generator = torch.Generator(device="cuda").manual_seed(SEED * 100 + m)
        x = torch.empty((m, HIDDEN), device="cuda", dtype=torch.bfloat16)
        x.normal_(mean=0.0, std=0.7, generator=generator)
        buffers = {
            "xq": torch.empty_like(x, dtype=torch.int8),
            "xs": torch.empty((m,), device="cuda", dtype=torch.float16),
            "gate_up": torch.empty((m, GATE_UP), device="cuda", dtype=torch.float16),
            "aq": torch.empty((m, INTERMEDIATE), device="cuda", dtype=torch.int8),
            "as": torch.empty((m,), device="cuda", dtype=torch.float16),
            "output": torch.empty((m, HIDDEN), device="cuda", dtype=torch.float16),
        }

        def candidate_chain(x=x, buffers=buffers):
            qserve_sm89.quantize_bf16_s8(x, buffers["xq"], buffers["xs"])
            qserve_sm89.w4a8_gemm(
                buffers["xq"],
                gate_up_candidate["qweight"],
                gate_up_candidate["zeros"],
                gate_up_candidate["scales_i8"],
                gate_up_candidate["weight_scales"],
                buffers["xs"],
                buffers["gate_up"],
            )
            qserve_sm89.gelu_mul_quant_s8(
                buffers["gate_up"], buffers["aq"], buffers["as"]
            )
            qserve_sm89.w4a8_gemm(
                buffers["aq"],
                down_candidate["qweight"],
                down_candidate["zeros"],
                down_candidate["scales_i8"],
                down_candidate["weight_scales"],
                buffers["as"],
                buffers["output"],
            )
            return buffers["output"]

        def control_chain(x=x):
            xq, xs = sglang_per_token_quant_fp8(x)
            gate_up = fp8_utils.fp8_scaled_mm(
                xq,
                gate_up_fp8,
                xs,
                gate_up_fp8_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )
            activated = activation(gate_up)
            aq, activation_scale = sglang_per_token_quant_fp8(activated)
            return fp8_utils.fp8_scaled_mm(
                aq,
                down_fp8,
                activation_scale,
                down_fp8_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        state["candidate_cuda_started"] = True
        atomic_json(invocation_path, state)
        candidate = candidate_chain()
        torch.cuda.synchronize()
        state["candidate_science_started"] = True
        atomic_json(invocation_path, state)
        reference = reference_chain(
            torch,
            buffers["xq"],
            buffers["xs"],
            gate_up_candidate["oracle"],
            down_candidate["oracle"],
        )
        control = control_chain()
        torch.cuda.synchronize()
        state["control_science_started"] = True
        atomic_json(invocation_path, state)
        candidate_timing, candidate = timed(
            torch, candidate_chain, args.warmups, args.iterations
        )
        control_timing, control = timed(
            torch, control_chain, args.warmups, args.iterations
        )
        candidate_error = error_metrics(torch, candidate, reference)
        control_error = error_metrics(torch, control, reference)
        row = {
            "m": m,
            "shape": {
                "gate_up": [m, HIDDEN, GATE_UP],
                "activation": [m, GATE_UP, INTERMEDIATE],
                "down": [m, INTERMEDIATE, HIDDEN],
            },
            "candidate": {
                "timing": candidate_timing,
                "vs_dequantized_w4_oracle": candidate_error,
                "input_saturation_fraction": float(
                    (buffers["xq"].abs() == 127).float().mean()
                ),
                "intermediate_saturation_fraction": float(
                    (buffers["aq"].abs() == 127).float().mean()
                ),
                "output_consumed_sum_squares": float(
                    candidate.float().square().sum()
                ),
            },
            "control": {
                "timing": control_timing,
                "vs_dequantized_w4_oracle": control_error,
                "output_consumed_sum_squares": float(
                    control.float().square().sum()
                ),
            },
            "speedup": (
                control_timing["p50_ms"] / candidate_timing["p50_ms"]
            ),
            "correctness_pass": (
                candidate_error["nonfinite_count"] == 0
                and candidate_error["relative_l2"] <= 0.02
                and candidate_error["cosine_similarity"] >= 0.999
            ),
        }
        rows.append(row)
        atomic_json(args.output / f"ROW_M{m}.json", row)
        state["completed_m"].append(m)
        atomic_json(invocation_path, state)
        if m == 32:
            m32_candidate = candidate_chain
            m32_control = control_chain
            m32_x = x
            m32_buffers = buffers

    boundary_rows = []
    for name, value in (("zero", 0.0), ("positive_extreme", 4.0), ("negative_extreme", -4.0)):
        x = torch.full((1, HIDDEN), value, device="cuda", dtype=torch.bfloat16)
        buffers = {
            "xq": torch.empty_like(x, dtype=torch.int8),
            "xs": torch.empty((1,), device="cuda", dtype=torch.float16),
            "gate_up": torch.empty((1, GATE_UP), device="cuda", dtype=torch.float16),
            "aq": torch.empty((1, INTERMEDIATE), device="cuda", dtype=torch.int8),
            "as": torch.empty((1,), device="cuda", dtype=torch.float16),
            "output": torch.empty((1, HIDDEN), device="cuda", dtype=torch.float16),
        }
        qserve_sm89.quantize_bf16_s8(x, buffers["xq"], buffers["xs"])
        qserve_sm89.w4a8_gemm(
            buffers["xq"],
            gate_up_candidate["qweight"],
            gate_up_candidate["zeros"],
            gate_up_candidate["scales_i8"],
            gate_up_candidate["weight_scales"],
            buffers["xs"],
            buffers["gate_up"],
        )
        qserve_sm89.gelu_mul_quant_s8(
            buffers["gate_up"], buffers["aq"], buffers["as"]
        )
        qserve_sm89.w4a8_gemm(
            buffers["aq"],
            down_candidate["qweight"],
            down_candidate["zeros"],
            down_candidate["scales_i8"],
            down_candidate["weight_scales"],
            buffers["as"],
            buffers["output"],
        )
        torch.cuda.synchronize()
        boundary_rows.append(
            {
                "case": name,
                "finite": bool(torch.isfinite(buffers["output"]).all()),
                "output_sum_squares": float(buffers["output"].float().square().sum()),
            }
        )

    assert m32_candidate is not None and m32_control is not None
    candidate_kernels = profiler_kernel_names(torch, m32_candidate)
    control_kernels = profiler_kernel_names(torch, m32_control)
    row32 = next(row for row in rows if row["m"] == 32)
    saved_seconds = (
        row32["control"]["timing"]["p50_ms"]
        - row32["candidate"]["timing"]["p50_ms"]
    ) / 1000.0 * LAYERS * DECODE_STEPS / 32
    physical = {
        "useful_flops_m32": int(
            2
            * 32
            * (HIDDEN * GATE_UP + INTERMEDIATE * HIDDEN)
        ),
        "packed_weight_bytes": int(
            (HIDDEN * GATE_UP + INTERMEDIATE * HIDDEN) / 2
        ),
        "fp8_weight_bytes": int(
            HIDDEN * GATE_UP + INTERMEDIATE * HIDDEN
        ),
        "w4_arithmetic_intensity_flop_per_weight_byte_m32": 128.0,
        "fp8_arithmetic_intensity_flop_per_weight_byte_m32": 64.0,
        "gate_up_grid_blocks": GATE_UP // 64,
        "gate_up_grid_waves_l40s": (GATE_UP // 64) / 142,
        "down_grid_blocks": HIDDEN // 64,
        "down_grid_waves_l40s": (HIDDEN // 64) / 142,
        "candidate_dynamic_shared_memory_bytes": 24960,
        "candidate_threads_per_block": 128,
    }
    terminal = {
        "schema_version": 1,
        "classification": "component_complete",
        "pass": (
            all(row["correctness_pass"] for row in rows)
            and all(row["finite"] for row in boundary_rows)
        ),
        "identity": {
            "gpu": properties.name,
            "capability": [properties.major, properties.minor],
            "sm_count": properties.multi_processor_count,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "manifest_sha256": sha256(args.manifest),
            "manifest": manifest,
            "candidate_symbols": [
                "qserve_sm89.quantize_bf16_s8",
                "qserve_sm89.w4a8_gemm",
                "qserve_sm89.gelu_mul_quant_s8",
            ],
            "control_symbols": [
                "sglang.srt.layers.quantization.fp8_kernel.sglang_per_token_quant_fp8",
                "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
                "sglang.srt.layers.activation.GeluAndMul",
            ],
        },
        "physical_model": physical,
        "candidate_kernel_names_m32": candidate_kernels,
        "control_kernel_names_m32": control_kernels,
        "candidate_path_pass": (
            any("dense_kernel0" in name for name in candidate_kernels)
            and any("gelu_mul_quant_s8_kernel" in name for name in candidate_kernels)
        ),
        "boundary_rows": boundary_rows,
        "rows": rows,
        "call_weighted_bound": {
            "basis": "M32 p50, 60 MLP layers, 357 post-first-token decode steps, 32 requests",
            "saved_seconds_per_request": saved_seconds,
            "whole_request_reduction_fraction": saved_seconds
            / CONTROL_REQUEST_SECONDS,
            "control_request_seconds": CONTROL_REQUEST_SECONDS,
        },
        "complete_outputs_consumed": True,
    }
    terminal["pass"] = bool(terminal["pass"] and terminal["candidate_path_pass"])
    terminal["classification"] = (
        "component_positive"
        if terminal["pass"] and row32["speedup"] > 1.0
        else "component_correct_but_slower"
        if terminal["pass"]
        else "component_reject"
    )
    atomic_json(args.output / "TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 72


if __name__ == "__main__":
    raise SystemExit(main())
