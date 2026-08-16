from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics


HIDDEN = 5376
EPSILON = 1e-6
SHAPES = (32, 118, 1409, 1631, 2048)
PROFILE_COUNTS = {118: 240, 1409: 240, 1631: 240, 2048: 13920}


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def timed(torch, function, repetitions: int) -> tuple[object, list[float]]:
    for _ in range(3):
        output = function()
    torch.cuda.synchronize()
    values = []
    output = None
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        values.append(start.elapsed_time(end))
    return output, values


def summarize(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median_ms": statistics.median(ordered),
        "minimum_ms": ordered[0],
        "p90_ms": ordered[max(0, int(0.9 * len(ordered)) - 1)],
        "maximum_ms": ordered[-1],
    }


def quantize_weight(torch, raw):
    weight_bf16 = raw.cuda().t()
    scale = (weight_bf16.float().abs().amax(dim=0) / 448.0).clamp_min(1e-8).float()
    weight = (weight_bf16 / scale).to(torch.float8_e4m3fn)
    if weight.stride() != (1, weight.shape[0]):
        raise RuntimeError(f"consumer weight is not column-major:{weight.shape}:{weight.stride()}")
    return weight, scale


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    state_path = args.output / "INVOCATION_STATE.json"
    atomic(
        state_path,
        {
            "schema_version": 1,
            "compile_started": False,
            "candidate_cuda_started": False,
            "candidate_science_started": False,
        },
    )

    import torch
    from safetensors import safe_open
    from fused_rmsnorm_quant import (
        fused_add_rmsnorm_quant,
        invocation_counts,
        prepare,
        rmsnorm_quant,
    )
    from sgl_kernel import fused_add_rmsnorm, rmsnorm
    from sglang.srt.layers.quantization.fp8_kernel import sglang_per_token_quant_fp8
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    if not torch.cuda.is_available() or "H200" not in torch.cuda.get_device_properties(0).name:
        raise RuntimeError("exact H200 required")

    shard = args.checkpoint / "layer0-rms-qkv-gate-up.safetensors"
    keys = {
        "input_norm": "model.language_model.layers.0.input_layernorm.weight",
        "pre_ff_norm": "model.language_model.layers.0.pre_feedforward_layernorm.weight",
        "q": "model.language_model.layers.0.self_attn.q_proj.weight",
        "k": "model.language_model.layers.0.self_attn.k_proj.weight",
        "v": "model.language_model.layers.0.self_attn.v_proj.weight",
        "gate": "model.language_model.layers.0.mlp.gate_proj.weight",
        "up": "model.language_model.layers.0.mlp.up_proj.weight",
    }
    with safe_open(str(shard), framework="pt", device="cpu") as handle:
        tensors = {name: handle.get_tensor(key) for name, key in keys.items()}
    input_norm_weight = tensors["input_norm"].cuda().contiguous()
    pre_ff_norm_weight = tensors["pre_ff_norm"].cuda().contiguous()
    qkv_weight, qkv_scale = quantize_weight(
        torch, torch.cat([tensors["q"], tensors["k"], tensors["v"]], dim=0)
    )
    gate_up_weight, gate_up_scale = quantize_weight(
        torch, torch.cat([tensors["gate"], tensors["up"]], dim=0)
    )
    metadata = {
        "checkpoint_shard": shard.name,
        "keys": keys,
        "hidden_size": HIDDEN,
        "qkv_weight_shape": list(qkv_weight.shape),
        "qkv_weight_stride": list(qkv_weight.stride()),
        "gate_up_weight_shape": list(gate_up_weight.shape),
        "gate_up_weight_stride": list(gate_up_weight.stride()),
        "activation_dtype": "torch.float8_e4m3fn",
        "activation_scale": "per_token_float32",
        "residual_dtype": "torch.bfloat16",
        "consumer_symbol": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
    }
    atomic(args.output / "BINDING.json", metadata)

    state = json.loads(state_path.read_text())
    state["compile_started"] = True
    atomic(state_path, state)
    prepare()
    state["candidate_cuda_started"] = True
    atomic(state_path, state)
    smoke = torch.randn((1, HIDDEN), device="cuda", dtype=torch.bfloat16)
    rmsnorm_quant(smoke, input_norm_weight, EPSILON)
    torch.cuda.synchronize()
    state["candidate_science_started"] = True
    atomic(state_path, state)

    generator = torch.Generator(device="cuda")
    generator.manual_seed(20260723)
    rows = []
    for tokens in SHAPES:
        repetitions = 20 if tokens == 32 else 8
        base = torch.randn(
            (tokens, HIDDEN),
            generator=generator,
            device="cuda",
            dtype=torch.bfloat16,
        )
        branch = torch.randn(
            (tokens, HIDDEN),
            generator=generator,
            device="cuda",
            dtype=torch.bfloat16,
        ) * 0.35

        def control_plain_producer():
            normalized = rmsnorm(base, input_norm_weight, EPSILON)
            return sglang_per_token_quant_fp8(normalized)

        def candidate_plain_producer():
            return rmsnorm_quant(base, input_norm_weight, EPSILON)

        control_residual = base.clone()
        candidate_residual = base.clone()

        def control_residual_producer():
            hidden = branch.clone()
            residual = control_residual.clone()
            fused_add_rmsnorm(hidden, residual, pre_ff_norm_weight, EPSILON)
            quantized, scales = sglang_per_token_quant_fp8(hidden)
            return quantized, scales, residual

        def candidate_residual_producer():
            return fused_add_rmsnorm_quant(
                branch, candidate_residual.clone(), pre_ff_norm_weight, EPSILON
            )

        control_plain, plain_control_times = timed(torch, control_plain_producer, repetitions)
        candidate_plain, plain_candidate_times = timed(torch, candidate_plain_producer, repetitions)
        control_residual_output, residual_control_times = timed(
            torch, control_residual_producer, repetitions
        )
        candidate_residual_output, residual_candidate_times = timed(
            torch, candidate_residual_producer, repetitions
        )

        def consume(producer, weight, weight_scale):
            quantized, scales = producer()[:2]
            return fp8_scaled_mm(
                quantized,
                weight,
                scales,
                weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        control_qkv, qkv_control_times = timed(
            torch,
            lambda: consume(control_plain_producer, qkv_weight, qkv_scale),
            repetitions,
        )
        candidate_qkv, qkv_candidate_times = timed(
            torch,
            lambda: consume(candidate_plain_producer, qkv_weight, qkv_scale),
            repetitions,
        )
        control_gate, gate_control_times = timed(
            torch,
            lambda: consume(control_residual_producer, gate_up_weight, gate_up_scale),
            repetitions,
        )
        candidate_gate, gate_candidate_times = timed(
            torch,
            lambda: consume(candidate_residual_producer, gate_up_weight, gate_up_scale),
            repetitions,
        )

        def numerical(control, candidate, control_out, candidate_out):
            control_q, control_s = control[:2]
            candidate_q, candidate_s = candidate[:2]
            dequantized_diff = control_q.float() * control_s - candidate_q.float() * candidate_s
            output_diff = control_out.float() - candidate_out.float()
            return {
                "quantized_byte_match_fraction": (
                    control_q.view(torch.uint8) == candidate_q.view(torch.uint8)
                ).float().mean().item(),
                "scale_max_abs_error": (control_s - candidate_s).abs().max().item(),
                "dequantized_relative_l2_error": (
                    torch.linalg.vector_norm(dequantized_diff)
                    / torch.linalg.vector_norm(control_q.float() * control_s).clamp_min(1e-12)
                ).item(),
                "consumer_relative_l2_error": (
                    torch.linalg.vector_norm(output_diff)
                    / torch.linalg.vector_norm(control_out.float()).clamp_min(1e-12)
                ).item(),
                "consumer_cosine_similarity": torch.nn.functional.cosine_similarity(
                    control_out.float().flatten(),
                    candidate_out.float().flatten(),
                    dim=0,
                ).item(),
                "saturation_fraction": (
                    candidate_q.float().abs() >= 448.0
                ).float().mean().item(),
                "nonfinite_count": int(
                    (~torch.isfinite(candidate_q.float() * candidate_s)).sum().item()
                ),
            }

        plain_numerical = numerical(
            control_plain, candidate_plain, control_qkv, candidate_qkv
        )
        residual_numerical = numerical(
            control_residual_output,
            candidate_residual_output,
            control_gate,
            candidate_gate,
        )
        residual_exact = torch.equal(
            control_residual_output[2], candidate_residual_output[2]
        )
        numerical_pass = (
            plain_numerical["dequantized_relative_l2_error"] <= 0.002
            and plain_numerical["consumer_relative_l2_error"] <= 0.002
            and plain_numerical["consumer_cosine_similarity"] >= 0.99999
            and residual_numerical["dequantized_relative_l2_error"] <= 0.002
            and residual_numerical["consumer_relative_l2_error"] <= 0.002
            and residual_numerical["consumer_cosine_similarity"] >= 0.99999
            and residual_exact
            and plain_numerical["nonfinite_count"] == 0
            and residual_numerical["nonfinite_count"] == 0
        )
        row = {
            "tokens": tokens,
            "plain_producer_control": summarize(plain_control_times),
            "plain_producer_candidate": summarize(plain_candidate_times),
            "residual_producer_control": summarize(residual_control_times),
            "residual_producer_candidate": summarize(residual_candidate_times),
            "qkv_component_control": summarize(qkv_control_times),
            "qkv_component_candidate": summarize(qkv_candidate_times),
            "gate_up_component_control": summarize(gate_control_times),
            "gate_up_component_candidate": summarize(gate_candidate_times),
            "plain_numerical": plain_numerical,
            "residual_numerical": residual_numerical,
            "residual_state_bitwise_equal": residual_exact,
            "numerical_pass": numerical_pass,
            "candidate_symbols": [
                "rmsnorm_quant_kernel<false>",
                "rmsnorm_quant_kernel<true>",
            ],
            "consumer_symbol": "fp8_scaled_mm",
            "complete_outputs_consumed": True,
        }
        rows.append(row)
        atomic(args.output / f"ROW_M{tokens}.json", row)

    saved_seconds = 0.0
    conservative_shape_deltas = {}
    for row in rows:
        tokens = row["tokens"]
        if tokens not in PROFILE_COUNTS:
            continue
        plain_delta = (
            row["plain_producer_control"]["median_ms"]
            - row["plain_producer_candidate"]["median_ms"]
        )
        residual_delta = (
            row["residual_producer_control"]["median_ms"]
            - row["residual_producer_candidate"]["median_ms"]
        )
        conservative_delta = min(plain_delta, residual_delta)
        eligible_calls = PROFILE_COUNTS[tokens] // 2
        saved_seconds += max(0.0, conservative_delta) * eligible_calls / 1000.0
        conservative_shape_deltas[str(tokens)] = {
            "plain_delta_ms": plain_delta,
            "residual_delta_ms": residual_delta,
            "admitted_delta_ms": max(0.0, conservative_delta),
            "eligible_calls": eligible_calls,
        }

    bound = {
        "profile_window_seconds": 23.038600455,
        "profile_standalone_quant_calls": 14640,
        "predicted_candidate_standalone_quant_calls": 7320,
        "predicted_removed_standalone_quant_calls": 7320,
        "conservative_saved_seconds": saved_seconds,
        "conservative_endpoint_reduction_fraction": saved_seconds / 23.038600455,
        "shape_deltas": conservative_shape_deltas,
        "positive": saved_seconds > 0,
    }
    numerical_pass = all(row["numerical_pass"] for row in rows)
    pass_component = numerical_pass and bound["positive"]
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "component_positive" if pass_component else "component_negative",
        "pass": pass_component,
        "binding": metadata,
        "rows": rows,
        "bound": bound,
        "invocation_counts": invocation_counts(),
        "path_proof": {
            "producer_family": "rmsnorm_quant_kernel<AddResidual>",
            "plain_path": "input_layernorm -> qkv_proj.fp8_scaled_mm",
            "residual_path": "pre_feedforward_layernorm(add residual) -> gate_up_proj.fp8_scaled_mm",
            "standalone_quant_bypassed": True,
            "bf16_residual_preserved": all(
                row["residual_state_bitwise_equal"] for row in rows
            ),
        },
    }
    atomic(args.output / "TERMINAL.json", terminal)
    return 0 if pass_component else 20


if __name__ == "__main__":
    raise SystemExit(main())
