from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def number(value: str) -> float:
    return float(value.replace(",", "").replace(" ", ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-result", type=Path, required=True)
    parser.add_argument("--ncu-csv", type=Path, required=True)
    parser.add_argument("--ncu-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.component_result.read_text())
    lines = args.ncu_csv.read_text().splitlines()
    header_index = next(
        index for index, line in enumerate(lines) if line.startswith('"ID",')
    )
    rows = list(csv.DictReader(lines[header_index:]))
    counters: dict[str, dict[str, float]] = {"control": {}, "candidate": {}}
    for row in rows:
        kernel = row.get("Kernel Name", "")
        route = (
            "candidate"
            if "_int4_grouped_stage1" in kernel
            else "control"
            if "_fwd_grouped_kernel_stage1" in kernel
            else None
        )
        if route is None:
            continue
        metric = row.get("Metric Name", "")
        if metric in {"dram__sectors_read.sum", "lts__t_sectors_op_read.sum"}:
            counters[route][metric] = counters[route].get(metric, 0.0) + number(
                row["Metric Value"]
            )
        for wide_metric in (
            "dram__sectors_read.sum",
            "lts__t_sectors_op_read.sum",
        ):
            if row.get(wide_metric):
                counters[route][wide_metric] = counters[route].get(
                    wide_metric, 0.0
                ) + number(row[wide_metric])
    required = "dram__sectors_read.sum"
    if required not in counters["control"] or required not in counters["candidate"]:
        raise RuntimeError(f"missing_required_dram_sector_counter:{counters}")
    dram_reduction = 1.0 - counters["candidate"][required] / counters["control"][required]
    numerics = result["numerics"]["candidate_vs_bf16"]
    numerical_pass = bool(
        numerics["finite"]
        and numerics["relative_l2"] <= 0.05
        and numerics["cosine"] >= 0.995
        and numerics["nonfinite_count"] == 0
    )
    semantic_pass = bool(
        result["producer"]["negative_slot_noop"]
        and result["producer"]["multi_token_append"]
        and result["routing"]["pass"]
        and result["routing"]["local_candidate_layers"] == 50
        and result["routing"]["global_unchanged_e5m2_layers"] == 10
    )
    physical_pass = dram_reduction >= 0.35
    bound_pass = (
        result["timing"]["conservative_whole_request_bound_fraction"] >= 0.03
    )
    gate_pass = numerical_pass and semantic_pass and physical_pass and bound_pass
    result["profile_pending"] = False
    result["profile"] = {
        "ncu_report": str(args.ncu_report),
        "counters": counters,
        "local_kv_dram_sector_reduction_fraction": dram_reduction,
        "required_reduction_fraction": 0.35,
    }
    result["gates"] = {
        "numerical_pass": numerical_pass,
        "semantic_and_routing_pass": semantic_pass,
        "physical_pass": physical_pass,
        "whole_request_bound_pass": bound_pass,
        "component_pass": gate_pass,
    }
    atomic_json(args.output, result)
    terminal = {
        "schema_version": 1,
        "stage": "component",
        "scientific_terminal": True,
        "candidate_invocations": 1,
        "producer_invocations": 1,
        "actual_paged_triton_consumer_executed": True,
        "component_pass": gate_pass,
        "numerical_pass": numerical_pass,
        "semantic_and_routing_pass": semantic_pass,
        "physical_pass": physical_pass,
        "whole_request_bound_pass": bound_pass,
        "local_kv_dram_sector_reduction_fraction": dram_reduction,
        "conservative_whole_request_bound_fraction": result["timing"][
            "conservative_whole_request_bound_fraction"
        ],
        "conditional_endpoint_invoked": False,
        "decision": (
            "promote_to_one_exact_c32_pair"
            if gate_pass
            else "close_on_component_gate"
        ),
    }
    atomic_json(args.output.parent / "COMPONENT_TERMINAL.json", terminal)
    invocation_path = args.output.parent / "INVOCATION_STATE.json"
    invocation = json.loads(invocation_path.read_text())
    invocation["scientific_terminal_recorded"] = True
    atomic_json(invocation_path, invocation)
    return 0 if gate_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
