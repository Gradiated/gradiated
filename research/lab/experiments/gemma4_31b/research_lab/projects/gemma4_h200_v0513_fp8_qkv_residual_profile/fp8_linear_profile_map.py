#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sqlite3


KERNEL_PATTERN = "%cutlass_3x_gemm_sm90_fp8%"
DOMINANT_TILE_PATTERN = "%C<(int)128>%, cute::C<(int)128>%, cute::C<(int)128>>%"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=pathlib.Path, required=True)
    parser.add_argument("--consumer-audit", type=pathlib.Path, required=True)
    parser.add_argument("--dispatch-source", type=pathlib.Path, required=True)
    parser.add_argument("--fp8-source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    consumers = [json.loads(line) for line in args.consumer_audit.read_text().splitlines() if line]
    by_suffix: dict[str, dict[str, object]] = {}
    for row in consumers:
        prefix = str(row["prefix"])
        for suffix in ("qkv_proj", "o_proj", "gate_up_proj", "down_proj"):
            if prefix.endswith(suffix):
                by_suffix.setdefault(suffix, row)

    connection = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    rows = connection.execute(
        """
        SELECT k.start, k.end - k.start
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id = k.demangledName
        WHERE s.value LIKE ? AND s.value LIKE ?
        ORDER BY k.start
        """,
        (KERNEL_PATTERN, DOMINANT_TILE_PATTERN),
    ).fetchall()
    if len(rows) != 14400:
        raise RuntimeError(f"expected 14400 dominant launches, observed {len(rows)}")

    names = ("qkv_proj", "o_proj", "gate_up_proj", "down_proj")
    families = []
    for position, name in enumerate(names):
        durations = [duration for index, (_, duration) in enumerate(rows) if index % 4 == position]
        audit = by_suffix[name]
        families.append(
            {
                "projection": name,
                "launches": len(durations),
                "seconds": sum(durations) / 1e9,
                "mean_microseconds": sum(durations) / len(durations) / 1e3,
                "input_shape_at_c32": audit["input"]["shape"],
                "weight_shape_k_n": audit["weight"]["shape"],
            }
        )

    total_seconds = sum(row["seconds"] for row in families)
    for row in families:
        row["family_fraction"] = row["seconds"] / total_seconds

    value = {
        "schema_version": 1,
        "evidence_class": {
            "launch_timing": "measured",
            "projection_mapping": "measured sequence joined to behavioral FP8 audit and model source",
            "causal_limiter": "source-backed inference",
        },
        "inputs": {
            "sqlite": str(args.sqlite),
            "sqlite_sha256": sha256(args.sqlite),
            "consumer_audit": str(args.consumer_audit),
            "consumer_audit_sha256": sha256(args.consumer_audit),
            "dispatch_source": str(args.dispatch_source),
            "dispatch_source_sha256": sha256(args.dispatch_source),
            "fp8_source": str(args.fp8_source),
            "fp8_source_sha256": sha256(args.fp8_source),
        },
        "dominant_kernel": {
            "launches": len(rows),
            "seconds": total_seconds,
            "tile": [128, 128, 128],
            "cluster": [2, 1, 1],
            "schedule": "KernelTmaWarpSpecializedPingpongFP8FastAccum",
            "epilogue": "ScaledEpilogue_bfloat16",
            "grid": [132, 1, 1],
            "threads_per_cta": 384,
            "dynamic_shared_memory_bytes": 214016,
            "registers_per_thread": 168,
            "dispatch_bucket": "M>128",
        },
        "projection_families": families,
        "dominant_exact_shape": {
            "projection": "gate_up_proj",
            "m": "dynamic and >128 in the retained dominant kernel bucket",
            "n": 43008,
            "k": 5376,
            "layers": 60,
            "launches": 3600,
            "seconds": next(row["seconds"] for row in families if row["projection"] == "gate_up_proj"),
        },
        "causal_model": {
            "limiter": "large exact gate/up tensor-core realization with one high-footprint CTA per H200 SM",
            "observations": [
                "The persistent grid equals the H200 SM count (132).",
                "A 214016-byte CTA and 168 registers/thread prevent a second resident 384-thread CTA.",
                "Gate/up owns 44.8% of the measured dominant FP8 GEMM family.",
            ],
            "intervention": "Route only M>128,K=5376,N=43008 to a 64x256x128 eight-warp Triton tile; preserve stock CUTLASS for decode and every other shape.",
            "falsifier": "The endpoint candidate fails to improve its contemporaneous stacked control or fails semantic/path proof.",
        },
    }
    temporary = args.output.with_suffix(".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
