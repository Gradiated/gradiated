#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
from typing import Any


METRICS = (
    "Kernel Name",
    "Block Size",
    "Grid Size",
    "gpu__time_duration.sum",
    "launch__occupancy_limit_registers",
    "launch__occupancy_limit_shared_mem",
    "launch__registers_per_thread",
    "launch__registers_per_thread_allocated",
    "launch__shared_mem_per_block_dynamic",
    "launch__shared_mem_per_block",
    "launch__sm_count",
    "launch__waves_per_multiprocessor",
    "dram__throughput.avg.pct_of_peak_sustained_elapsed",
    "lts__throughput.avg.pct_of_peak_sustained_elapsed",
    "sm__maximum_warps_avg_per_active_cycle",
    "sm__maximum_warps_per_active_cycle_pct",
    "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active",
    "sm__warps_active.avg.pct_of_peak_sustained_active",
    "profiler__replayer_passes",
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def parse_metrics(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    rows = list(csv.reader(path.open()))
    index = next(i for i, row in enumerate(rows) if len(row) > 4 and row[4] == "_fwd_kernel")
    header, units, values = rows[index - 2], rows[index - 1], rows[index]
    parsed = {}
    for name in METRICS:
        column = header.index(name)
        raw = values[column].replace(",", "")
        try:
            value: Any = float(raw)
        except ValueError:
            value = values[column]
        parsed[name] = {"value": value, "unit": units[column] or None}
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-csv", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-report", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    component = json.loads(args.component_terminal.read_text())
    metrics = parse_metrics(args.ncu_csv)
    registers = metrics["launch__registers_per_thread"]["value"]
    register_ctas = metrics["launch__occupancy_limit_registers"]["value"]
    shared_ctas = metrics["launch__occupancy_limit_shared_mem"]["value"]
    counter_pass = registers <= 128 and register_ctas >= 2 and shared_ctas >= 2
    mechanism_pass = bool(component["mechanism_pass"] and counter_pass)
    output = {
        "schema_version": 1,
        "status": "component_pass" if mechanism_pass else "component_reject",
        "mechanism_pass": mechanism_pass,
        "component_terminal": component,
        "counter_gate": {
            "pass": counter_pass,
            "registers_per_thread_at_most": 128,
            "register_ctas_at_least": 2,
            "shared_memory_ctas_at_least": 2,
        },
        "metrics": metrics,
        "producer": {
            "ncu_report": str(args.ncu_report),
            "ncu_report_sha256": sha256(args.ncu_report),
        },
        "consumer": {
            "ncu_csv": str(args.ncu_csv),
            "ncu_csv_sha256": sha256(args.ncu_csv),
        },
        "promotion": "paired_endpoint" if mechanism_pass else "reject_without_endpoint",
    }
    atomic_json(args.output, output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if mechanism_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
