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
KERNELS = ("_fwd_kernel", "_qk_softmax_stage", "_value_stage")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def parse_value(raw: str) -> Any:
    normalized = raw.replace(",", "")
    try:
        return float(normalized)
    except ValueError:
        return raw


def parsed_metric_row(
    header: list[str], units: list[str], values: list[str]
) -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    for name in (*REQUIRED_METRICS, *OPTIONAL_METRICS):
        if name not in header:
            continue
        column = header.index(name)
        parsed[name] = {
            "value": parse_value(values[column]),
            "unit": units[column] or None,
        }
    missing = [name for name in REQUIRED_METRICS if name not in parsed]
    if missing:
        raise RuntimeError(f"required_ncu_metrics_missing:{missing}")
    return parsed


def parse_metrics(path: pathlib.Path) -> dict[str, dict[str, dict[str, Any]]]:
    rows = list(csv.reader(path.open()))
    header_index = next(
        index
        for index, row in enumerate(rows)
        if "Kernel Name" in row and "ID" in row
    )
    header = rows[header_index]
    units = rows[header_index + 1]
    kernel_column = header.index("Kernel Name")
    parsed: dict[str, dict[str, dict[str, Any]]] = {}
    for values in rows[header_index + 2 :]:
        if len(values) != len(header):
            continue
        observed = values[kernel_column]
        match = next((name for name in KERNELS if name in observed), None)
        if match is None:
            continue
        if match in parsed:
            raise RuntimeError(f"duplicate_profiled_kernel:{match}")
        parsed[match] = parsed_metric_row(header, units, values)
    missing = [name for name in KERNELS if name not in parsed]
    if missing:
        raise RuntimeError(f"missing_profiled_kernels:{missing}")
    return parsed


def numeric(
    metrics: dict[str, dict[str, Any]], name: str, default: float = 0.0
) -> float:
    return float(metrics.get(name, {}).get("value", default))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-csv", type=pathlib.Path, required=True)
    parser.add_argument("--ncu-report", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    component = json.loads(args.component_terminal.read_text())
    metrics = parse_metrics(args.ncu_csv)
    control = metrics["_fwd_kernel"]
    stages = {
        name: metrics[name] for name in ("_qk_softmax_stage", "_value_stage")
    }

    stage_gates: dict[str, dict[str, Any]] = {}
    for name, row in stages.items():
        registers = numeric(row, "launch__registers_per_thread")
        register_ctas = numeric(row, "launch__occupancy_limit_registers")
        shared_ctas = numeric(row, "launch__occupancy_limit_shared_mem")
        stage_gates[name] = {
            "pass": (registers <= 128 or register_ctas >= 2) and shared_ctas >= 2,
            "registers_per_thread": registers,
            "register_limited_ctas": register_ctas,
            "shared_memory_limited_ctas": shared_ctas,
            "local_load_sectors": numeric(
                row, "l1tex__t_sectors_pipe_lsu_mem_local_op_ld.sum"
            ),
            "local_store_sectors": numeric(
                row, "l1tex__t_sectors_pipe_lsu_mem_local_op_st.sum"
            ),
            "stack_size_bytes": numeric(row, "launch__stack_size"),
        }

    control_loads = numeric(
        control, "l1tex__t_sectors_pipe_lsu_mem_local_op_ld.sum"
    )
    control_stores = numeric(
        control, "l1tex__t_sectors_pipe_lsu_mem_local_op_st.sum"
    )
    candidate_loads = sum(
        row["local_load_sectors"] for row in stage_gates.values()
    )
    candidate_stores = sum(
        row["local_store_sectors"] for row in stage_gates.values()
    )
    no_spill_regression = (
        candidate_loads <= control_loads
        and candidate_stores <= control_stores
        and all(
            row["stack_size_bytes"] <= numeric(control, "launch__stack_size")
            for row in stage_gates.values()
        )
    )
    physical_pass = all(row["pass"] for row in stage_gates.values())
    counter_pass = physical_pass and no_spill_regression
    component_pass = bool(component["component_pass"] and counter_pass)
    output = {
        "schema_version": 2,
        "status": "component_pass" if component_pass else "component_reject",
        "component_pass": component_pass,
        "component_terminal": component,
        "counter_gate": {
            "pass": counter_pass,
            "physical_pass": physical_pass,
            "no_spill_regression": no_spill_regression,
            "stages": stage_gates,
            "control_local_load_sectors": control_loads,
            "control_local_store_sectors": control_stores,
            "candidate_local_load_sectors_sum": candidate_loads,
            "candidate_local_store_sectors_sum": candidate_stores,
            "registers_per_thread_at_most_or_register_limited_ctas_at_least": [
                128,
                2,
            ],
            "shared_memory_limited_ctas_at_least": 2,
        },
        "metrics": {
            "control": control,
            "qk_softmax_stage": stages["_qk_softmax_stage"],
            "value_stage": stages["_value_stage"],
        },
        "producer": {
            "ncu_report": str(args.ncu_report),
            "ncu_report_sha256": sha256(args.ncu_report),
        },
        "consumer": {
            "ncu_csv": str(args.ncu_csv),
            "ncu_csv_sha256": sha256(args.ncu_csv),
        },
        "promotion": "paired_endpoint" if component_pass else "reject_without_endpoint",
    }
    atomic_json(args.output, output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if component_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
