#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import pathlib
import statistics
import time


MS = (1, 2, 4, 8, 12, 16, 24, 32)
HIDDEN = 5376
INTERMEDIATE = 21504
GATE_UP = 43008
LAYERS = 60
DECODE_STEPS = 357
CONTROL_REQUEST_SECONDS = 0.6746877474374742


def atomic(path: pathlib.Path, value: object) -> None:
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


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    return {
        "raw_ms": values,
        "p50_ms": statistics.median(values),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "minimum_ms": min(values),
        "maximum_ms": max(values),
    }


def timed(torch, fn, warmups: int = 5, iterations: int = 30):
    output = None
    for _ in range(warmups):
        output = fn()
    torch.cuda.synchronize()
    cuda_ms = []
    wall_ms = []
    for _ in range(iterations):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        wall_start = time.perf_counter()
        output = fn()
        end.record()
        end.synchronize()
        cuda_ms.append(float(start.elapsed_time(end)))
        wall_ms.append((time.perf_counter() - wall_start) * 1000)
    return {
        "warmups": warmups,
        "iterations": iterations,
        "cuda_event": distribution(cuda_ms),
        "synchronized_wall": distribution(wall_ms),
    }, output


def error_metrics(torch, actual, reference) -> dict[str, object]:
    actual32 = actual.float()
    reference32 = reference.float()
    delta = actual32 - reference32
    reference_norm = torch.linalg.vector_norm(reference32).clamp_min(1e-12)
    return {
        "maximum_absolute": float(delta.abs().max()),
        "relative_l2": float(torch.linalg.vector_norm(delta) / reference_norm),
        "cosine_similarity": float(
            torch.nn.functional.cosine_similarity(
                actual32.flatten(), reference32.flatten(), dim=0
            )
        ),
        "nonfinite_count": int((~torch.isfinite(actual32)).sum()),
        "nontrivial": bool(float(actual32.abs().max()) > 1e-6),
    }


def locate_tensor(safe_open, root: pathlib.Path, index: dict, key: str):
    shard = root / index["weight_map"][key]
    with safe_open(str(shard), framework="pt", device="cpu") as handle:
        return handle.get_tensor(key)


def make_awq_layer(torch, qweight, qzeros, scales, input_size: int, output_size: int):
    from sglang.srt.layers.quantization.awq import AWQMarlinConfig
    from sglang.srt.layers.quantization.awq.awq import AWQLinearMethod
    from sglang.srt.layers.quantization.awq.schemes.awq_marlin import (
        AWQMarlinLinearScheme,
    )

    config_dict = {
        "quant_method": "awq",
        "bits": 4,
        "group_size": 128,
        "zero_point": True,
        "version": "gemm",
    }
    config = AWQMarlinConfig(4, 128, True, False, [], config_dict)
    method = AWQLinearMethod(config)
    layer = torch.nn.Module()
    layer.scheme = AWQMarlinLinearScheme(config)
    with torch.device("cuda"):
        method.create_weights(
            layer,
            input_size,
            [output_size],
            input_size,
            output_size,
            torch.bfloat16,
        )
    layer.qweight.data.copy_(qweight.cuda())
    layer.qzeros.data.copy_(qzeros.cuda())
    layer.scales.data.copy_(scales.cuda())
    method.process_weights_after_loading(layer)
    return method, layer


def fp8_weight(torch, raw):
    weight_bf16 = raw.cuda().t()
    scale = (
        weight_bf16.float().abs().amax(dim=0).div(448.0).clamp_min(1e-8).float()
    )
    weight = (weight_bf16 / scale).to(torch.float8_e4m3fn)
    return weight, scale


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--current-checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--w4-component", type=pathlib.Path, required=True)
    parser.add_argument(
        "--counter-probe", choices=("candidate", "control"), default=None
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    state_path = args.output / "INVOCATION_STATE.json"
    state = {
        "schema_version": 1,
        "candidate_cuda_started": False,
        "candidate_science_started": False,
        "control_cuda_started": False,
        "control_science_started": False,
    }
    atomic(state_path, state)
    terminal: dict[str, object] = {
        "schema_version": 1,
        "classification": "component_integration_failure",
        "pass": False,
    }
    try:
        import torch
        from safetensors import safe_open
        from sglang.srt.hardware_backend.gpu.quantization import awq_kernels
        from sglang.srt.layers.activation import GeluAndMul
        from sglang.srt.layers.quantization import fp8_utils
        from sglang.srt.layers.quantization.fp8_kernel import (
            sglang_per_token_quant_fp8,
        )

        if not torch.cuda.is_available() or "H200" not in torch.cuda.get_device_name():
            raise RuntimeError("exact_nvidia_h200_required")
        if sha256(args.w4_component) == "":
            raise RuntimeError("unreachable_component_identity")

        current_index = json.loads(
            (args.current_checkpoint / "model.safetensors.index.json").read_text()
        )
        prefix = "model.language_model.layers.0.mlp"
        gate_raw = locate_tensor(
            safe_open, args.current_checkpoint, current_index, f"{prefix}.gate_proj.weight"
        )
        up_raw = locate_tensor(
            safe_open, args.current_checkpoint, current_index, f"{prefix}.up_proj.weight"
        )
        down_raw = locate_tensor(
            safe_open, args.current_checkpoint, current_index, f"{prefix}.down_proj.weight"
        )
        if tuple(gate_raw.shape) != (INTERMEDIATE, HIDDEN):
            raise RuntimeError(f"gate_shape_mismatch:{tuple(gate_raw.shape)}")
        if tuple(up_raw.shape) != (INTERMEDIATE, HIDDEN):
            raise RuntimeError(f"up_shape_mismatch:{tuple(up_raw.shape)}")
        if tuple(down_raw.shape) != (HIDDEN, INTERMEDIATE):
            raise RuntimeError(f"down_shape_mismatch:{tuple(down_raw.shape)}")

        gate_up_fp8, gate_up_fp8_scale = fp8_weight(
            torch, torch.cat((gate_raw, up_raw), dim=0)
        )
        down_fp8, down_fp8_scale = fp8_weight(torch, down_raw)
        del gate_raw, up_raw, down_raw

        with safe_open(str(args.w4_component), framework="pt", device="cpu") as handle:
            gate_qweight = handle.get_tensor(f"{prefix}.gate_proj.qweight")
            gate_qzeros = handle.get_tensor(f"{prefix}.gate_proj.qzeros")
            gate_scales = handle.get_tensor(f"{prefix}.gate_proj.scales")
            up_qweight = handle.get_tensor(f"{prefix}.up_proj.qweight")
            up_qzeros = handle.get_tensor(f"{prefix}.up_proj.qzeros")
            up_scales = handle.get_tensor(f"{prefix}.up_proj.scales")
            down_qweight = handle.get_tensor(f"{prefix}.down_proj.qweight")
            down_qzeros = handle.get_tensor(f"{prefix}.down_proj.qzeros")
            down_scales = handle.get_tensor(f"{prefix}.down_proj.scales")

        gate_up_qweight = torch.cat((gate_qweight, up_qweight), dim=1)
        gate_up_qzeros = torch.cat((gate_qzeros, up_qzeros), dim=1)
        gate_up_scales = torch.cat((gate_scales, up_scales), dim=1)
        dequantize = awq_kernels.awq_dequantize
        gate_up_reference_weight = dequantize(
            gate_up_qweight.cuda(), gate_up_scales.cuda(), gate_up_qzeros.cuda()
        )
        down_reference_weight = dequantize(
            down_qweight.cuda(), down_scales.cuda(), down_qzeros.cuda()
        )
        gate_up_method, gate_up_layer = make_awq_layer(
            torch,
            gate_up_qweight,
            gate_up_qzeros,
            gate_up_scales,
            HIDDEN,
            GATE_UP,
        )
        down_method, down_layer = make_awq_layer(
            torch,
            down_qweight,
            down_qzeros,
            down_scales,
            INTERMEDIATE,
            HIDDEN,
        )
        del (
            gate_qweight,
            gate_qzeros,
            gate_scales,
            up_qweight,
            up_qzeros,
            up_scales,
            down_qweight,
            down_qzeros,
            down_scales,
            gate_up_qweight,
            gate_up_qzeros,
            gate_up_scales,
        )
        activation = GeluAndMul(approximate="tanh")

        def candidate_chain(x):
            torch.cuda.nvtx.range_push("hybrid_w4_mlp_candidate")
            gate_up = gate_up_method.apply(gate_up_layer, x)
            activated = activation(gate_up)
            output = down_method.apply(down_layer, activated)
            torch.cuda.nvtx.range_pop()
            return output

        def reference_chain(x):
            return torch.mm(
                activation(torch.mm(x, gate_up_reference_weight)),
                down_reference_weight,
            )

        def control_chain(x):
            torch.cuda.nvtx.range_push("current_fp8_mlp_control")
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
            aq, ass = sglang_per_token_quant_fp8(activated)
            output = fp8_utils.fp8_scaled_mm(
                aq,
                down_fp8,
                ass,
                down_fp8_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )
            torch.cuda.nvtx.range_pop()
            return output

        if args.counter_probe is not None:
            torch.manual_seed(20260755)
            probe = torch.randn((32, HIDDEN), device="cuda", dtype=torch.bfloat16)
            torch.cuda.synchronize()
            state[f"{args.counter_probe}_cuda_started"] = True
            state[f"{args.counter_probe}_science_started"] = True
            atomic(state_path, state)
            torch.cuda.cudart().cudaProfilerStart()
            output = (
                candidate_chain(probe)
                if args.counter_probe == "candidate"
                else control_chain(probe)
            )
            torch.cuda.synchronize()
            torch.cuda.cudart().cudaProfilerStop()
            counter_terminal = {
                "schema_version": 1,
                "classification": "counter_probe_complete",
                "arm": args.counter_probe,
                "m": 32,
                "finite": bool(torch.isfinite(output).all()),
                "nontrivial": bool(float(output.float().abs().max()) > 1e-6),
            }
            atomic(args.output / "TERMINAL.json", counter_terminal)
            return 0 if counter_terminal["finite"] and counter_terminal["nontrivial"] else 20

        state["candidate_cuda_started"] = True
        atomic(state_path, state)
        torch.manual_seed(20260723)
        tiny = torch.randn((1, HIDDEN), device="cuda", dtype=torch.bfloat16)
        tiny_candidate = candidate_chain(tiny)
        tiny_reference = reference_chain(tiny)
        torch.cuda.synchronize()
        tiny_metrics = error_metrics(torch, tiny_candidate, tiny_reference)
        state["candidate_science_started"] = True
        atomic(state_path, state)

        rows = []
        state["control_cuda_started"] = True
        state["control_science_started"] = True
        atomic(state_path, state)
        for m in MS:
            torch.manual_seed(20260723 + m)
            x = torch.randn((m, HIDDEN), device="cuda", dtype=torch.bfloat16)
            candidate_timing, candidate = timed(torch, lambda: candidate_chain(x))
            control_timing, control = timed(torch, lambda: control_chain(x))
            reference = reference_chain(x)
            candidate_error = error_metrics(torch, candidate, reference)
            representation_error = error_metrics(torch, reference, control)
            correctness_pass = bool(
                candidate_error["nonfinite_count"] == 0
                and candidate_error["nontrivial"]
                and candidate_error["relative_l2"] <= 0.03
                and candidate_error["cosine_similarity"] >= 0.999
            )
            row = {
                "m": m,
                "candidate_timing": candidate_timing,
                "control_timing": control_timing,
                "candidate_vs_dequantized_w4": candidate_error,
                "dequantized_w4_vs_current_fp8": representation_error,
                "correctness_pass": correctness_pass,
                "speedup": float(control_timing["cuda_event"]["p50_ms"])
                / float(candidate_timing["cuda_event"]["p50_ms"]),
            }
            rows.append(row)
            atomic(args.output / f"ROW_M{m}.json", row)
            del x, candidate, control, reference

        m32 = next(row for row in rows if row["m"] == 32)
        control_layer_ms = float(m32["control_timing"]["cuda_event"]["p50_ms"])
        candidate_layer_ms = float(m32["candidate_timing"]["cuda_event"]["p50_ms"])
        saved_request_seconds = (
            (control_layer_ms - candidate_layer_ms)
            / 1000
            * LAYERS
            * DECODE_STEPS
            / 32
        )
        bound = saved_request_seconds / CONTROL_REQUEST_SECONDS
        source_identity = {
            "awq_config": hashlib.sha256(
                inspect.getsource(
                    __import__(
                        "sglang.srt.layers.quantization.awq.awq",
                        fromlist=["AWQMarlinConfig"],
                    ).AWQMarlinConfig
                ).encode()
            ).hexdigest(),
            "awq_kernel": hashlib.sha256(
                inspect.getsource(awq_kernels.AWQMarlinLinearKernel).encode()
            ).hexdigest(),
            "fp8_scaled_mm": hashlib.sha256(
                inspect.getsource(fp8_utils.fp8_scaled_mm).encode()
            ).hexdigest(),
        }
        correctness_pass = bool(
            tiny_metrics["nonfinite_count"] == 0
            and tiny_metrics["relative_l2"] <= 0.03
            and tiny_metrics["cosine_similarity"] >= 0.999
            and all(row["correctness_pass"] for row in rows)
        )
        terminal = {
            "schema_version": 1,
            "classification": (
                "component_promote"
                if correctness_pass and bound >= 0.03
                else "component_reject"
            ),
            "pass": correctness_pass,
            "promotion_pass": correctness_pass and bound >= 0.03,
            "identity": {
                "gpu": torch.cuda.get_device_name(),
                "capability": list(torch.cuda.get_device_capability()),
                "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
                "torch": torch.__version__,
                "cuda": torch.version.cuda,
                "component_snapshot_sha256": sha256(args.w4_component),
                "source_sha256": source_identity,
                "candidate_symbol": "sglang.srt.hardware_backend.gpu.quantization.awq_kernels.AWQMarlinLinearKernel.apply",
                "control_symbol": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
                "consumer": "MergedColumnParallelLinear gate_up_proj -> GeluAndMul -> down_proj",
            },
            "geometry": {
                "decode_m": list(MS),
                "gate_up": [HIDDEN, GATE_UP],
                "down": [INTERMEDIATE, HIDDEN],
                "layers": LAYERS,
                "c32_decode_steps": DECODE_STEPS,
            },
            "representation": {
                "bits": 4,
                "group_size": 128,
                "zero_point": True,
                "activation_dtype": "torch.bfloat16",
            },
            "tiny_discovery": tiny_metrics,
            "rows": rows,
            "call_weighted_bound": {
                "basis": "M32 warm CUDA-event p50, 60 MLP layers, 357 post-first-token decode steps, 32 completed requests",
                "control_layer_ms": control_layer_ms,
                "candidate_layer_ms": candidate_layer_ms,
                "saved_seconds_per_request": saved_request_seconds,
                "current_seconds_per_request": CONTROL_REQUEST_SECONDS,
                "whole_request_reduction_fraction": bound,
                "promotion_threshold": 0.03,
                "pass": bound >= 0.03,
            },
            "correctness_pass": correctness_pass,
        }
    except Exception as error:
        terminal["error"] = {
            "type": type(error).__name__,
            "message": str(error)[:4000],
        }
    atomic(args.output / "TERMINAL.json", terminal)
    return 0 if terminal.get("pass") else 20


if __name__ == "__main__":
    raise SystemExit(main())
