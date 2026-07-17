#!/usr/bin/env python3
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

MS = (1, 2, 4, 8, 16, 32)
HIDDEN = 5376
VOCAB = 262144
STEPS = 358
PLANNING_SECONDS = 1.394581
CONSERVATIVE_SECONDS = 0.86329
BANDWIDTH_FLOOR_MS = 2818572288 / (864 * 1_000_000) * 1000


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[max(0, min(len(values) - 1, int((len(values) - 1) * fraction)))]


def timed(fn, repetitions: int) -> tuple[list[float], list[float]]:
    cuda_ms, wall_ms = [], []
    for _ in range(repetitions):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        wall_start = time.perf_counter()
        start.record()
        output = fn()
        end.record()
        end.synchronize()
        wall_ms.append((time.perf_counter() - wall_start) * 1000)
        cuda_ms.append(start.elapsed_time(end))
        if not bool(torch.isfinite(output).all()) or float(output.float().abs().max()) != 0.0:
            raise RuntimeError("timed ParallelLMHead output violated finite zero oracle")
    return cuda_ms, wall_ms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    result: dict[str, object] = {
        "schema_version": 1,
        "stage": args.stage,
        "pass": False,
        "all_actual_consumers_pass": False,
        "economic_both_envelopes_falsified": False,
        "geometry": {"m_values": list(MS), "hidden": HIDDEN, "vocab": VOCAB, "dtype": "bfloat16"},
        "timing_contract": {"warmups": 5, "repetitions": 15, "cuda_event_and_wall": True, "setup_outside_timing": True},
        "rows": [],
    }
    try:
        torch.manual_seed(args.seed)
        config = VllmConfig()
        config.model_config = types.SimpleNamespace(dtype=torch.bfloat16, head_dtype=None, is_moe=False)
        with set_current_vllm_config(config):
            init_distributed_environment(world_size=1, rank=0, distributed_init_method="tcp://127.0.0.1:29500", local_rank=0, backend="nccl")
            ensure_model_parallel_initialized(1, 1)
            with torch.device("cuda"):
                head = ParallelLMHead(VOCAB, HIDDEN, params_dtype=torch.bfloat16, prefix="model.lm_head")
            head.weight.data.zero_()
            consumer = f"{type(head).__module__}.{type(head).__name__}"
            method = f"{type(head.quant_method).__module__}.{type(head.quant_method).__name__}"
            result["runtime"] = {
                "vllm_version": vllm.__version__,
                "consumer": consumer,
                "quantization_method": method,
                "consumer_source_sha256": hashlib.sha256(inspect.getsource(type(head)).encode()).hexdigest(),
                "method_source_sha256": hashlib.sha256(inspect.getsource(type(head.quant_method)).encode()).hexdigest(),
            }
            for m in MS:
                activations = torch.randn((m, HIDDEN), device="cuda", dtype=torch.bfloat16)
                apply = lambda: head.quant_method.apply(head, activations, None)
                for _ in range(5):
                    warm = apply()
                    if not bool(torch.isfinite(warm).all()) or float(warm.float().abs().max()) != 0.0:
                        raise RuntimeError(f"warmup zero oracle failed at M={m}")
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                cuda_ms, wall_ms = timed(apply, 15)
                output = apply()
                finite = bool(torch.isfinite(output).all())
                error = float(output.float().abs().max())
                p50 = statistics.median(cuda_ms)
                row = {
                    "m": m,
                    "activations_shape": [m, HIDDEN],
                    "weight_shape": [VOCAB, HIDDEN],
                    "input_dtype": str(activations.dtype),
                    "weight_dtype": str(head.weight.dtype),
                    "output_dtype": str(output.dtype),
                    "finite": finite,
                    "max_absolute_error_zero_oracle": error,
                    "pass": finite and error == 0.0,
                    "cuda_event_ms": {"p50": p50, "p95": percentile(cuda_ms, 0.95), "raw": cuda_ms},
                    "wall_ms": {"p50": statistics.median(wall_ms), "p95": percentile(wall_ms, 0.95), "raw": wall_ms},
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                    "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                    "per_request_head_seconds_at_358_steps": p50 / m * STEPS / 1000,
                    "planning_budget_seconds": PLANNING_SECONDS,
                    "conservative_budget_seconds": CONSERVATIVE_SECONDS,
                    "bandwidth_floor_ms": BANDWIDTH_FLOOR_MS,
                }
                row["planning_head_alone_exceeds"] = row["per_request_head_seconds_at_358_steps"] > PLANNING_SECONDS
                row["conservative_head_alone_exceeds"] = row["per_request_head_seconds_at_358_steps"] > CONSERVATIVE_SECONDS
                result["rows"].append(row)
                del activations, output
        rows = result["rows"]
        result["all_actual_consumers_pass"] = len(rows) == len(MS) and all(row["pass"] for row in rows)
        result["economic_both_envelopes_falsified"] = all(row["planning_head_alone_exceeds"] and row["conservative_head_alone_exceeds"] for row in rows)
        result["pass"] = result["all_actual_consumers_pass"] is True
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
    result["useful_gpu_seconds"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
