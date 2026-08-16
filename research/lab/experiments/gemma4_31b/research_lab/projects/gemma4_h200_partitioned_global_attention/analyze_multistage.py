#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
from typing import Any


METRICS = ("Kernel Name", "Block Size", "Grid Size", "gpu__time_duration.sum", "launch__occupancy_limit_registers", "launch__occupancy_limit_shared_mem", "launch__registers_per_thread", "launch__registers_per_thread_allocated", "launch__shared_mem_per_block_dynamic", "launch__shared_mem_per_block", "launch__sm_count", "launch__waves_per_multiprocessor", "dram__throughput.avg.pct_of_peak_sustained_elapsed", "lts__throughput.avg.pct_of_peak_sustained_elapsed", "sm__maximum_warps_avg_per_active_cycle", "sm__maximum_warps_per_active_cycle_pct", "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active", "sm__warps_active.avg.pct_of_peak_sustained_active", "profiler__replayer_passes")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_metrics(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    rows = list(csv.reader(path.open()))
    header_index = next(i for i, row in enumerate(rows) if "Kernel Name" in row)
    header, units = rows[header_index], rows[header_index + 1]
    values = next(row for row in rows[header_index + 2 :] if row and row[0].isdigit())
    parsed: dict[str, dict[str, Any]] = {}
    for name in METRICS:
        column = header.index(name); raw = values[column].replace(",", "")
        try: value: Any = float(raw)
        except ValueError: value = values[column]
        parsed[name] = {"value": value, "unit": units[column] or None}
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-csv", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-report", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    component = json.loads(args.component_terminal.read_text()); metrics = parse_metrics(args.ncu_csv)
    registers = float(metrics["launch__registers_per_thread"]["value"])
    occupancy = float(metrics["sm__warps_active.avg.pct_of_peak_sustained_active"]["value"])
    counter_pass = registers < 255 and occupancy > 12.496527
    mechanism_pass = bool(component["mechanism_pass"] and counter_pass)
    result = {"schema_version": 1, "status": "component_pass" if mechanism_pass else "component_reject", "mechanism_pass": mechanism_pass, "component_terminal": component, "counter_gate": {"pass": counter_pass, "registers_per_thread_below_monolithic_255": registers < 255, "achieved_warp_occupancy_above_monolithic_12_496527_percent": occupancy > 12.496527}, "metrics": metrics, "producer": {"ncu_report": str(args.ncu_report), "ncu_report_sha256": digest(args.ncu_report)}, "consumer": {"ncu_csv": str(args.ncu_csv), "ncu_csv_sha256": digest(args.ncu_csv)}, "promotion": "paired_endpoint" if mechanism_pass else "reject_without_endpoint"}
    temporary = args.output.with_suffix(".part"); temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n"); temporary.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if mechanism_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
