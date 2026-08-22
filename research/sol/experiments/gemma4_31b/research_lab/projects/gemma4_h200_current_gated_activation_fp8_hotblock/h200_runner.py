#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics


INTERMEDIATE = 21504
HIDDEN = 5376
GATE_UP = 2 * INTERMEDIATE
PRIMARY_ROWS = 32
SHAPES = (1, 16, 32)
DOWN_KEY = "model.language_model.layers.0.mlp.down_proj.weight"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def contract() -> dict[str, object]:
    return {
        "schema_version": 1,
        "model": (
            "google/gemma-4-31B-it@"
            "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
        ),
        "checkpoint_manifest_sha256": (
            "6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6"
        ),
        "runtime_image": (
            "docker.io/lmsysorg/sglang@sha256:"
            "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
        ),
        "runtime": "sglang v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        "hardware": "NVIDIA H200 SXM / sm_90a",
        "producer_control": (
            "GeluAndMul(approximate='tanh') + "
            "sglang_per_token_quant_fp8"
        ),
        "producer_candidate": "gemma4_gated_activation_quant_e4m3_kernel",
        "consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
        "real_weight_key": DOWN_KEY,
        "component_input": {
            "placement": "project-local immutable safetensors",
            "only_tensor": DOWN_KEY,
            "raw_shape": [HIDDEN, INTERMEDIATE],
            "raw_dtype": "bfloat16",
            "manifest_required_fields": [
                "component_sha256",
                "checkpoint_manifest_sha256",
                "tensor_key",
            ],
        },
        "geometry": {
            "gate_up": [PRIMARY_ROWS, GATE_UP],
            "gate_up_dtype": "bfloat16",
            "gate_up_stride": [GATE_UP, 1],
            "activated": [PRIMARY_ROWS, INTERMEDIATE],
            "down_weight_k_n": [INTERMEDIATE, HIDDEN],
            "activation_dtype": "float8_e4m3fn",
            "activation_scale": [PRIMARY_ROWS, 1],
            "activation_scale_dtype": "float32",
            "output": [PRIMARY_ROWS, HIDDEN],
            "output_dtype": "bfloat16",
        },
        "row_ledger": {
            "shapes": list(SHAPES),
            "expected_rows": len(SHAPES),
            "required_fields": [
                "baseline_producer",
                "candidate_producer",
                "baseline_component",
                "candidate_component",
                "numerical",
                "candidate_path",
            ],
        },
        "cuda_graph": {
            "required_shape": [PRIMARY_ROWS, GATE_UP],
            "arms": ["baseline_component", "candidate_component"],
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


def load_manifest(
    component: pathlib.Path, manifest_path: pathlib.Path
) -> dict[str, object]:
    component = component.resolve()
    manifest_path = manifest_path.resolve()
    if not component.is_relative_to(PROJECT_ROOT):
        raise RuntimeError("component safetensors must be project-local")
    if not manifest_path.is_relative_to(PROJECT_ROOT):
        raise RuntimeError("component manifest must be project-local")
    manifest = json.loads(manifest_path.read_text())
    expected = manifest.get("component_sha256")
    observed = sha256(component)
    if expected != observed:
        raise RuntimeError(
            f"component SHA-256 mismatch: expected {expected}, got {observed}"
        )
    if manifest.get("checkpoint_manifest_sha256") != contract()[
        "checkpoint_manifest_sha256"
    ]:
        raise RuntimeError("checkpoint manifest identity mismatch")
    if manifest.get("tensor_key") != DOWN_KEY:
        raise RuntimeError("component tensor key mismatch")
    return {
        **manifest,
        "component_path": str(component),
        "component_sha256_observed": observed,
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
    }


def numerical(torch, control, candidate, control_output, candidate_output):
    control_q, control_scale = control
    candidate_q, candidate_scale = candidate
    control_dequantized = control_q.float() * control_scale
    candidate_dequantized = candidate_q.float() * candidate_scale
    activation_difference = candidate_dequantized - control_dequantized
    output_difference = candidate_output.float() - control_output.float()
    activation_relative_l2 = (
        torch.linalg.vector_norm(activation_difference)
        / torch.linalg.vector_norm(control_dequantized).clamp_min(1e-12)
    ).item()
    output_relative_l2 = (
        torch.linalg.vector_norm(output_difference)
        / torch.linalg.vector_norm(control_output.float()).clamp_min(1e-12)
    ).item()
    cosine = torch.nn.functional.cosine_similarity(
        control_output.float().flatten(),
        candidate_output.float().flatten(),
        dim=0,
    ).item()
    result = {
        "activation_dequantized_relative_l2_error": activation_relative_l2,
        "consumer_relative_l2_error": output_relative_l2,
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
        "complete_output_elements_consumed": int(candidate_output.numel()),
    }
    result["pass"] = (
        activation_relative_l2 <= 0.001
        and output_relative_l2 <= 0.001
        and cosine >= 0.999999
        and result["candidate_nonfinite_count"] == 0
    )
    return result


def capture_graph(torch, function):
    function()
    torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        captured = function()
    graph.replay()
    torch.cuda.synchronize()
    replay = captured.clone()
    direct = function()
    torch.cuda.synchronize()
    difference = replay.float() - direct.float()
    relative_l2 = (
        torch.linalg.vector_norm(difference)
        / torch.linalg.vector_norm(direct.float()).clamp_min(1e-12)
    ).item()
    return {
        "captured": True,
        "replay_output_elements_consumed": int(replay.numel()),
        "replay_vs_direct_relative_l2_error": relative_l2,
        "pass": relative_l2 == 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--component-safetensors", type=pathlib.Path)
    parser.add_argument("--component-manifest", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--repetitions", type=int, default=100)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(contract(), indent=2, sort_keys=True))
        return 0
    if (
        args.component_safetensors is None
        or args.component_manifest is None
        or args.output is None
    ):
        parser.error(
            "--component-safetensors, --component-manifest, and --output "
            "are required"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    atomic(args.output / "CONTRACT.json", contract())
    state = {
        "schema_version": 1,
        "identity_validated": False,
        "weight_producer_completed": False,
        "science_started": False,
        "baseline_first_call_completed": False,
        "candidate_first_call_completed": False,
        "rows_completed": 0,
    }
    atomic(args.output / "INVOCATION_STATE.json", state)

    import torch
    from safetensors import safe_open

    from gated_activation_fp8_decode import (
        gemma4_gated_activation_quant_e4m3,
        invocation_count,
        prepare,
    )
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import (
        per_token_group_quant_fp8,
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

    manifest = load_manifest(
        args.component_safetensors, args.component_manifest
    )
    with safe_open(
        str(args.component_safetensors), framework="pt", device="cpu"
    ) as handle:
        if set(handle.keys()) != {DOWN_KEY}:
            raise RuntimeError(
                f"component must contain only {DOWN_KEY}, got {handle.keys()}"
            )
        raw_weight = handle.get_tensor(DOWN_KEY)
    if raw_weight.shape != (HIDDEN, INTERMEDIATE):
        raise RuntimeError(f"unexpected raw down weight {raw_weight.shape}")
    if raw_weight.dtype != torch.bfloat16:
        raise RuntimeError(f"unexpected raw down dtype {raw_weight.dtype}")
    identity = contract()
    identity["loaded_component"] = manifest
    identity["raw_weight_shape"] = list(raw_weight.shape)
    identity["raw_weight_stride"] = list(raw_weight.stride())
    atomic(args.output / "IDENTITY.json", identity)
    state["identity_validated"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)

    raw_weight = raw_weight.cuda().contiguous()
    quantized_weight_n_k, weight_scale_n_1 = per_token_group_quant_fp8(
        raw_weight, group_size=INTERMEDIATE
    )
    weight = quantized_weight_n_k.t()
    weight_scale = weight_scale_n_1.t().contiguous().flatten()
    if weight.shape != (INTERMEDIATE, HIDDEN):
        raise RuntimeError(f"unexpected consumer weight shape {weight.shape}")
    if weight.stride() != (1, INTERMEDIATE):
        raise RuntimeError(f"weight is not column-major: {weight.stride()}")
    if weight_scale.shape != (HIDDEN,):
        raise RuntimeError(f"unexpected weight scale {weight_scale.shape}")
    state["weight_producer_completed"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)

    prepare()
    activation = GeluAndMul(approximate="tanh")
    generator = torch.Generator(device="cuda")
    generator.manual_seed(20260729)

    def baseline_producer(gate_up):
        return sglang_per_token_quant_fp8(activation(gate_up))

    def candidate_producer(gate_up):
        return gemma4_gated_activation_quant_e4m3(gate_up)

    def consume(gate_up, producer):
        quantized, scales = producer(gate_up)
        return fp8_scaled_mm(
            quantized,
            weight,
            scales,
            weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )

    smoke = torch.randn(
        (1, GATE_UP),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    )
    state["science_started"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)
    consume(smoke, baseline_producer)
    torch.cuda.synchronize()
    state["baseline_first_call_completed"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)
    consume(smoke, candidate_producer)
    torch.cuda.synchronize()
    state["candidate_first_call_completed"] = True
    atomic(args.output / "INVOCATION_STATE.json", state)

    graph_input = torch.randn(
        (PRIMARY_ROWS, GATE_UP),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    )
    graph_proof = {
        "shape": list(graph_input.shape),
        "baseline_component": capture_graph(
            torch, lambda: consume(graph_input, baseline_producer)
        ),
        "candidate_component": capture_graph(
            torch, lambda: consume(graph_input, candidate_producer)
        ),
    }
    graph_proof["pass"] = all(
        graph_proof[arm]["pass"]
        for arm in ("baseline_component", "candidate_component")
    )
    atomic(args.output / "CUDA_GRAPH_PROOF.json", graph_proof)

    rows = []
    for tokens in SHAPES:
        gate_up = torch.randn(
            (tokens, GATE_UP),
            generator=generator,
            device="cuda",
            dtype=torch.bfloat16,
        )
        control = baseline_producer(gate_up)
        candidate = candidate_producer(gate_up)
        control_output = consume(gate_up, baseline_producer)
        candidate_output = consume(gate_up, candidate_producer)
        torch.cuda.synchronize()
        row_numerical = numerical(
            torch,
            control,
            candidate,
            control_output,
            candidate_output,
        )
        _, baseline_producer_samples = timed(
            torch,
            lambda: baseline_producer(gate_up),
            args.repetitions,
        )
        _, candidate_producer_samples = timed(
            torch,
            lambda: candidate_producer(gate_up),
            args.repetitions,
        )
        _, baseline_component_samples = timed(
            torch,
            lambda: consume(gate_up, baseline_producer),
            args.repetitions,
        )
        _, candidate_component_samples = timed(
            torch,
            lambda: consume(gate_up, candidate_producer),
            args.repetitions,
        )
        row = {
            "tokens": tokens,
            "baseline_producer": summarize(baseline_producer_samples),
            "candidate_producer": summarize(candidate_producer_samples),
            "baseline_component": summarize(baseline_component_samples),
            "candidate_component": summarize(candidate_component_samples),
            "numerical": row_numerical,
            "candidate_path": {
                "symbol": "gemma4_gated_activation_quant_e4m3_kernel",
                "invocation_count": invocation_count(),
                "gate_up_shape": list(gate_up.shape),
                "gate_up_stride": list(gate_up.stride()),
                "weight_shape": list(weight.shape),
                "weight_stride": list(weight.stride()),
            },
        }
        row["component_reduction_fraction"] = 1.0 - (
            row["candidate_component"]["median_ms"]
            / row["baseline_component"]["median_ms"]
        )
        row["timing_positive"] = (
            row["candidate_component"]["median_ms"]
            < row["baseline_component"]["median_ms"]
        )
        rows.append(row)
        atomic(args.output / f"ROW_M{tokens}.json", row)
        state["rows_completed"] = len(rows)
        atomic(args.output / "INVOCATION_STATE.json", state)

    primary = next(row for row in rows if row["tokens"] == PRIMARY_ROWS)
    ledger_complete = (
        len(rows) == len(SHAPES)
        and graph_proof["pass"]
        and all(row["candidate_path"]["invocation_count"] > 0 for row in rows)
    )
    numerical_pass = ledger_complete and all(
        row["numerical"]["pass"] for row in rows
    )
    positive = numerical_pass and primary["timing_positive"]
    if positive:
        classification = "component_positive"
    elif not ledger_complete:
        classification = "invalid_incomplete"
    elif not numerical_pass:
        classification = "component_negative_numerical_equivalence"
    else:
        classification = "component_negative_timing"
    terminal = {
        "schema_version": 1,
        "classification": classification,
        "identity": identity,
        "device": {
            "name": properties.name,
            "major": properties.major,
            "minor": properties.minor,
            "sm_count": properties.multi_processor_count,
        },
        "rows": rows,
        "row_ledger_complete": ledger_complete,
        "numerical_pass": numerical_pass,
        "cuda_graph": graph_proof,
        "primary_m32_component_positive": primary["timing_positive"],
        "candidate_invocations": invocation_count(),
        "science_consumed": True,
        "pass": positive,
    }
    atomic(args.output / "TERMINAL.json", terminal)
    return 0 if positive else 20


if __name__ == "__main__":
    raise SystemExit(main())
