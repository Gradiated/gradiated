#!/usr/bin/env python3
"""Compare two runs that consumed the same open-loop arrival manifest."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any


def bootstrap_mean_ci(values: list[float], seed: int, samples: int = 2000) -> list[float]:
    if not values:
        return [math.nan, math.nan]
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return [means[int(0.025 * samples)], means[int(0.975 * samples)]]


def relative(candidate: float, baseline: float) -> float | None:
    return (candidate / baseline - 1.0) if baseline else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--seed", type=int, default=20260823)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    if baseline["manifest_sha256"] != candidate["manifest_sha256"]:
        raise SystemExit("runs used different manifests and cannot be paired")
    baseline_rows = {row["id"]: row for row in baseline["results"]}
    candidate_rows = {row["id"]: row for row in candidate["results"]}
    if baseline_rows.keys() != candidate_rows.keys():
        raise SystemExit("runs contain different request IDs")

    paired: dict[str, Any] = {}
    usable_ids = [
        request_id
        for request_id in baseline_rows
        if not baseline_rows[request_id]["error"] and not candidate_rows[request_id]["error"]
    ]
    for metric in ("queue_ms", "ttft_ms", "tpot_ms", "request_ms", "client_total_ms"):
        deltas = [
            float(candidate_rows[request_id][metric])
            - float(baseline_rows[request_id][metric])
            for request_id in usable_ids
        ]
        paired[metric] = {
            "mean_delta": round(statistics.fmean(deltas), 4) if deltas else math.nan,
            "median_delta": round(statistics.median(deltas), 4) if deltas else math.nan,
            "mean_delta_95ci": [round(value, 4) for value in bootstrap_mean_ci(deltas, args.seed)],
        }
    exact = sum(
        baseline_rows[request_id]["output_ids"]
        == candidate_rows[request_id]["output_ids"]
        for request_id in usable_ids
    )
    baseline_summary = baseline["summary"]
    candidate_summary = candidate["summary"]
    report = {
        "paired_requests": len(usable_ids),
        "exact_output_matches": exact,
        "exact_output_match_rate": exact / len(usable_ids) if usable_ids else None,
        "aggregate_output_tps_relative": relative(
            candidate_summary["aggregate_output_tps"], baseline_summary["aggregate_output_tps"]
        ),
        "slo_output_tps_relative": relative(
            candidate_summary["slo_output_tps"], baseline_summary["slo_output_tps"]
        ),
        "slo_request_ratio_delta": (
            candidate_summary["slo_request_ratio"] - baseline_summary["slo_request_ratio"]
        ),
        "compute_recovery_delta": (
            candidate_summary["economics"]["compute_recovery"]
            - baseline_summary["economics"]["compute_recovery"]
        ),
        "slo_compute_recovery_delta": (
            candidate_summary["economics"]["slo_compute_recovery"]
            - baseline_summary["economics"]["slo_compute_recovery"]
        ),
        "slo_margin_per_hour_delta": (
            candidate_summary["economics"]["slo_margin_per_hour"]
            - baseline_summary["economics"]["slo_margin_per_hour"]
        ),
        "paired_latency": paired,
    }
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
