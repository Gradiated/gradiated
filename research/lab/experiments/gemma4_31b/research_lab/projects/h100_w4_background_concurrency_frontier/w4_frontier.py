#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import h100_w4_marlin_tp_single_rank as context
import h100_w4_marlin_falsifier as program

MS = (48, 64, 96, 128)


def aggregate_frontier(rows):
    expected = {(entry[0][0], m) for entry in program.selected("sweep")[::4] for m in MS}
    observed = {(row["case"], row["m"]) for row in rows}
    if len(rows) != 24 or observed != expected:
        raise RuntimeError("expected six exact Gemma shapes at each of M48/M64/M96/M128")
    result = {}
    for m in MS:
        w4_step = sum(row["architecture_multiplicity"] * row["cold_candidate_timing"]["cuda_event"]["p50_ms"] for row in rows if row["m"] == m) / 1000
        bf16_step = sum(row["architecture_multiplicity"] * row["cold_bf16_comparator_timing"]["cuda_event"]["p50_ms"] for row in rows if row["m"] == m) / 1000
        result[str(m)] = {"w4_decode_linear_seconds_per_request_at_358_steps": w4_step * 358 / m, "bf16_decode_linear_seconds_per_request_at_358_steps": bf16_step * 358 / m, "w4_decode_batch_duration_seconds_at_358_steps": w4_step * 358, "bf16_decode_batch_duration_seconds_at_358_steps": bf16_step * 358, "w4_linear_reduction_fraction": 1 - w4_step / bf16_step}
    return {"timing_basis": "cold CUDA-event p50; generated-token linear proxy only (358 steps), excluding prompt and attention", "by_concurrency": result}


def main() -> int:
    target = Path(sys.argv[sys.argv.index("--output") + 1])
    result = {"schema_version": 1, "type": "gemma4_h100_w4_machete_background_frontier", "stage": "primary", "concurrency": list(MS), "rows": [], "pass": False}
    try:
        with context.single_rank_context() as tp:
            for case in (entry[0] for entry in program.selected("sweep")[::4]):
                prepared = program.make_case(case, 20260718)
                for m in MS:
                    result["rows"].append(program.run_row(case, m, 20260718, prepared))
                del prepared
                program.torch.cuda.empty_cache()
            result["tensor_parallel_context"] = tp
        result["all_actual_consumers_pass"] = all(row["pass"] for row in result["rows"])
        result["aggregation"] = aggregate_frontier(result["rows"])
        result["pass"] = bool(result["all_actual_consumers_pass"] and len(result["rows"]) == 24)
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    program.atomic(target, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
