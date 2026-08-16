#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import h100_w4_marlin_tp_single_rank as context
import h100_w4_marlin_falsifier as program


MS = (96, 128)


def aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    expected = {(entry[0][0], m) for entry in program.selected("sweep")[::4] for m in MS}
    observed = {(str(row["case"]), int(row["m"])) for row in rows}
    if len(rows) != 12 or observed != expected:
        raise RuntimeError("expected six exact Gemma shapes at each of M96/M128")
    by_concurrency = {}
    for m in MS:
        w4_step = sum(float(row["architecture_multiplicity"]) * float(row["cold_candidate_timing"]["cuda_event"]["p50_ms"]) for row in rows if row["m"] == m) / 1000
        bf16_step = sum(float(row["architecture_multiplicity"]) * float(row["cold_bf16_comparator_timing"]["cuda_event"]["p50_ms"]) for row in rows if row["m"] == m) / 1000
        by_concurrency[str(m)] = {
            "w4_decode_linear_seconds_per_request_at_358_steps": w4_step * 358 / m,
            "bf16_decode_linear_seconds_per_request_at_358_steps": bf16_step * 358 / m,
            "w4_decode_batch_duration_seconds_at_358_steps": w4_step * 358,
            "bf16_decode_batch_duration_seconds_at_358_steps": bf16_step * 358,
            "w4_linear_reduction_fraction": 1 - w4_step / bf16_step,
        }
    return {"timing_basis": "cold CUDA-event p50; generated-token linear proxy only (358 steps), excluding prompt and attention", "by_concurrency": by_concurrency}


def main() -> int:
    target = Path(sys.argv[sys.argv.index("--output") + 1])
    result: dict[str, object] = {"schema_version": 1, "type": "gemma4_h200_w4_machete_component_frontier", "stage": "primary", "concurrency": list(MS), "rows": [], "pass": False}
    try:
        program.GPU = "NVIDIA H200"
        with context.single_rank_context() as tp:
            sentinel_case, sentinel_m = program.selected("sentinel")[0]
            sentinel = program.run_row(sentinel_case, sentinel_m, 20260718)
            result["numerical_sentinel"] = {"case": sentinel_case[0], "m": sentinel_m, "row": sentinel, "pass": bool(sentinel["pass"])}
            if not sentinel["pass"]:
                raise RuntimeError("numerical sentinel failed")
            for case in (entry[0] for entry in program.selected("sweep")[::4]):
                prepared = program.make_case(case, 20260718)
                for m in MS:
                    result["rows"].append(program.run_row(case, m, 20260718, prepared))
                del prepared
                program.torch.cuda.empty_cache()
            result["tensor_parallel_context"] = tp
        result["all_actual_consumers_pass"] = all(bool(row["pass"]) for row in result["rows"])
        result["aggregation"] = aggregate(result["rows"])
        result["pass"] = bool(result["numerical_sentinel"]["pass"] and result["all_actual_consumers_pass"] and len(result["rows"]) == 12)
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    program.atomic(target, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
