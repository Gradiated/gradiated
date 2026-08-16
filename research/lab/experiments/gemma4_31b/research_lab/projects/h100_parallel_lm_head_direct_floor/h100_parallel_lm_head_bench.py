#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
import types
from pathlib import Path

import torch
import vllm
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.distributed.parallel_state import ensure_model_parallel_initialized, init_distributed_environment
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead

from h100_head_contract import CEILING_SECONDS, atomic_json

HIDDEN = 5376
VOCAB = 262144
STEPS = 358
EXPECTED_GPU = "NVIDIA H100 80GB HBM3"


def percentile(values: list[float], q: float) -> float:
    return sorted(values)[int((len(values) - 1) * q)]


def timed(apply, repetitions: int) -> tuple[list[float], list[float], float]:
    cuda_ms, wall_ms, checksum = [], [], 0.0
    for _ in range(repetitions):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        wall_start = time.perf_counter()
        start.record(); output = apply(); end.record(); end.synchronize()
        cuda_ms.append(start.elapsed_time(end))
        wall_ms.append((time.perf_counter() - wall_start) * 1000)
        finite = bool(torch.isfinite(output).all())
        maximum, minimum = float(output.float().max()), float(output.float().min())
        if not finite or maximum <= 0 or minimum >= 0:
            raise RuntimeError("timed ParallelLMHead output violated finite/nonzero/varied-sign oracle")
        checksum += float(output.float().sum())
    return cuda_ms, wall_ms, checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("sentinel", "remainder"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    ms = (8,) if args.stage == "sentinel" else (16, 32)
    result: dict[str, object] = {
        "schema_version": 1, "type": "gemma4_h100_actual_parallel_lm_head_bf16",
        "stage": args.stage, "pass": False, "all_actual_consumers_pass": False,
        "geometry": {"m_values": list(ms), "hidden": HIDDEN, "vocab": VOCAB, "steps": STEPS, "dtype": "bfloat16"},
        "timing_contract": {"warmups": 5, "repetitions": 15, "setup_outside_timing": True, "cuda_event_and_synchronized_wall": True},
        "rows": [],
    }
    started = time.perf_counter()
    try:
        torch.manual_seed(args.seed); torch.cuda.manual_seed_all(args.seed)
        name = torch.cuda.get_device_name(0); capability = tuple(torch.cuda.get_device_capability(0)); props = torch.cuda.get_device_properties(0)
        if name != EXPECTED_GPU or capability != (9, 0) or props.total_memory < 80 * 1024**3:
            raise RuntimeError(f"expected full H100 80GB capability 9.0, got {name} {capability} {props.total_memory}")
        config = VllmConfig(); config.model_config = types.SimpleNamespace(dtype=torch.bfloat16, head_dtype=None, is_moe=False)
        with set_current_vllm_config(config):
            init_distributed_environment(world_size=1, rank=0, distributed_init_method="tcp://127.0.0.1:29500", local_rank=0, backend="nccl")
            ensure_model_parallel_initialized(1, 1)
            with torch.device("cuda"):
                head = ParallelLMHead(VOCAB, HIDDEN, params_dtype=torch.bfloat16, prefix="model.lm_head")
        # Deterministic varied-sign, nonzero BF16 weights without a second full-size allocation.
        head.weight.data.fill_(1.0 / 128.0); head.weight.data[1::2].neg_()
        consumer = f"{type(head).__module__}.{type(head).__name__}"
        method = f"{type(head.quant_method).__module__}.{type(head.quant_method).__name__}"
        result["runtime"] = {
            "vllm_version": vllm.__version__, "torch": torch.__version__, "cuda": torch.version.cuda,
            "gpu_name": name, "gpu_capability": list(capability), "gpu_total_memory_bytes": props.total_memory,
            "consumer": consumer, "quantization_method": method,
            "consumer_source_sha256": hashlib.sha256(inspect.getsource(type(head)).encode()).hexdigest(),
            "method_source_sha256": hashlib.sha256(inspect.getsource(type(head.quant_method)).encode()).hexdigest(),
        }
        for m in ms:
            activations = torch.ones((m, HIDDEN), device="cuda", dtype=torch.bfloat16)
            activations[:, 1::2].fill_(-0.5)
            activations.mul_(torch.arange(1, m + 1, device="cuda", dtype=torch.bfloat16)[:, None] / m)
            apply = lambda: head.quant_method.apply(head, activations, None)
            for _ in range(5):
                warm = apply()
                if not bool(torch.isfinite(warm).all()) or float(warm.float().max()) <= 0 or float(warm.float().min()) >= 0:
                    raise RuntimeError(f"warmup oracle failed at M={m}")
            torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
            cuda_ms, wall_ms, checksum = timed(apply, 15)
            output = apply(); maximum, minimum = float(output.float().max()), float(output.float().min())
            p50 = statistics.median(cuda_ms)
            row = {
                "m": m, "activation_shape": [m, HIDDEN], "weight_shape": [VOCAB, HIDDEN],
                "input_dtype": str(activations.dtype), "weight_dtype": str(head.weight.dtype), "output_dtype": str(output.dtype),
                "oracle": {"finite": bool(torch.isfinite(output).all()), "nonzero": maximum != 0 or minimum != 0, "varied_sign": maximum > 0 and minimum < 0, "consumed_checksum": checksum},
                "cuda_event_ms": {"p50": p50, "p95": percentile(cuda_ms, .95), "raw": cuda_ms},
                "wall_ms": {"p50": statistics.median(wall_ms), "p95": percentile(wall_ms, .95), "raw": wall_ms},
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                "per_request_head_seconds_at_358_steps": p50 / 1000 * STEPS / m,
                "ceiling_seconds_per_request": CEILING_SECONDS,
            }
            row["survives_ceiling"] = row["per_request_head_seconds_at_358_steps"] < CEILING_SECONDS
            row["pass"] = all(row["oracle"][key] is True for key in ("finite", "nonzero", "varied_sign")) and p50 > 0
            result["rows"].append(row)
            del activations, warm, output
        result["all_actual_consumers_pass"] = len(result["rows"]) == len(ms) and all(row["pass"] for row in result["rows"])
        result["pass"] = result["all_actual_consumers_pass"] is True
        if args.stage == "sentinel": result["sentinel"] = {"m": 8, "pass": result["pass"] and len(result["rows"]) == 1}
        else: result["remainder"] = {"required_ms": list(ms), "pass": result["pass"], "surviving_concurrencies": [row["m"] for row in result["rows"] if row["survives_ceiling"]]}
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
    result["useful_gpu_seconds"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True); atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
