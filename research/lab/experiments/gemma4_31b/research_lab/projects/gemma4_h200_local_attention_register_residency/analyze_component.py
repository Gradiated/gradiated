#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
from typing import Any


REQUIRED_METRICS = (
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
    "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active",
    "sm__warps_active.avg.pct_of_peak_sustained_active",
    "profiler__replayer_passes",
)


OPTIONAL_METRICS = (
    "launch__stack_size",
    "l1tex__t_sectors_pipe_lsu_mem_local_op_ld.sum",
    "l1tex__t_sectors_pipe_lsu_mem_local_op_st.sum",
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def parse_metrics(path: pathlib.Path) -> list[dict[str, dict[str, Any]]]:
    rows = list(csv.reader(path.open()))
    parsed_rows: list[dict[str, dict[str, Any]]] = []
    for index, values in enumerate(rows):
        if len(values) <= 4 or values[4] != "_fwd_kernel":
            continue
        header, units = rows[index - 2], rows[index - 1]
        parsed: dict[str, dict[str, Any]] = {}
        for name in (*REQUIRED_METRICS, *OPTIONAL_METRICS):
            if name not in header:
                continue
            column = header.index(name)
            raw = values[column].replace(",", "")
            try:
                value: Any = float(raw)
            except ValueError:
                value = values[column]
            parsed[name] = {"value": value, "unit": units[column] or None}
        missing = [name for name in REQUIRED_METRICS if name not in parsed]
        if missing:
            raise RuntimeError(f"required_ncu_metrics_missing:{missing}")
        parsed_rows.append(parsed)
    if len(parsed_rows) != 2:
        raise RuntimeError(f"expected_two_profiled_fwd_kernels:{len(parsed_rows)}")
    return parsed_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-csv", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-report", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    component = json.loads(args.component_terminal.read_text())
    control_metrics, candidate_metrics = parse_metrics(args.ncu_csv)
    registers = float(candidate_metrics["launch__registers_per_thread"]["value"])
    register_ctas = float(candidate_metrics["launch__occupancy_limit_registers"]["value"])
    shared_ctas = float(candidate_metrics["launch__occupancy_limit_shared_mem"]["value"])
    control_local_loads = float(control_metrics.get("l1tex__t_sectors_pipe_lsu_mem_local_op_ld.sum", {}).get("value", 0.0))
    control_local_stores = float(control_metrics.get("l1tex__t_sectors_pipe_lsu_mem_local_op_st.sum", {}).get("value", 0.0))
    control_stack_size = float(control_metrics.get("launch__stack_size", {}).get("value", 0.0))
    local_loads = float(candidate_metrics.get("l1tex__t_sectors_pipe_lsu_mem_local_op_ld.sum", {}).get("value", 0.0))
    local_stores = float(candidate_metrics.get("l1tex__t_sectors_pipe_lsu_mem_local_op_st.sum", {}).get("value", 0.0))
    stack_size = float(candidate_metrics.get("launch__stack_size", {}).get("value", 0.0))
    residency_pass = (registers <= 128 or register_ctas >= 2) and shared_ctas >= 2
    no_spill_regression = local_loads <= control_local_loads and local_stores <= control_local_stores and stack_size <= control_stack_size
    counter_pass = residency_pass and no_spill_regression
    component_pass = bool(component["component_pass"] and counter_pass)
    output = {
        "schema_version": 1,
        "status": "component_pass" if component_pass else "component_reject",
        "component_pass": component_pass,
        "component_terminal": component,
        "counter_gate": {
            "pass": counter_pass,
            "residency_pass": residency_pass,
            "no_spill_regression": no_spill_regression,
            "registers_per_thread_at_most": 128,
            "or_register_limited_ctas_at_least": 2,
            "shared_memory_ctas_at_least": 2,
            "local_load_sectors": local_loads,
            "local_store_sectors": local_stores,
            "stack_size_bytes": stack_size,
            "control_local_load_sectors": control_local_loads,
            "control_local_store_sectors": control_local_stores,
            "control_stack_size_bytes": control_stack_size,
        },
        "metrics": {"control": control_metrics, "candidate": candidate_metrics},
        "producer": {"ncu_report": str(args.ncu_report), "ncu_report_sha256": sha256(args.ncu_report)},
        "consumer": {"ncu_csv": str(args.ncu_csv), "ncu_csv_sha256": sha256(args.ncu_csv)},
        "promotion": "paired_endpoint" if component_pass else "reject_without_endpoint",
    }
    atomic_json(args.output, output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if component_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
