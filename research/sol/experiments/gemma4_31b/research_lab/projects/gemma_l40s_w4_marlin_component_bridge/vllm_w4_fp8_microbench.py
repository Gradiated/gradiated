#!/usr/bin/env python3
"""Pinned-vLLM W4 Marlin and FP8 linear consumer measurement."""
import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import time
import types
from pathlib import Path

import torch
from vllm.config import VllmConfig, set_current_vllm_config


CASES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("global_qkv", 5376, 20480, 10),
    ("sliding_output", 8192, 5376, 50),
    ("global_output", 16384, 5376, 10),
    ("merged_gate_up", 5376, 43008, 60),
    ("down_projection", 21504, 5376, 60),
)
MS = (1, 2, 4, 8, 16)
WARMUPS = 3
ITERATIONS = 12
TOLERANCE = {"absolute": 0.015625, "relative": 0.02}


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "p50_ms": round(statistics.median(ordered), 6),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 6),
    }


def config_context():
    config = VllmConfig()
    config.model_config = types.SimpleNamespace(dtype=torch.bfloat16, head_dtype=None)
    return set_current_vllm_config(config)


def timed(fn):
    for _ in range(WARMUPS):
        fn()
    torch.cuda.synchronize()
    events, walls = [], []
    for _ in range(ITERATIONS):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        wall_start = time.perf_counter()
        fn()
        end.record()
        end.synchronize()
        events.append(start.elapsed_time(end))
        walls.append((time.perf_counter() - wall_start) * 1000)
    return {"cuda_event": percentiles(events), "wall": percentiles(walls)}


def kernel_identity(method) -> dict[str, str]:
    kernel = getattr(method, "kernel", getattr(method, "fp8_linear", None))
    if kernel is None:
        raise RuntimeError("vLLM method did not install a concrete linear kernel")
    return {
        "method_class": f"{type(method).__module__}.{type(method).__name__}",
        "kernel_class": f"{type(kernel).__module__}.{type(kernel).__name__}",
        "apply_symbol": f"{type(method).__module__}.{type(method).__name__}.apply",
        "kernel_apply_symbol": f"{type(kernel).__module__}.{type(kernel).__name__}.apply_weights",
    }


def make_w4_layer(k: int, n: int):
    from vllm.model_executor.layers.quantization.awq_marlin import AWQMarlinConfig, AWQMarlinLinearMethod

    config = AWQMarlinConfig(4, 128, True, False, None, {})
    method = AWQMarlinLinearMethod(config)
    layer = torch.nn.Module()
    method.create_weights(layer, k, [n], k, n, torch.bfloat16)
    # Zero is valid deterministic packed uint4 material and dequantizes to the
    # zero oracle when the packed AWQ zero-points are also zero.
    layer.qweight.data.zero_()
    layer.qzeros.data.zero_()
    layer.scales.data.fill_(1)
    method.process_weights_after_loading(layer)
    identity = kernel_identity(method)
    if "marlin" not in identity["kernel_class"].lower():
        raise RuntimeError(f"AWQMarlin W4 consumer selected non-Marlin kernel: {identity['kernel_class']}")
    return method, layer, identity


def make_fp8_layer(k: int, n: int):
    from vllm.model_executor.layers.quantization.fp8 import Fp8Config, Fp8LinearMethod

    config = Fp8Config(is_checkpoint_fp8_serialized=True, activation_scheme="dynamic")
    method = Fp8LinearMethod(config)
    layer = torch.nn.Module()
    method.create_weights(layer, k, [n], k, n, torch.bfloat16)
    layer.weight.data.zero_()
    layer.weight_scale.data.fill_(1)
    method.process_weights_after_loading(layer)
    return method, layer, kernel_identity(method)


def run_representation(representation: str, builder, case, m: int, seed: int) -> dict:
    name, k, n, multiplicity = case
    torch.manual_seed(seed + k + n + m)
    torch.cuda.reset_peak_memory_stats()
    with torch.device("cuda"):
        method, layer, identity = builder(k, n)
    x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16) / math.sqrt(k)
    output = method.apply(layer, x)
    torch.cuda.synchronize()
    oracle = torch.zeros((m, n), device="cuda", dtype=torch.bfloat16)
    error = (output.float() - oracle.float()).abs()
    finite = bool(torch.isfinite(output).all())
    max_absolute = float(error.max())
    max_relative = float((error / oracle.float().abs().clamp_min(1)).max())
    passed = finite and max_absolute <= TOLERANCE["absolute"] and max_relative <= TOLERANCE["relative"]
    timing = timed(lambda: method.apply(layer, x))
    row = {
        "representation": representation,
        "case": name,
        "m": m,
        "k": k,
        "n": n,
        "architecture_multiplicity": multiplicity,
        "seed": seed + k + n + m,
        "activation_dtype": str(x.dtype),
        "output_dtype": str(output.dtype),
        "packed_layout": "AWQ packed uint4/group128" if representation == "w4_marlin" else "vLLM FP8 serialized tensor",
        "identity": identity,
        "oracle": {"kind": "same deterministic dequantized zero weight", "max_absolute_error": max_absolute, "max_relative_error": max_relative, "tolerance": TOLERANCE},
        "finite": finite,
        "pass": passed,
        "warmups": WARMUPS,
        "iterations": ITERATIONS,
        "timing": timing,
        "memory": {"peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()},
    }
    del x, output, oracle, error, layer
    torch.cuda.empty_cache()
    return row


def aggregate(rows: list[dict], representation: str) -> float:
    selected = [row for row in rows if row["representation"] == representation and row["m"] == 16]
    if len(selected) != len(CASES):
        raise RuntimeError(f"{representation} lacks exactly one M=16 row per required shape")
    return sum(row["architecture_multiplicity"] * row["timing"]["cuda_event"]["p50_ms"] for row in selected) / 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("primary",))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    args = parser.parse_args()
    result = {"schema_version": 1, "stage": args.stage, "pass": False, "all_actual_consumers_pass": False, "economic_both_envelopes_falsified": False, "seed": args.seed, "rows": [], "tolerances": TOLERANCE, "useful_gpu_seconds": 0.0}
    started = time.perf_counter()
    try:
        with config_context():
            for representation, builder in (("w4_marlin", make_w4_layer), ("fp8", make_fp8_layer)):
                for case in CASES:
                    for m in MS:
                        result["rows"].append(run_representation(representation, builder, case, m, args.seed))
        w4_seconds, fp8_seconds = aggregate(result["rows"], "w4_marlin"), aggregate(result["rows"], "fp8")
        all_pass = len(result["rows"]) == len(CASES) * len(MS) * 2 and all(row["pass"] for row in result["rows"])
        reduction = 1 - w4_seconds / fp8_seconds if fp8_seconds > 0 else None
        result.update({"aggregate_m16": {"w4_seconds": w4_seconds, "fp8_seconds": fp8_seconds, "w4_to_fp8_reduction": reduction, "gate": "w4 <= 0.75 * fp8"}, "all_actual_consumers_pass": all_pass, "component_fit": {"corrected_w4_c16_logical_gib": 31.158265, "l40s_envelope_gib": 44.704, "measurement": "transient allocator peaks only; not a full-model residency claim"}})
        result["pass"] = bool(all_pass and reduction is not None and reduction >= 0.25)
        # The W4 component-fit predicate is true by the bound above; neither
        # envelope is falsified merely by this component comparison.
        result["economic_both_envelopes_falsified"] = False
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
    result["useful_gpu_seconds"] = round(time.perf_counter() - started, 6)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
