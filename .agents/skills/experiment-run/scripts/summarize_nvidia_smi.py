#!/usr/bin/env python3
"""Summarize standard one-second nvidia-smi CSV telemetry by recorded phase."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import statistics
from pathlib import Path


COLUMNS = (
    "timestamp",
    "uuid",
    "name",
    "pstate",
    "gpu_util_pct",
    "memory_util_pct",
    "memory_used_mib",
    "memory_total_mib",
    "power_draw_w",
    "power_limit_w",
    "temperature_c",
    "sm_clock_mhz",
    "memory_clock_mhz",
)
NUMERIC = COLUMNS[4:]


def timestamp(value: str) -> dt.datetime:
    value = value.strip().replace("Z", "+00:00")
    for pattern in (None, "%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            result = dt.datetime.fromisoformat(value) if pattern is None else dt.datetime.strptime(value, pattern)
            return result.replace(tzinfo=result.tzinfo or dt.timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"unsupported timestamp {value!r}")


def quantile(values: list[float], fraction: float) -> float:
    rows = sorted(values)
    return rows[max(0, min(len(rows) - 1, math.ceil(fraction * len(rows)) - 1))]


def read_samples(path: Path, timestamp_offset_hours: float = 0.0) -> list[dict]:
    samples = []
    with path.open(newline="") as handle:
        for values in csv.reader(handle):
            if len(values) != len(COLUMNS):
                raise ValueError(f"expected {len(COLUMNS)} columns, observed {len(values)}")
            row = {key: value.strip() for key, value in zip(COLUMNS, values, strict=True)}
            row["parsed_timestamp"] = timestamp(row["timestamp"]) + dt.timedelta(
                hours=timestamp_offset_hours
            )
            for key in NUMERIC:
                row[key] = float(row[key])
            samples.append(row)
    return samples


def read_intervals(path: Path) -> list[tuple[str, dt.datetime, dt.datetime]]:
    opens: dict[str, dt.datetime] = {}
    intervals = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        phase = row["phase"]
        when = timestamp(row["timestamp"])
        if row["state"] == "begin":
            opens[phase] = when
        elif row["state"] == "complete" and phase in opens:
            intervals.append((phase, opens.pop(phase), when))
    return intervals


def summarize(samples: list[dict], intervals: list[tuple[str, dt.datetime, dt.datetime]]) -> dict:
    result = {"schema_version": 1, "sample_count": len(samples), "phases": {}}
    for phase, start, end in intervals:
        selected = [row for row in samples if start <= row["parsed_timestamp"] <= end]
        selected.sort(key=lambda row: row["parsed_timestamp"])
        metrics = {}
        for key in NUMERIC:
            values = [row[key] for row in selected]
            metrics[key] = None if not values else {
                "mean": statistics.fmean(values),
                "p50": quantile(values, 0.50),
                "p95": quantile(values, 0.95),
                "max": max(values),
            }
        gaps = [
            (right["parsed_timestamp"] - left["parsed_timestamp"]).total_seconds()
            for left, right in zip(selected, selected[1:])
        ]
        energy_joules = sum(
            (left["power_draw_w"] + right["power_draw_w"]) / 2 * gap
            for left, right, gap in zip(selected, selected[1:], gaps)
        )
        duration_seconds = max(0.0, (end - start).total_seconds())
        expected_samples = math.floor(duration_seconds) + 1
        result["phases"][phase] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_seconds": duration_seconds,
            "sample_count": len(selected),
            "sampling": {
                "expected_samples_at_1hz": expected_samples,
                "coverage_fraction_at_1hz": min(1.0, len(selected) / expected_samples) if expected_samples else 0.0,
                "max_gap_seconds": max(gaps) if gaps else None,
                "gaps_over_2_seconds": sum(gap > 2.0 for gap in gaps),
            },
            "energy_joules_trapezoidal": energy_joules,
            "metrics": metrics,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("telemetry", type=Path)
    parser.add_argument("phases", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--timestamp-offset-hours",
        type=float,
        default=0.0,
        help="add this offset to telemetry timestamps before phase matching",
    )
    args = parser.parse_args()
    result = summarize(
        read_samples(args.telemetry, args.timestamp_offset_hours), read_intervals(args.phases)
    )
    result["telemetry_timestamp_offset_hours"] = args.timestamp_offset_hours
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
