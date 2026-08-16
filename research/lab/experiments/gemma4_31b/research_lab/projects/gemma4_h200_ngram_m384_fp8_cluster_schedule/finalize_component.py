#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import statistics


ROOT = pathlib.Path("/home/glmrunner/gemma4-h200-ngram-m384-cluster")
ARTIFACTS = ROOT / "artifacts"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    audit = ARTIFACTS / "COMPONENT_AUDIT_PERSISTED.jsonl"
    rows = [json.loads(line) for line in audit.read_text().splitlines() if line.strip()]
    paths = [row for row in rows if row["phase"] == "production_candidate_path"]
    measurements = [row for row in rows if row["phase"] == "exact_real_weight_component"]
    shapes = sorted({tuple(row["shape_mnk"]) for row in measurements})
    families = sorted({row["family"] for row in measurements})
    expected_shapes = {
        (384, 16384, 5376),
        (384, 5376, 8192),
        (384, 43008, 5376),
        (384, 5376, 21504),
        (384, 20480, 5376),
        (384, 5376, 16384),
    }
    coverage_pass = set(shapes) == expected_shapes
    numerical_pass = coverage_pass and all(
        row["projection"]["bitwise_equal"]
        and row["projection"]["candidate_nonfinite"] == 0
        and row["projection"]["reference_nonfinite"] == 0
        for row in measurements
    )
    stock_total = sum(row["stock"]["median_us"] for row in measurements)
    candidate_total = sum(row["candidate"]["median_us"] for row in measurements)
    component_speedup = 1 - candidate_total / stock_total
    terminal = {
        "schema_version": 1,
        "kind": "exact_real_weight_m384_component",
        "classification": "scientific_terminal",
        "result": "candidate_correctness_and_performance_failure",
        "exact_live_m384_verified": bool(paths),
        "candidate_path_rows": len(paths),
        "component_rows": measurements,
        "families": families,
        "shapes_mnk": shapes,
        "expected_shape_coverage_pass": coverage_pass,
        "numerical_pass": numerical_pass,
        "component_speedup_fraction": component_speedup,
        "stock_sum_of_shape_medians_us": stock_total,
        "candidate_sum_of_shape_medians_us": candidate_total,
        "median_family_speedup_fraction": statistics.median(
            row["candidate_speedup_fraction"] for row in measurements
        ),
        "grid_cta_reduction_fraction_by_shape": {
            "x".join(map(str, row["shape_mnk"])): 1
            - row["candidate_grid_ctas"] / row["stock_grid_ctas"]
            for row in paths
        },
        "candidate_build_sha256": sha256(ARTIFACTS / "BUILD.json"),
        "compiler_log_sha256": sha256(ARTIFACTS / "build.stdout"),
        "raw_component_audit_sha256": sha256(audit),
        "partial_server_stdout": {
            "remote_path": str(ARTIFACTS / "component.server.partial.stdout"),
            "bytes": (ARTIFACTS / "component.server.partial.stdout").stat().st_size,
            "sha256": sha256(ARTIFACTS / "component.server.partial.stdout"),
        },
        "component_pass": False,
        "endpoint_admitted": False,
        "endpoint_executed": False,
        "interpretation": "The N-oriented cluster removes the modeled 25% padded CTA count at every observed shape but is unsupported/incorrect in this production CUTLASS instantiation: outputs diverge or become nonfinite, SM90 architecture guards fire, and latency regresses by orders of magnitude.",
    }
    atomic(ARTIFACTS / "COMPONENT_TERMINAL.json", terminal)
    atomic(
        ARTIFACTS / "FINAL_TERMINAL.json",
        {
            "schema_version": 1,
            "classification": "scientific_terminal",
            "result": terminal["result"],
            "component": terminal,
            "endpoint_executed": False,
            "control_replayed": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
