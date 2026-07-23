#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import pathlib
import statistics
import time
from typing import Any, Callable


GATE_KEY = "model.language_model.layers.0.mlp.gate_proj.weight"
UP_KEY = "model.language_model.layers.0.mlp.up_proj.weight"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def percentile(samples: list[float], quantile: float) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def distribution(samples: list[float]) -> dict[str, Any]:
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "minimum_ms": min(samples),
        "p90_ms": percentile(samples, 0.9),
        "maximum_ms": max(samples),
        "coefficient_of_variation": statistics.pstdev(samples)
        / statistics.fmean(samples),
    }


def validate_binding(
    binding_path: pathlib.Path, input_root_override: pathlib.Path | None = None
) -> dict[str, Any]:
    binding = json.loads(binding_path.read_text())
    if binding.get("pass") is not True:
        raise RuntimeError("binding_not_admitted")
    input_root = input_root_override or pathlib.Path(binding["inputs"]["root"])
    if not input_root.is_absolute():
        raise RuntimeError("binding_input_root_not_absolute")
    for name, relative in binding["inputs"]["paths"].items():
        path = input_root / relative
        actual = sha256(path)
        expected = binding["inputs"]["sha256"][name]
        if actual != expected:
            raise RuntimeError(
                f"bound_input_identity_mismatch:{name}:{expected}:{actual}"
            )
    if binding["attention"]["query_rows"] != 2048:
        raise RuntimeError("attention_query_rows_changed")
    if binding["fp8_linear"]["shape_mkn"] != [2048, 5376, 43008]:
        raise RuntimeError("fp8_shape_changed")
    binding["_resolved_input_root"] = str(input_root)
    return binding


def timed(
    torch: Any,
    timer_stream: Any,
    worker_streams: list[Any],
    function: Callable[[], tuple[Any, ...]],
) -> tuple[float, tuple[Any, ...]]:
    start = torch.cuda.Event(enable_timing=True)
    stop = torch.cuda.Event(enable_timing=True)
    done = [torch.cuda.Event() for _ in worker_streams]
    start.record(timer_stream)
    for stream in worker_streams:
        stream.wait_event(start)
    outputs = function()
    for stream, event in zip(worker_streams, done):
        event.record(stream)
        timer_stream.wait_event(event)
    stop.record(timer_stream)
    stop.synchronize()
    return float(start.elapsed_time(stop)), outputs


def numerical(torch: Any, reference: Any, candidate: Any) -> dict[str, Any]:
    difference = candidate.float() - reference.float()
    reference_float = reference.float()
    return {
        "bitwise_equal": bool(torch.equal(reference, candidate)),
        "all_finite": bool(torch.isfinite(candidate).all().item()),
        "relative_l2": float(
            torch.linalg.vector_norm(difference)
            / torch.linalg.vector_norm(reference_float).clamp_min(1e-12)
        ),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                candidate.float().flatten(),
                reference_float.flatten(),
                dim=0,
            )
        ),
        "max_abs_error": float(difference.abs().max()),
        "shape": list(candidate.shape),
        "complete_output_elements_consumed": candidate.numel(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=pathlib.Path, required=True)
    parser.add_argument("--input-root", type=pathlib.Path)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=21)
    parser.add_argument("--seed", type=int, default=20260724)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    binding = validate_binding(args.binding, args.input_root)
    if args.validate_only:
        result = {
            "schema_version": 1,
            "pass": True,
            "classification": "offline_binding_and_harness_validation_pass",
            "binding_sha256": sha256(args.binding),
            "gpu_science_started": False,
        }
        if args.artifact_root:
            atomic_json(args.artifact_root / "OFFLINE_VALIDATION.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.artifact_root is None:
        raise RuntimeError("artifact_root_required_for_gpu_execution")
    if args.iterations < 7:
        raise RuntimeError("iterations_must_be_at_least_7")

    import torch
    from safetensors import safe_open
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    attention_module = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    backend_module = importlib.import_module(
        "sglang.srt.layers.attention.triton_backend"
    )
    fp8_module = importlib.import_module(
        "sglang.srt.layers.quantization.fp8_utils"
    )
    installed = {
        "extend_attention.py": sha256(
            pathlib.Path(attention_module.__file__).resolve()
        ),
        "triton_backend.py": sha256(
            pathlib.Path(backend_module.__file__).resolve()
        ),
        "fp8_utils.py": sha256(pathlib.Path(fp8_module.__file__).resolve()),
    }
    for name, actual in installed.items():
        expected = binding["inputs"]["sha256"][name]
        if actual != expected:
            raise RuntimeError(
                f"installed_source_identity_mismatch:{name}:{expected}:{actual}"
            )
    if (
        not torch.cuda.is_available()
        or tuple(torch.cuda.get_device_capability()) != (9, 0)
        or "H200" not in torch.cuda.get_device_name()
    ):
        raise RuntimeError("exact_h200_sm90_required")

    args.artifact_root.mkdir(parents=True, exist_ok=False)
    invocation_path = args.artifact_root / "INVOCATION_STATE.json"
    invocation = {
        "schema_version": 1,
        "binding_sha256": sha256(args.binding),
        "candidate_cuda_started": False,
        "scientific_invocation_started": False,
        "scientific_terminal_recorded": False,
        "updated_unix_s": time.time(),
    }
    atomic_json(invocation_path, invocation)

    input_root = pathlib.Path(binding["_resolved_input_root"])
    weights_path = input_root / binding["inputs"]["paths"]["weights"]
    with safe_open(str(weights_path), framework="pt", device="cpu") as handle:
        gate = handle.get_tensor(GATE_KEY)
        up = handle.get_tensor(UP_KEY)
    packed_bf16 = torch.cat((gate, up), dim=0).cuda().t()
    weight_scale = (
        packed_bf16.float().abs().amax(dim=0) / 448.0
    ).clamp_min(1e-8).float()
    weight = (packed_bf16 / weight_scale).to(torch.float8_e4m3fn)
    weight_scale = weight_scale.unsqueeze(0)
    del gate, up, packed_bf16
    if weight.shape != (5376, 43008) or weight.stride() != (1, 5376):
        raise RuntimeError(
            f"production_weight_layout_mismatch:{weight.shape}:{weight.stride()}"
        )

    generator = torch.Generator(device="cuda")
    generator.manual_seed(args.seed)
    rows = binding["attention"]["query_rows"]
    q = (
        torch.randn(
            (rows, 32, 256),
            generator=generator,
            device="cuda",
            dtype=torch.bfloat16,
        )
        / math.sqrt(256)
    )
    k = (
        torch.randn(
            (rows, 16, 256),
            generator=generator,
            device="cuda",
            dtype=torch.bfloat16,
        )
        / math.sqrt(256)
    )
    v = torch.randn(
        (rows, 16, 256),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    )
    cache_rows = 1024
    k_cache = torch.randn(
        (cache_rows, 16, 256),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    ).to(torch.float8_e5m2)
    v_cache = torch.randn(
        (cache_rows, 16, 256),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    ).to(torch.float8_e5m2)
    qo_indptr = torch.tensor([0, rows], device="cuda", dtype=torch.int32)
    kv_indptr = torch.tensor([0, cache_rows], device="cuda", dtype=torch.int32)
    kv_indices = torch.arange(cache_rows, device="cuda", dtype=torch.int64)
    linear_bf16 = torch.randn(
        (rows, 5376),
        generator=generator,
        device="cuda",
        dtype=torch.bfloat16,
    )
    linear_input, linear_scale = sglang_per_token_quant_fp8(linear_bf16)
    if (
        linear_input.shape != (2048, 5376)
        or linear_scale.shape != (2048, 1)
    ):
        raise RuntimeError(
            f"production_activation_layout_mismatch:{linear_input.shape}:{linear_scale.shape}"
        )
    del linear_bf16

    serial_attention_output = torch.empty_like(q)
    concurrent_attention_output = torch.empty_like(q)
    timer_stream = torch.cuda.current_stream()
    serial_stream = torch.cuda.Stream()
    attention_stream = torch.cuda.Stream()
    linear_stream = torch.cuda.Stream()

    def attention(output: Any) -> Any:
        attention_module.extend_attention_fwd(
            q,
            k,
            v,
            output,
            k_cache,
            v_cache,
            qo_indptr,
            kv_indptr,
            kv_indices,
            None,
            True,
            None,
            rows,
            1.0,
            1.0,
            sliding_window_size=1024,
        )
        return output

    def linear() -> Any:
        return fp8_scaled_mm(
            linear_input,
            weight,
            linear_scale,
            weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )

    invocation["candidate_cuda_started"] = True
    invocation["updated_unix_s"] = time.time()
    atomic_json(invocation_path, invocation)
    with torch.cuda.stream(serial_stream):
        attention(serial_attention_output)
        serial_linear_output = linear()
    torch.cuda.synchronize()
    for _ in range(args.warmups):
        with torch.cuda.stream(serial_stream):
            attention(serial_attention_output)
            serial_linear_output = linear()
        with torch.cuda.stream(attention_stream):
            attention(concurrent_attention_output)
        with torch.cuda.stream(linear_stream):
            concurrent_linear_output = linear()
        torch.cuda.synchronize()

    invocation["scientific_invocation_started"] = True
    invocation["updated_unix_s"] = time.time()
    atomic_json(invocation_path, invocation)
    attention_samples: list[float] = []
    linear_samples: list[float] = []
    serial_samples: list[float] = []
    concurrent_samples: list[float] = []
    concurrent_linear_output = None
    for index in range(args.iterations):
        modes = (
            ("attention", "linear", "serial", "concurrent")
            if index % 2 == 0
            else ("concurrent", "serial", "linear", "attention")
        )
        for mode in modes:
            if mode == "attention":
                def run_attention() -> tuple[Any, ...]:
                    with torch.cuda.stream(serial_stream):
                        return (attention(serial_attention_output),)

                elapsed, _ = timed(
                    torch,
                    timer_stream,
                    [serial_stream],
                    run_attention,
                )
                attention_samples.append(elapsed)
            elif mode == "linear":
                def run_linear() -> tuple[Any, ...]:
                    with torch.cuda.stream(serial_stream):
                        return (linear(),)

                elapsed, outputs = timed(
                    torch, timer_stream, [serial_stream], run_linear
                )
                serial_linear_output = outputs[0]
                linear_samples.append(elapsed)
            elif mode == "serial":
                def run_serial() -> tuple[Any, ...]:
                    with torch.cuda.stream(serial_stream):
                        return attention(serial_attention_output), linear()

                elapsed, outputs = timed(
                    torch, timer_stream, [serial_stream], run_serial
                )
                serial_linear_output = outputs[1]
                serial_samples.append(elapsed)
            else:
                def run_concurrent() -> tuple[Any, ...]:
                    with torch.cuda.stream(attention_stream):
                        attention(concurrent_attention_output)
                    with torch.cuda.stream(linear_stream):
                        concurrent_output = linear()
                    return concurrent_attention_output, concurrent_output

                elapsed, outputs = timed(
                    torch,
                    timer_stream,
                    [attention_stream, linear_stream],
                    run_concurrent,
                )
                concurrent_linear_output = outputs[1]
                concurrent_samples.append(elapsed)

    torch.cuda.synchronize()
    if concurrent_linear_output is None:
        raise RuntimeError("concurrent_output_missing")
    attention_numerical = numerical(
        torch, serial_attention_output, concurrent_attention_output
    )
    fp8_numerical = numerical(
        torch, serial_linear_output, concurrent_linear_output
    )
    numerical_pass = (
        attention_numerical["bitwise_equal"]
        and attention_numerical["all_finite"]
        and fp8_numerical["bitwise_equal"]
        and fp8_numerical["all_finite"]
    )
    attention_result = distribution(attention_samples)
    linear_result = distribution(linear_samples)
    serial_result = distribution(serial_samples)
    concurrent_result = distribution(concurrent_samples)
    component_sum = (
        attention_result["median_ms"] + linear_result["median_ms"]
    )
    concurrent_ratio = concurrent_result["median_ms"] / component_sum
    serial_pair_ratio = (
        concurrent_result["median_ms"] / serial_result["median_ms"]
    )
    possible_overlap = min(
        attention_result["median_ms"], linear_result["median_ms"]
    )
    overlap_efficiency = (
        component_sum - concurrent_result["median_ms"]
    ) / possible_overlap
    if not numerical_pass:
        classification = "numerical_reject"
    elif concurrent_ratio <= binding["decision_contract"][
        "promote_concurrent_ratio_lte"
    ]:
        classification = "component_promote_runtime_slice"
    elif concurrent_ratio >= binding["decision_contract"][
        "close_pair_concurrent_ratio_gte"
    ]:
        classification = "component_close_pair_destructive_interference"
    else:
        classification = "component_ambiguous_overlap"
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": classification,
        "pass": numerical_pass,
        "binding_sha256": sha256(args.binding),
        "candidate_path_proof": {
            "attention_consumer": binding["attention"]["consumer_symbol"],
            "attention_kernel": binding["attention"]["kernel_symbol"],
            "fp8_consumer": binding["fp8_linear"]["consumer_symbol"],
            "installed_source_sha256": installed,
            "serial_stream": serial_stream.cuda_stream,
            "attention_stream": attention_stream.cuda_stream,
            "linear_stream": linear_stream.cuda_stream,
            "disjoint_streams": len(
                {
                    serial_stream.cuda_stream,
                    attention_stream.cuda_stream,
                    linear_stream.cuda_stream,
                }
            )
            == 3,
        },
        "timings": {
            "attention": attention_result,
            "fp8_linear": linear_result,
            "serial_pair": serial_result,
            "concurrent_pair": concurrent_result,
            "component_median_sum_ms": component_sum,
            "concurrent_to_component_sum_ratio": concurrent_ratio,
            "concurrent_to_measured_serial_pair_ratio": serial_pair_ratio,
            "overlap_efficiency": overlap_efficiency,
        },
        "numerical": {
            "attention": attention_numerical,
            "fp8_linear": fp8_numerical,
            "complete_outputs_consumed": True,
        },
        "identity": {
            "seed": args.seed,
            "torch": torch.__version__,
            "triton": importlib.import_module("triton").__version__,
            "device_name": torch.cuda.get_device_name(),
            "device_capability": list(torch.cuda.get_device_capability()),
            "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
        },
    }
    atomic_json(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    invocation["scientific_terminal_recorded"] = True
    invocation["updated_unix_s"] = time.time()
    atomic_json(invocation_path, invocation)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if numerical_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
