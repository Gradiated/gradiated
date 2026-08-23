#!/usr/bin/env python3
"""Summarize an arrival-rate sweep and identify the SLO-qualified economic knee."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--minimum-slo-request-ratio", type=float, default=0.99)
    parser.add_argument("--maximum-dispatch-p99-ms", type=float, default=10.0)
    args = parser.parse_args()
    rows = []
    for path in args.results:
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload["summary"]
        row = {
            "path": str(path),
            "offered_rps": summary["offered_rps_realized"],
            "completed_rps": summary["completed_rps"],
            "output_tps": summary["aggregate_output_tps"],
            "slo_output_tps": summary["slo_output_tps"],
            "slo_request_ratio": summary["slo_request_ratio"],
            "ttft_p50_ms": summary["ttft_ms"]["p50"],
            "ttft_p99_ms": summary["ttft_ms"]["p99"],
            "tpot_p99_ms": summary["tpot_ms"]["p99"],
            "request_p99_ms": summary["request_ms"]["p99"],
            "dispatch_p99_ms": summary["client_dispatch_ms"]["p99"],
            "cache_ratio": summary["cache_ratio"],
            "compute_recovery": summary["economics"]["compute_recovery"],
            "slo_compute_recovery": summary["economics"]["slo_compute_recovery"],
            "slo_margin_per_hour": summary["economics"]["slo_margin_per_hour"],
        }
        row["qualifies"] = (
            row["slo_request_ratio"] >= args.minimum_slo_request_ratio
            and row["dispatch_p99_ms"] <= args.maximum_dispatch_p99_ms
        )
        rows.append(row)
    rows.sort(key=lambda row: row["offered_rps"])
    qualified = [row for row in rows if row["qualifies"]]
    best = max(qualified, key=lambda row: row["slo_margin_per_hour"], default=None)
    print(
        json.dumps(
            {
                "minimum_slo_request_ratio": args.minimum_slo_request_ratio,
                "maximum_dispatch_p99_ms": args.maximum_dispatch_p99_ms,
                "best_qualified": best,
                "points": rows,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if qualified else 1


if __name__ == "__main__":
    raise SystemExit(main())
