#!/usr/bin/env python3
"""Collect timestamped multi-model OpenRouter provider-panel snapshots."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

from panel_model import _write_json, collect_panel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("loop", choices=("loop",), nargs="?", default="loop")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".agents/runtime/openrouter-provider-panel"),
    )
    parser.add_argument("--interval-seconds", type=int, default=21_600)
    parser.add_argument("--max-models", type=int, default=30)
    parser.add_argument("--min-endpoints", type=int, default=4)
    parser.add_argument("--max-rank-scan", type=int, default=100)
    parser.add_argument("--share-samples", type=int, default=3)
    parser.add_argument("--request-delay", type=float, default=0.08)
    parser.add_argument("--max-runs", type=int)
    args = parser.parse_args()
    if args.interval_seconds < 900:
        raise SystemExit("panel collection interval must be at least 900 seconds")
    completed = 0
    while True:
        try:
            panel = collect_panel(
                max_models=args.max_models,
                min_endpoints=args.min_endpoints,
                max_rank_scan=args.max_rank_scan,
                share_samples=args.share_samples,
                request_delay=args.request_delay,
            )
            timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            snapshot = args.output_dir / f"panel-{timestamp}.json"
            _write_json(snapshot, panel)
            _write_json(args.output_dir / "latest.json", panel)
            completed += 1
            print(
                json.dumps(
                    {
                        "status": "collected",
                        "models": len(panel["models"]),
                        "rows": sum(len(model["rows"]) for model in panel["models"]),
                        "snapshot": str(snapshot),
                    }
                ),
                flush=True,
            )
        except Exception as error:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_type": type(error).__name__,
                        "message": str(error),
                    }
                ),
                flush=True,
            )
        if args.max_runs is not None and completed >= args.max_runs:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
