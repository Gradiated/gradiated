#!/usr/bin/env python3
"""Compare matched profiler regions and surface the residual bottleneck transition."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def relative(candidate: float, stock: float) -> float | None:
    return None if stock == 0 else candidate / stock - 1.0


def compare(stock: dict, candidate: dict, phase: str) -> dict:
    left = stock[phase]
    right = candidate[phase]
    stock_families = {row["family"]: float(row["duration_ms"]) for row in left["kernel_families"]}
    candidate_families = {row["family"]: float(row["duration_ms"]) for row in right["kernel_families"]}
    families = []
    for family in sorted(stock_families | candidate_families):
        stock_ms = stock_families.get(family, 0.0)
        candidate_ms = candidate_families.get(family, 0.0)
        families.append({
            "family": family,
            "stock_duration_ms": stock_ms,
            "candidate_duration_ms": candidate_ms,
            "delta_ms": candidate_ms - stock_ms,
            "relative_delta": relative(candidate_ms, stock_ms),
        })
    region_delta = relative(float(right["region_duration_sum_ms"]), float(left["region_duration_sum_ms"]))
    kernel_delta = relative(float(right["kernel_duration_sum_ms"]), float(left["kernel_duration_sum_ms"]))
    diagnosis = "measured_delta_requires_interpretation"
    if kernel_delta is not None and region_delta is not None and kernel_delta <= -0.05 and abs(region_delta) < 0.03:
        diagnosis = "saved_component_work_not_transferred_to_region_span"
    return {
        "schema_version": 1,
        "phase": phase,
        "stock_region_duration_sum_ms": left["region_duration_sum_ms"],
        "candidate_region_duration_sum_ms": right["region_duration_sum_ms"],
        "region_duration_relative_delta": region_delta,
        "stock_kernel_duration_sum_ms": left["kernel_duration_sum_ms"],
        "candidate_kernel_duration_sum_ms": right["kernel_duration_sum_ms"],
        "kernel_duration_relative_delta": kernel_delta,
        "families": families,
        "largest_saved_family": min(families, key=lambda row: row["delta_ms"])["family"],
        "largest_residual_candidate_family": max(families, key=lambda row: row["candidate_duration_ms"])["family"],
        "diagnosis": diagnosis,
        "next_measurement": "measure dependency-union critical path and resource signature of the largest residual family",
        "claim_limit": "annotation spans and summed profiler kernel work are diagnostic; this comparison is not end-to-end wall-time attribution",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stock", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--phase", default="decode")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.stock.read_text()), json.loads(args.candidate.read_text()), args.phase)
    result["stock_sha256"] = hashlib.sha256(args.stock.read_bytes()).hexdigest()
    result["candidate_sha256"] = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
