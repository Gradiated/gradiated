#!/usr/bin/env python3
"""Validate that a vLLM PyTorch trace captured the intended fixed c8 decode geometry."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


def grouped_mla_summary(events: list[dict]) -> dict:
    kernels = [
        event
        for event in events
        if event.get("cat") == "kernel"
        and event.get("ph") == "X"
        and "_fwd_grouped_kernel_stage1" in event.get("name", "")
    ]
    grids = Counter(tuple(event.get("args", {}).get("grid", ())) for event in kernels)
    c8 = [event for event in kernels if event.get("args", {}).get("grid", [None])[0] == 8]
    return {
        "kernel_count": len(kernels),
        "grid_counts": [{"grid": list(grid), "count": count} for grid, count in grids.most_common()],
        "c8_grid_kernel_count": len(c8),
        "c8_grid_fraction": len(c8) / len(kernels) if kernels else 0.0,
        "c8_resource_signatures": sorted(
            {
                (
                    event.get("args", {}).get("registers per thread"),
                    event.get("args", {}).get("shared memory"),
                    tuple(event.get("args", {}).get("block", ())),
                )
                for event in c8
            },
            key=str,
        ),
        "duration_sum_us_diagnostic_only": sum(float(event.get("dur", 0)) for event in c8),
    }


def validate(admission: dict, events: list[dict]) -> dict:
    summary = grouped_mla_summary(events)
    geometry = bool(
        admission.get("profile_scope") == "fixed_8k_128_c8"
        and admission.get("concurrency") == 8
        and admission.get("requests") == 8
        and admission.get("exact_geometry_pass") is True
    )
    trace_grid = summary["c8_grid_kernel_count"] > 0 and summary["c8_grid_fraction"] >= 0.95
    return {
        "schema_version": 1,
        "capture_geometry_pass": geometry,
        "trace_c8_grid_pass": trace_grid,
        "pass": geometry and trace_grid,
        "grouped_mla": summary,
        "claim_limit": "grid/resource validation only; summed kernel durations are diagnostic and are not phase-scoped wall-time or an Amdahl coefficient",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("admission", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with gzip.open(args.trace, "rt") as handle:
        trace = json.load(handle)
    admission = json.loads(args.admission.read_text())
    result = validate(admission, trace["traceEvents"])
    result["trace_sha256"] = hashlib.sha256(args.trace.read_bytes()).hexdigest()
    result["admission_sha256"] = hashlib.sha256(args.admission.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
