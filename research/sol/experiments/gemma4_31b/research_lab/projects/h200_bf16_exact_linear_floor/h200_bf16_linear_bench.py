#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

import torch

MS = (1, 4, 8, 16, 32)
STEPS = 358
STRICT_SECONDS = 0.47201182295214134
LENIENT_SECONDS = 0.47751364375858635
SHAPES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("global_qkv", 5376, 20480, 10),
    ("gate_up", 5376, 43008, 60),
    ("sliding_output", 8192, 5376, 50),
    ("global_output", 16384, 5376, 10),
    ("down", 21504, 5376, 60),
)


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction)))]


def timed_matmul(activations: torch.Tensor, weight_t: torch.Tensor, repetitions: int) -> tuple[list[float], list[float], float]:
    cuda_ms: list[float] = []
    wall_ms: list[float] = []
    checksum = 0.0
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        wall_start = time.perf_counter()
        start.record()
        output = torch.matmul(activations, weight_t)
        end.record()
        end.synchronize()
        wall_ms.append((time.perf_counter() - wall_start) * 1000.0)
        cuda_ms.append(start.elapsed_time(end))
        finite = bool(torch.isfinite(output).all())
        maximum = float(output.float().abs().max())
        checksum += float(output.float().sum())
        if not finite or maximum != 0.0:
            raise RuntimeError("timed torch.matmul output violated finite zero oracle")
    return cuda_ms, wall_ms, checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    benchmark_started = time.perf_counter()
    result: dict[str, object] = {
        "schema_version": 1,
        "stage": args.stage,
        "pass": False,
        "all_actual_consumers_pass": False,
        "economic_both_envelopes_falsified": False,
        "geometry": {
            "m_values": list(MS),
            "shapes": [
                {"name": name, "input": input_size, "output": output_size, "multiplicity": multiplicity}
                for name, input_size, output_size, multiplicity in SHAPES
            ],
            "dtype": "torch.bfloat16",
            "decode_steps": STEPS,
        },
        "timing_contract": {
            "warmups": 5,
            "repetitions": 15,
            "setup_outside_timing": True,
            "cuda_event_and_synchronized_wall": True,
            "consumer": "torch.matmul(activations, weight.transpose(0, 1))",
        },
        "rows": [],
        "architecture_weighted": [],
    }
    useful_gpu_seconds = 0.0
    try:
        torch.manual_seed(args.seed)
        torch.cuda.manual_seed_all(args.seed)
        gpu_name = torch.cuda.get_device_name()
        properties = torch.cuda.get_device_properties(0)
        if "H200" not in gpu_name or properties.total_memory < 130 * 1024**3:
            raise RuntimeError(f"expected one full H200, got {gpu_name} with {properties.total_memory} bytes")
        result["runtime"] = {
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "gpu_name": gpu_name,
            "gpu_capability": list(torch.cuda.get_device_capability()),
            "gpu_total_memory_bytes": properties.total_memory,
            "gpu_count": torch.cuda.device_count(),
            "consumer": "torch.matmul",
            "consumer_source_identity": hashlib.sha256(b"torch.matmul(activations,weight.transpose(0,1))").hexdigest(),
            "seed": args.seed,
        }
        rows_by_m: dict[int, list[dict[str, object]]] = {m: [] for m in MS}
        for shape_name, input_size, output_size, multiplicity in SHAPES:
            weight = torch.zeros((output_size, input_size), device="cuda", dtype=torch.bfloat16)
            weight_t = weight.transpose(0, 1)
            for m in MS:
                activations = torch.randn((m, input_size), device="cuda", dtype=torch.bfloat16)
                for _ in range(5):
                    warm = torch.matmul(activations, weight_t)
                    if not bool(torch.isfinite(warm).all()) or float(warm.float().abs().max()) != 0.0:
                        raise RuntimeError(f"warmup oracle failed for {shape_name} at M={m}")
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                cuda_ms, wall_ms, checksum = timed_matmul(activations, weight_t, 15)
                useful_gpu_seconds += sum(wall_ms) / 1000.0
                row = {
                    "shape": shape_name,
                    "m": m,
                    "multiplicity": multiplicity,
                    "activation_shape": [m, input_size],
                    "weight_shape": [output_size, input_size],
                    "output_shape": [m, output_size],
                    "activation_dtype": str(activations.dtype),
                    "weight_dtype": str(weight.dtype),
                    "finite_zero_oracle": True,
                    "consumed_checksum": checksum,
                    "pass": checksum == 0.0,
                    "cuda_event_ms": {"p50": statistics.median(cuda_ms), "p95": percentile(cuda_ms, 0.95), "raw": cuda_ms},
                    "wall_ms": {"p50": statistics.median(wall_ms), "p95": percentile(wall_ms, 0.95), "raw": wall_ms},
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                    "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                }
                result["rows"].append(row)
                rows_by_m[m].append(row)
                del activations, warm
            del weight_t, weight
            torch.cuda.empty_cache()
        for m in MS:
            rows = rows_by_m[m]
            if len(rows) != len(SHAPES):
                raise RuntimeError(f"wrong shape count at M={m}")
            cuda_step_ms = sum(float(row["cuda_event_ms"]["p50"]) * int(row["multiplicity"]) for row in rows)
            wall_step_ms = sum(float(row["wall_ms"]["p50"]) * int(row["multiplicity"]) for row in rows)
            cuda_request_seconds = cuda_step_ms * STEPS / m / 1000.0
            wall_request_seconds = wall_step_ms * STEPS / m / 1000.0
            result["architecture_weighted"].append({
                "m": m,
                "cuda_decode_step_ms": cuda_step_ms,
                "wall_decode_step_ms": wall_step_ms,
                "cuda_request_seconds_358_steps": cuda_request_seconds,
                "wall_request_seconds_358_steps": wall_request_seconds,
                "economic_lower_bound_seconds_358_steps": cuda_request_seconds,
                "economic_lower_bound_basis": "architecture-weighted CUDA-event p50 sum; synchronized isolated wall intervals are diagnostic only",
                "strict_total_service_ceiling_seconds": STRICT_SECONDS,
                "lenient_total_service_ceiling_seconds": LENIENT_SECONDS,
                "linear_floor_exceeds_strict": cuda_request_seconds > STRICT_SECONDS,
                "linear_floor_exceeds_lenient": cuda_request_seconds > LENIENT_SECONDS,
            })
        rows = result["rows"]
        weighted = result["architecture_weighted"]
        result["all_actual_consumers_pass"] = len(rows) == len(SHAPES) * len(MS) and all(row["pass"] for row in rows)
        result["economic_both_envelopes_falsified"] = all(row["linear_floor_exceeds_lenient"] for row in weighted)
        high_batch = [row for row in weighted if row["m"] in (16, 32)]
        result["h200_head_trigger_basis"] = {
            "all_primary_rows_valid": result["all_actual_consumers_pass"],
            "m16_or_m32_at_most_120pct_strict": any(row["cuda_request_seconds_358_steps"] <= 1.2 * STRICT_SECONDS for row in high_batch),
            "head_could_change_classification": any(row["cuda_request_seconds_358_steps"] <= LENIENT_SECONDS for row in high_batch),
            "strict_seconds": STRICT_SECONDS,
            "lenient_seconds": LENIENT_SECONDS,
            "basis": "CUDA-event architecture-weighted lower bound",
        }
        result["pass"] = result["all_actual_consumers_pass"] is True
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
    result["useful_gpu_seconds"] = useful_gpu_seconds
    result["benchmark_wall_seconds"] = time.perf_counter() - benchmark_started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
