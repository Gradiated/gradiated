#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import statistics


HIDDEN = 5376
EPSILON = 1e-6
PRIMARY_ROWS = 32
SHAPES = (1, 16, 32)
EXPECTED_ROWS = len(SHAPES)
KEYS = {
    "input_norm": "model.language_model.layers.0.input_layernorm.weight",
    "q": "model.language_model.layers.0.self_attn.q_proj.weight",
    "k": "model.language_model.layers.0.self_attn.k_proj.weight",
    "v": "model.language_model.layers.0.self_attn.v_proj.weight",
}


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def contract() -> dict[str, object]:
    return {
        "schema_version": 1,
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "runtime_image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        "runtime": "sglang v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        "hardware": "NVIDIA H200 SXM / sm_90a",
        "producer_control": "sgl_kernel.rmsnorm + sglang_per_token_quant_fp8",
        "producer_candidate": (
            "gemma4_decode_rmsnorm_quant_e4m3_exact_order"
        ),
        "consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
        "correctness_gate": {
            "activation_bytes": "exact",
            "scale_bytes": "exact",
            "consumer_output_bytes": "exact",
        },
        "geometry": {
            "input": [PRIMARY_ROWS, HIDDEN],
            "input_dtype": "bfloat16",
            "input_stride": [HIDDEN, 1],
            "qkv_weight_k_n": [HIDDEN, 16384],
            "activation_dtype": "float8_e4m3fn",
            "activation_scale": [PRIMARY_ROWS, 1],
            "activation_scale_dtype": "float32",
        },
        "row_ledger": {
            "shapes": list(SHAPES),
            "expected_rows": EXPECTED_ROWS,
            "required_fields": [
                "baseline_producer",
                "candidate_producer",
                "baseline_component",
                "candidate_component",
                "numerical",
                "candidate_path",
            ],
        },
    }


def summarize(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median_ms": statistics.median(ordered),
        "minimum_ms": ordered[0],
        "p90_ms": ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)],
        "maximum_ms": ordered[-1],
    }


def timed(torch, function, repetitions: int):
    for _ in range(5):
        output = function()
    torch.cuda.synchronize()
    samples = []
    output = None
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        samples.append(start.elapsed_time(end))
    return output, samples


def quantize_qkv_weight(torch, tensors):
    raw = torch.cat([tensors["q"], tensors["k"], tensors["v"]], dim=0)
    weight_bf16 = raw.cuda().t()
    scale = (
        weight_bf16.float().abs().amax(dim=0) / 448.0
    ).clamp_min(1e-8).float()
    weight = (weight_bf16 / scale).to(torch.float8_e4m3fn)
    if weight.shape != (HIDDEN, 16384):
        raise RuntimeError(f"unexpected QKV weight shape: {weight.shape}")
    if weight.stride() != (1, HIDDEN):
        raise RuntimeError(
            f"QKV consumer weight is not column-major: {weight.stride()}"
        )
    return weight, scale


def numerical(torch, control, candidate, control_out, candidate_out):
    control_q, control_scale = control
    candidate_q, candidate_scale = candidate
    control_dequantized = control_q.float() * control_scale
    candidate_dequantized = candidate_q.float() * candidate_scale
    dequantized_difference = control_dequantized - candidate_dequantized
    output_difference = control_out.float() - candidate_out.float()
    dequantized_relative_l2 = (
        torch.linalg.vector_norm(dequantized_difference)
        / torch.linalg.vector_norm(control_dequantized).clamp_min(1e-12)
    ).item()
    consumer_relative_l2 = (
        torch.linalg.vector_norm(output_difference)
        / torch.linalg.vector_norm(control_out.float()).clamp_min(1e-12)
    ).item()
    cosine = torch.nn.functional.cosine_similarity(
        control_out.float().flatten(),
        candidate_out.float().flatten(),
        dim=0,
    ).item()
    result = {
        "dequantized_relative_l2_error": dequantized_relative_l2,
        "consumer_relative_l2_error": consumer_relative_l2,
        "consumer_cosine_similarity": cosine,
        "quantized_byte_match_fraction": (
            control_q.view(torch.uint8) == candidate_q.view(torch.uint8)
        ).float().mean().item(),
        "scale_max_abs_error": (
            control_scale - candidate_scale
        ).abs().max().item(),
        "candidate_saturation_fraction": (
            candidate_q.float().abs() >= 448.0
        ).float().mean().item(),
        "candidate_nonfinite_count": int(
            (~torch.isfinite(candidate_dequantized)).sum().item()
        ),
        "complete_output_elements_consumed": int(candidate_out.numel()),
    }
    result["activation_bytes_exact"] = (
        result["quantized_byte_match_fraction"] == 1.0
    )
    result["scale_bytes_exact"] = bool(
        torch.equal(
            control_scale.view(torch.uint8),
            candidate_scale.view(torch.uint8),
        )
    )
    result["consumer_bytes_exact"] = bool(
        torch.equal(
            control_out.view(torch.uint8),
            candidate_out.view(torch.uint8),
        )
    )
    result["pass"] = (
        result["activation_bytes_exact"]
        and result["scale_bytes_exact"]
        and result["consumer_bytes_exact"]
        and result["candidate_nonfinite_count"] == 0
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--component-safetensors", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--repetitions", type=int, default=100)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(contract(), indent=2, sort_keys=True))
        return 0
    if args.component_safetensors is None or args.output is None:
        parser.error("--component-safetensors and --output are required")
    args.output.mkdir(parents=True, exist_ok=False)
    atomic(args.output / "CONTRACT.json", contract())
    state = {
        "schema_version": 1,
        "identity_validated": False,
        "science_started": False,
        "baseline_first_call_completed": False,
        "candidate_first_call_completed": False,
        "rows_completed": 0,
    }
    atomic(args.output / "INVOCATION_STATE.json", state)

    import torch
    from safetensors import safe_open

    from norm_fp8_decode_exact_order import (
        gemma4_decode_norm_fp8_exact_order,
        prepare,
    )
    from sgl_kernel import rmsnorm
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    if not torch.cuda.is_available():
        raise RuntimeError("exact H200 sm90 required, CUDA is unavailable")
    properties = torch.cuda.get_device_properties(0)
    if (
        "H200" not in properties.name
        or properties.major != 9
        or properties.minor != 0
    ):
        raise RuntimeError(f"exact H200 sm90 required, got {properties}")
    with safe_open(
        str(args.component_safetensors), framework="pt", device="cpu"
    ) as handle:
        missing = sorted(set(KEYS.values()) - set(handle.keys()))
        if missing:
            raise RuntimeError(f"missing exact component tensors: {missing}")
        tensors = {
            name: handle.get_tensor(key) for name, key in KEYS.items()
        }
    norm_weight = tensors["input_norm"].cuda().contiguous()
    qkv_weight, qkv_weight_scale = quantize_qkv_weight(torch, tensors)
    identity = contract()
    identity["loaded_component"] = {
        "path": str(args.component_safetensors.resolve()),
        "keys": KEYS,
        "norm_weight_shape": list(norm_weight.shape),
        "norm_weight_stride": list(norm_weight.stride()),
        "qkv_weight_shape": list(qkv_weight.shape),
        "qkv_weight_stride": list(qkv_weight.stride()),
        "qkv_weight_scale_shape": list(qkv_weight_scale.shape),
    }
    atomic(args.output / "IDENTITY.json", identity)
    state["identity_validated"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)

    prepare()
    generator = torch.Generator(device="cuda")
    generator.manual_seed(20260729)
    smoke = torch.randn(
        (1, HIDDEN),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    )

    def baseline_producer(value):
        return sglang_per_token_quant_fp8(
            rmsnorm(value, norm_weight, EPSILON)
        )

    def candidate_producer(value):
        return gemma4_decode_norm_fp8_exact_order(
            value, norm_weight, EPSILON
        )

    state["science_started"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)
    baseline_producer(smoke)
    torch.cuda.synchronize()
    state["baseline_first_call_completed"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)
    candidate_producer(smoke)
    torch.cuda.synchronize()
    state["candidate_first_call_completed"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)

    graph_input = torch.randn(
        (PRIMARY_ROWS, HIDDEN),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    )

    def graph_component():
        quantized, scales = candidate_producer(graph_input)
        return fp8_scaled_mm(
            quantized,
            qkv_weight,
            scales,
            qkv_weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )

    graph_component()
    torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        graph_output = graph_component()
    graph.replay()
    torch.cuda.synchronize()
    replay_output = graph_output.clone()
    direct_output = graph_component()
    torch.cuda.synchronize()
    graph_relative_l2 = (
        torch.linalg.vector_norm(
            replay_output.float() - direct_output.float()
        )
        / torch.linalg.vector_norm(direct_output.float()).clamp_min(1e-12)
    ).item()
    graph_proof = {
        "captured_shape": [PRIMARY_ROWS, HIDDEN],
        "candidate_and_consumer_captured": True,
        "replay_output_elements_consumed": int(replay_output.numel()),
        "replay_vs_direct_relative_l2_error": graph_relative_l2,
        "pass": graph_relative_l2 == 0.0,
    }
    atomic(args.output / "CUDA_GRAPH_PROOF.json", graph_proof)

    rows = []
    for tokens in SHAPES:
        value = torch.randn(
            (tokens, HIDDEN),
            generator=generator,
            device="cuda",
            dtype=torch.bfloat16,
        )

        def consume(producer):
            quantized, scales = producer(value)
            return fp8_scaled_mm(
                quantized,
                qkv_weight,
                scales,
                qkv_weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        control, baseline_producer_samples = timed(
            torch,
            lambda: baseline_producer(value),
            args.repetitions,
        )
        candidate, candidate_producer_samples = timed(
            torch,
            lambda: candidate_producer(value),
            args.repetitions,
        )
        control_output, baseline_component_samples = timed(
            torch,
            lambda: consume(baseline_producer),
            args.repetitions,
        )
        candidate_output, candidate_component_samples = timed(
            torch,
            lambda: consume(candidate_producer),
            args.repetitions,
        )
        row = {
            "tokens": tokens,
            "baseline_producer": summarize(baseline_producer_samples),
            "candidate_producer": summarize(candidate_producer_samples),
            "baseline_component": summarize(baseline_component_samples),
            "candidate_component": summarize(candidate_component_samples),
            "numerical": numerical(
                torch,
                control,
                candidate,
                control_output,
                candidate_output,
            ),
            "candidate_path": {
                "producer": (
                    "gemma4_decode_rmsnorm_quant_e4m3_exact_order"
                ),
                "consumer": "fp8_scaled_mm",
                "activation_shape": list(candidate[0].shape),
                "activation_stride": list(candidate[0].stride()),
                "activation_dtype": str(candidate[0].dtype),
                "scale_shape": list(candidate[1].shape),
                "scale_stride": list(candidate[1].stride()),
                "scale_dtype": str(candidate[1].dtype),
            },
        }
        atomic(args.output / f"ROW_M{tokens}.json", row)
        rows.append(row)
        state["rows_completed"] = len(rows)
        atomic(args.output / "INVOCATION_STATE.json", state)

    primary = next(row for row in rows if row["tokens"] == PRIMARY_ROWS)
    ledger_complete = (
        len(rows) == EXPECTED_ROWS
        and {row["tokens"] for row in rows} == set(SHAPES)
        and all(
            all(
                field in row
                for field in contract()["row_ledger"]["required_fields"]
            )
            for row in rows
        )
    )
    timing_positive = (
        primary["candidate_component"]["median_ms"]
        < primary["baseline_component"]["median_ms"]
    )
    passed = (
        ledger_complete
        and all(row["numerical"]["pass"] for row in rows)
        and timing_positive
        and graph_proof["pass"]
    )
    terminal = {
        "schema_version": 1,
        "classification": (
            "component_positive" if passed else "component_negative"
        ),
        "pass": passed,
        "ledger_complete": ledger_complete,
        "timing_positive_at_m32": timing_positive,
        "cuda_graph_proof": graph_proof,
        "rows": rows,
        "physical_prediction": {
            "standalone_launches_removed_per_layer_decode": 1,
            "bf16_intermediate_bytes_removed_per_m32_call": 688128,
            "unfused_launches": 3,
            "fused_launches": 2,
            "candidate_threads_per_cta": 672,
            "candidate_warps_per_cta": 21,
            "candidate_static_shared_memory_logical_bytes": 10876,
            "candidate_static_shared_memory_expected_aligned_bytes": 10880,
            "candidate_grid_ctas_m32": 32,
            "candidate_grid_waves_on_132_sms": 0.24242424242424243,
        },
    }
    atomic(args.output / "TERMINAL.json", terminal)
    return 0 if passed else 20


if __name__ == "__main__":
    raise SystemExit(main())
