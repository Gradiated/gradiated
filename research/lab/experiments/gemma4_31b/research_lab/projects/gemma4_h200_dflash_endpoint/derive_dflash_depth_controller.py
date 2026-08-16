#!/usr/bin/env python3
"""Derive a conditional c32 DFlash depth controller from persisted telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any


DEPTHS = (4, 8, 12, 16)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def final_meta(path: Path) -> dict[str, Any]:
    result = None
    for line in path.read_text().splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            result = json.loads(line[6:])
    if result is None:
        raise ValueError(f"no SSE data frames: {path}")
    return result["meta_info"]


def expected_emitted(histogram: list[int], depth: int) -> float:
    total = sum(histogram)
    return 1.0 + sum(
        min(accepted, depth - 1) * count
        for accepted, count in enumerate(histogram)
    ) / total


def verifier_scale(depth: int, fixed_fraction: float) -> float:
    return fixed_fraction + (1.0 - fixed_fraction) * depth / 12.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--trace-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    per_request = []
    combined = [0] * 16
    for index in range(4):
        path = args.candidate / f"response-{index:02d}.sse"
        meta = final_meta(path)
        hist = [int(x) for x in meta["spec_accept_histogram"]]
        for accepted, count in enumerate(hist):
            combined[accepted] += count
        per_request.append(
            {
                "request_index": index,
                "response_sha256": sha256(path),
                "verify_cycles": int(meta["spec_verify_ct"]),
                "accepted_drafts": int(meta["spec_accepted_drafts"]),
                "proposed_drafts": int(meta["spec_proposed_drafts"]),
                "accept_histogram": hist,
            }
        )

    trace = json.loads(args.trace_analysis.read_text())
    verify_cycles = int(
        trace["semantic_ranges"]["ngram.target_forward_verify"]["calls"]
    )
    gpu_union_ms_per_cycle = trace["gpu"]["interval_union_us"] / verify_cycles / 1000
    model_event_names = (
        "_fwd_kernel",
        "cutlass::device_kernel",
        "nvjet_sm90",
    )
    model_event_sum_us = sum(
        row["summed_us"]
        for row in trace["gpu"]["top_events_by_summed_time_us"]
        if any(name in row["name"] for name in model_event_names)
    )
    model_event_ms_per_cycle = model_event_sum_us / verify_cycles / 1000
    anchor_ms = median((model_event_ms_per_cycle, gpu_union_ms_per_cycle))

    total_cycles = sum(combined)
    accepted_total = sum(i * count for i, count in enumerate(combined))
    survival = [
        {
            "draft_position": position,
            "survival_probability": sum(combined[position:]) / total_cycles,
        }
        for position in range(1, 16)
    ]
    depth_rows = []
    for depth in DEPTHS:
        depth_rows.append(
            {
                "depth": depth,
                "expected_emitted_tokens_per_verify": expected_emitted(
                    combined, depth
                ),
                "probability_reaching_last_draft_position": sum(
                    combined[depth - 1 :]
                )
                / total_cycles,
                "derived_verifier_cost_ms": {
                    "row_proportional": anchor_ms
                    * verifier_scale(depth, fixed_fraction=0.0),
                    "half_fixed_half_row_proportional": anchor_ms
                    * verifier_scale(depth, fixed_fraction=0.5),
                    "launch_bound": anchor_ms,
                },
            }
        )

    decision_table = []
    for fixed_fraction, cost_model in (
        (0.0, "row_proportional"),
        (0.5, "half_fixed_half_row_proportional"),
        (1.0, "launch_bound"),
    ):
        for draft_ratio in (0.0, 0.25, 0.5, 1.0, 2.0):
            choices = []
            for row in depth_rows:
                scale = verifier_scale(row["depth"], fixed_fraction)
                score = row["expected_emitted_tokens_per_verify"] / (
                    draft_ratio + scale
                )
                choices.append((score, row["depth"]))
            score, depth = max(choices)
            decision_table.append(
                {
                    "verifier_cost_model": cost_model,
                    "fixed_block16_draft_cost_over_m12_verify_cost": draft_ratio,
                    "selected_depth": depth,
                    "normalized_accepted_tokens_per_gpu_time": score,
                }
            )

    output = {
        "schema_version": 1,
        "classification": "conditional_offline_controller",
        "production_authorized": False,
        "telemetry_scope": {
            "survival": (
                "Measured from the semantically rejected four-request DFlash "
                "diagnostic; usable for controller construction, not a quality or "
                "endpoint performance claim."
            ),
            "cost": (
                "Measured H200 c32 fixed-M384 (depth 12) NGRAM trace. The model-"
                "kernel sum and full GPU interval union form a proxy envelope, not "
                "scope-matched DFlash depth measurements."
            ),
        },
        "inputs": {
            "candidate_directory": str(args.candidate),
            "trace_analysis": str(args.trace_analysis),
            "trace_analysis_sha256": sha256(args.trace_analysis),
        },
        "acceptance": {
            "verify_cycles": total_cycles,
            "accepted_drafts": accepted_total,
            "proposed_drafts": sum(row["proposed_drafts"] for row in per_request),
            "combined_accept_histogram": combined,
            "per_request": per_request,
            "per_position_survival": survival,
        },
        "c32_m12_cost_anchor": {
            "fixed_rows": 384,
            "target_verify_calls": verify_cycles,
            "model_event_sum_ms_per_cycle": model_event_ms_per_cycle,
            "full_gpu_interval_union_ms_per_cycle": gpu_union_ms_per_cycle,
            "controller_anchor_midpoint_ms": anchor_ms,
        },
        "depths": depth_rows,
        "controller": {
            "objective": (
                "argmax_M E[1 + min(accepted_drafts, M-1)] / "
                "(fixed_block16_draft_gpu_ms + verifier_gpu_ms[M])"
            ),
            "decision_table": decision_table,
            "provisional_readout": (
                "Depth 8 wins the half-fixed cost model for every tested draft-cost "
                "ratio. Depth 4 wins a row-proportional verifier while draft cost is "
                "below about 0.943 times M12 verify cost; depth 8 wins above it. A "
                "fully launch-bound verifier selects depth 16, but the gain over "
                "depth 12 is only the rare depth-15 survival event."
            ),
            "runtime_guard": (
                "Do not enable adaptation until a lossless oracle run measures "
                "DFlash-specific c32 draft time and verifier costs at all four depths. "
                "Fall back to the deepest measured lossless fixed depth if any oracle "
                "field or request row is missing."
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
