#!/usr/bin/env python3
import argparse
import math
import os
import time
from pathlib import Path

import torch

from fp8_actual import CASES, OUTPUT_TOKENS, atomic_json, run_head
from fp8_single_rank import _distribution_valid, single_rank_context
from w4_actual import run_case

MS = (12, 16)


def architecture_seconds(rows: list[dict[str, object]], arm: str, m: int) -> float:
    selected = [row for row in rows if row["m"] == m]
    if len(selected) != 6:
        raise RuntimeError(f"{arm} aggregation lacks six M={m} rows")
    return sum(float(row["architecture_multiplicity"]) * float(row[arm]["timing"]["cuda_event"]["p50_ms"]) * OUTPUT_TOKENS / m / 1000 for row in selected)


def row_valid(row: dict[str, object]) -> bool:
    return bool(
        row.get("pass")
        and row["w4"]["oracle_from_timed_outputs"]["pass"]
        and row["fp8"]["oracle_from_timed_outputs"]["pass"]
        and all(_distribution_valid(row[arm]["timing"][kind]) for arm in ("w4", "fp8") for kind in ("cuda_event", "synchronized_wall"))
        and all(_distribution_valid(row["bf16"]["timing"][kind]) for kind in ("cuda_event", "synchronized_wall"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("conditional",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    result: dict[str, object] = {"schema_version": 1, "stage": "conditional", "pass": False, "all_actual_consumers_pass": False, "economic_both_envelopes_falsified": False, "rows": [], "semantics": "AWQMarlin W4 group-128 asymmetric execution proxy only; no checkpoint or quality claim", "identity": {"model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4", "runtime_image": os.environ.get("RUNTIME_IMAGE_IDENTITY")}}
    measured_ms = 0.0
    teardown = {"attempted": False, "model_parallel_initialized_after": None, "torch_distributed_initialized_after": None, "pass": False}
    try:
        torch.manual_seed(args.seed)
        torch.set_default_dtype(torch.bfloat16)
        with single_rank_context() as group:
            result["group_identity"] = group
            for case in CASES:
                for m in MS:
                    row = run_case(case, m)
                    result["rows"].append(row)
                    for arm in ("w4", "fp8"):
                        measured_ms += sum(row[arm]["timing"]["cuda_event"]["raw_ms"])
                    measured_ms += sum(row["bf16"]["timing"]["cuda_event"]["raw_ms"])
            head = run_head(12)
            result["head"] = head
            measured_ms += sum(head["timing"]["cuda_event"]["raw_ms"])
            valid = len(result["rows"]) == 12 and all(row_valid(row) for row in result["rows"]) and bool(head.get("pass")) and group["pass"]
            per_shape = []
            for row in result["rows"]:
                w4 = float(row["w4"]["timing"]["cuda_event"]["p50_ms"])
                fp8 = float(row["fp8"]["timing"]["cuda_event"]["p50_ms"])
                reduction = 1.0 - w4 / fp8 if fp8 > 0 else -math.inf
                per_shape.append({"case": row["case"], "m": row["m"], "w4_p50_ms": w4, "fp8_p50_ms": fp8, "reduction": reduction, "at_least_20_percent_faster": reduction >= 0.20})
            w4_seconds = architecture_seconds(result["rows"], "w4", 12)
            fp8_seconds = architecture_seconds(result["rows"], "fp8", 12)
            head_seconds = float(head["timing"]["cuda_event"]["p50_ms"]) * OUTPUT_TOKENS / 12 / 1000
            component = w4_seconds + head_seconds
            nominated = bool(valid and all(row["at_least_20_percent_faster"] for row in per_shape) and component <= 0.60)
            result.update({"runtime": {"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability())}, "required_row_count": 12, "actual_row_count": len(result["rows"]), "all_actual_consumers_pass": valid, "pass": valid, "W4_DECISION": {"nominated": nominated, "per_shape": per_shape, "all_shapes_at_least_20_percent_faster": all(row["at_least_20_percent_faster"] for row in per_shape), "w4_linear_seconds_per_request_c12": w4_seconds, "matched_fp8_linear_seconds_per_request_c12": fp8_seconds, "bf16_head_seconds_per_request_c12": head_seconds, "w4_component_floor_seconds_per_request_c12": component, "component_floor_gate": 0.60}})
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    finally:
        from vllm.distributed.parallel_state import model_parallel_is_initialized
        teardown["attempted"] = True
        teardown["model_parallel_initialized_after"] = bool(model_parallel_is_initialized())
        teardown["torch_distributed_initialized_after"] = bool(torch.distributed.is_initialized())
        teardown["pass"] = not teardown["model_parallel_initialized_after"] and not teardown["torch_distributed_initialized_after"]
        result["group_teardown"] = teardown
        result["pass"] = bool(result.get("pass") and teardown["pass"])
        result["all_actual_consumers_pass"] = bool(result.get("all_actual_consumers_pass") and teardown["pass"])
        result["useful_gpu_seconds"] = measured_ms / 1000
        result["scientific_wall_seconds"] = time.perf_counter() - started
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
