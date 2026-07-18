#!/usr/bin/env python3
import argparse
import hashlib
import inspect
import json
import math
import os
import time
from pathlib import Path

import torch
from vllm import _custom_ops as ops
from vllm.model_executor.layers.quantization.awq_marlin import AWQMarlinConfig, AWQMarlinLinearMethod
from vllm.model_executor.layers.quantization.fp8 import Fp8Config, Fp8OnlineLinearMethod

from fp8_actual import (
    CASES,
    OUTPUT_TOKENS,
    atomic_json,
    config_context,
    error_record,
    make_bf16_layer,
    run_head,
    time_cuda,
)


MS = (14, 16)
TOLERANCE = {"absolute": 0.15, "relative": 0.10}


def make_w4_and_dense(k: int, n: int):
    config = AWQMarlinConfig(4, 128, True, False, None, {})
    method = AWQMarlinLinearMethod(config)
    layer = torch.nn.Module()
    with torch.device("cuda"):
        method.create_weights(layer, k, [n], k, n, torch.bfloat16)
    layer.qweight.data.fill_(-1717986919)
    layer.qzeros.data.fill_(2004318071)
    layer.scales.data.fill_(0.0078125)
    dense_k_n = ops.awq_dequantize(layer.qweight, layer.scales, layer.qzeros, 0, 0, 0).to(torch.bfloat16)
    if dense_k_n.shape != (k, n):
        raise RuntimeError(f"AWQ dequantized oracle has shape {tuple(dense_k_n.shape)}, expected {(k, n)}")
    if not bool(torch.isfinite(dense_k_n).all()) or not bool(float(dense_k_n.abs().max()) > 1e-4):
        raise RuntimeError("AWQ dequantized oracle is nonfinite or trivial")
    method.process_weights_after_loading(layer)
    kernel = getattr(method, "kernel", None)
    if kernel is None or "marlin" not in type(kernel).__name__.lower():
        raise RuntimeError(f"AWQMarlinLinearMethod selected non-Marlin kernel {type(kernel).__name__}")
    return method, layer, dense_k_n, {
        "method_class": f"{type(method).__module__}.{type(method).__name__}",
        "kernel_class": f"{type(kernel).__module__}.{type(kernel).__name__}",
        "method_source_sha256": hashlib.sha256(inspect.getsource(AWQMarlinLinearMethod).encode()).hexdigest(),
        "packed_weight_pattern_signed_int32": -1717986919,
        "packed_zero_pattern_signed_int32": 2004318071,
        "group_size": 128,
        "zero_point": True,
        "scale": 0.0078125,
    }


def replace_dense_weight(layer: torch.nn.Module, dense_n_k: torch.Tensor) -> None:
    layer._parameters["weight"] = torch.nn.Parameter(dense_n_k, requires_grad=False)


def make_matched_fp8_layer(k: int, n: int, dense_n_k: torch.Tensor):
    method = Fp8OnlineLinearMethod(Fp8Config(is_checkpoint_fp8_serialized=False, activation_scheme="dynamic"))
    layer = torch.nn.Module()
    method.create_weights(layer, k, [n], k, n, torch.bfloat16)
    replace_dense_weight(layer, dense_n_k)
    method.process_weights_after_loading(layer)
    kernel = getattr(method, "fp8_linear", None)
    if kernel is None:
        raise RuntimeError("matched online FP8 method has no concrete kernel")
    return method, layer, {
        "method_class": f"{type(method).__module__}.{type(method).__name__}",
        "kernel_class": f"{type(kernel).__module__}.{type(kernel).__name__}",
    }


def run_case(case: tuple[str, int, int, int], m: int) -> dict[str, object]:
    name, k, n, multiplicity = case
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    w4_method, w4_layer, dense_k_n, identity = make_w4_and_dense(k, n)
    dense_n_k = dense_k_n.t().contiguous()
    bf16_method, bf16_layer = make_bf16_layer(k, n, 0.0)
    replace_dense_weight(bf16_layer, dense_n_k)
    fp8_method, fp8_layer, fp8_identity = make_matched_fp8_layer(k, n, dense_n_k.clone())
    x = torch.full((m, k), 1.0 / math.sqrt(k), device="cuda", dtype=torch.bfloat16)
    w4_timing, w4_output = time_cuda(lambda: w4_method.apply(w4_layer, x), 3, 7)
    fp8_timing, fp8_output = time_cuda(lambda: fp8_method.apply(fp8_layer, x), 3, 7)
    bf16_timing, bf16_output = time_cuda(lambda: bf16_method.apply(bf16_layer, x), 3, 7)
    if w4_output is None or fp8_output is None or bf16_output is None:
        raise RuntimeError("one actual timed consumer returned no tensor")
    w4_oracle = error_record(w4_output, bf16_output, TOLERANCE)
    fp8_oracle = error_record(fp8_output, bf16_output, TOLERANCE)
    row = {
        "case": name,
        "m": m,
        "k": k,
        "n": n,
        "architecture_multiplicity": multiplicity,
        "w4": {"identity": identity, "timing": w4_timing, "oracle_from_timed_outputs": w4_oracle},
        "fp8": {"identity": fp8_identity, "timing": fp8_timing, "oracle_from_timed_outputs": fp8_oracle},
        "bf16": {"method_class": f"{type(bf16_method).__module__}.{type(bf16_method).__name__}", "timing": bf16_timing},
        "producer_to_timer_connected": True,
        "allocator": {"peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()},
        "pass": w4_oracle["pass"] and fp8_oracle["pass"],
    }
    del x, w4_output, fp8_output, bf16_output, w4_layer, fp8_layer, bf16_layer, dense_k_n, dense_n_k
    torch.cuda.empty_cache()
    return row


def architecture_seconds(rows: list[dict[str, object]], representation: str, m: int) -> float:
    selected = [row for row in rows if row["m"] == m]
    if len(selected) != len(CASES):
        raise RuntimeError(f"{representation} aggregation lacks six M={m} rows")
    return sum(
        float(row["architecture_multiplicity"])
        * float(row[representation]["timing"]["cuda_event"]["p50_ms"])
        * OUTPUT_TOKENS
        / m
        / 1000
        for row in selected
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("conditional",))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    result: dict[str, object] = {
        "schema_version": 2,
        "stage": args.stage,
        "pass": False,
        "all_actual_consumers_pass": False,
        "economic_both_envelopes_falsified": False,
        "rows": [],
        "head": None,
        "semantics": "W4 group-128 asymmetric mechanism proxy only; no checkpoint quality claim",
    }
    measured_event_ms = 0.0
    try:
        torch.manual_seed(args.seed)
        torch.set_default_dtype(torch.bfloat16)
        with config_context():
            for case in CASES:
                for m in MS:
                    result["rows"].append(run_case(case, m))
            result["head"] = run_head(16)
        valid = len(result["rows"]) == len(CASES) * len(MS) and all(row["pass"] for row in result["rows"]) and result["head"]["pass"]
        w4_seconds = architecture_seconds(result["rows"], "w4", 16)
        fp8_seconds = architecture_seconds(result["rows"], "fp8", 16)
        head_seconds = float(result["head"]["timing"]["cuda_event"]["p50_ms"]) * OUTPUT_TOKENS / 16 / 1000
        reduction = 1 - w4_seconds / fp8_seconds if fp8_seconds > 0 else None
        component_floor = w4_seconds + head_seconds
        nominated = bool(valid and reduction is not None and reduction >= 0.20 and component_floor <= 0.60)
        for row in result["rows"]:
            for representation in ("w4", "fp8"):
                measured_event_ms += sum(row[representation]["timing"]["cuda_event"]["raw_ms"])
            measured_event_ms += sum(row["bf16"]["timing"]["cuda_event"]["raw_ms"])
        measured_event_ms += sum(result["head"]["timing"]["cuda_event"]["raw_ms"])
        result.update({
            "all_actual_consumers_pass": valid,
            "pass": valid,
            "W4_DECISION": {
                "nominated": nominated,
                "w4_linear_seconds_per_request_c16": w4_seconds,
                "fp8_linear_seconds_per_request_c16": fp8_seconds,
                "actual_bf16_head_seconds_per_request_c16": head_seconds,
                "disjoint_w4_component_floor_seconds_per_request_c16": component_floor,
                "w4_to_fp8_reduction": reduction,
                "reduction_gate": 0.20,
                "component_floor_gate_seconds_per_request": 0.60,
            },
        })
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    result["useful_gpu_seconds"] = measured_event_ms / 1000
    result["scientific_wall_seconds"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
