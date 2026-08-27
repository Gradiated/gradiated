#!/usr/bin/env python3
"""Run a bounded second-pass KDA architecture exploration."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from kda_sweep import Architecture, KDAWorkload, evaluate, gpu_control


def candidate_architectures() -> list[Architecture]:
    common = {
        "kind": "fpga",
        "fused": True,
        "double_buffered": True,
        "compute_efficiency": 0.70,
        "memory_efficiency": 0.75,
        "vector_lanes": 32,
        "launch_overhead_ns": 0.0,
        "static_power_w": 2.5,
    }
    specs = [
        ("streaming", 128, 250, 32, False, False, 64.0, 16.0),
        ("weights_local", 128, 250, 64, False, True, 64.0, 128.0),
        ("state_local", 256, 200, 128, True, False, 64.0, 256.0),
        ("state_weights_local", 256, 200, 128, True, True, 64.0, 256.0),
        ("larger_state_weights_local", 512, 200, 256, True, True, 64.0, 256.0),
        ("unfused_streaming", 256, 250, 32, False, False, 64.0, 16.0),
    ]
    architectures = []
    for label, macs, clock, sram, local_state, weights_local, external_bw, local_bw in specs:
        architectures.append(
            Architecture(
                name=label,
                mac_units=macs,
                clock_mhz=clock,
                sram_kb=sram,
                local_state=local_state,
                weights_local=weights_local,
                external_bandwidth_gbps=external_bw,
                local_bandwidth_gbps=local_bw,
                **common,
            )
        )
    architectures[-1] = Architecture(
        **{**asdict(architectures[-1]), "fused": False, "double_buffered": False}
    )
    return architectures


def workload_matrix() -> list[KDAWorkload]:
    workloads = []
    for head_dim, state_update_macs, weight_bytes, activation_bytes in itertools.product(
        (64, 128, 256), (1, 2, 4, 8), (0.5, 1.0), (1.0, 2.0)
    ):
        workloads.append(
            KDAWorkload(
                name=f"kda_d{head_dim}_u{state_update_macs}_w{weight_bytes}_a{activation_bytes}",
                head_dim=head_dim,
                state_update_macs=state_update_macs,
                weight_bytes_per_value=weight_bytes,
                activation_bytes_per_value=activation_bytes,
            )
        )
    return workloads


def compact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key
        in {
            "name",
            "kind",
            "model_kind",
            "latency_us",
            "energy_proxy_uj",
            "external_bytes",
            "local_bytes",
            "required_local_bytes",
            "fits_kv260",
            "capacity_ok",
            "resource_ok",
            "fused",
            "local_state",
            "weights_local",
            "double_buffered",
            "mac_units",
            "clock_mhz",
            "external_bandwidth_gbps",
            "local_bandwidth_gbps",
            "sram_kb",
            "logic_cells",
            "dsp_slices",
            "compute_us",
            "vector_us",
            "external_memory_us",
            "local_memory_us",
            "overlap_mode",
        }
    }


def run(output_dir: Path) -> dict[str, Any]:
    architectures = candidate_architectures()
    gpu = gpu_control()
    workloads = workload_matrix()
    rows: list[dict[str, Any]] = []
    for workload in workloads:
        for architecture in [gpu, *architectures]:
            row = compact(evaluate(workload, architecture))
            row["workload"] = asdict(workload)
            rows.append(row)

    by_workload: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_workload[row["workload"]["name"]].append(row)
    rankings = []
    best_counts: dict[str, int] = defaultdict(int)
    for workload_name, workload_rows in by_workload.items():
        gpu_row = next(row for row in workload_rows if row["kind"] == "gpu")
        feasible = [row for row in workload_rows if row["kind"] == "fpga" and row["fits_kv260"]]
        best = min(feasible, key=lambda row: row["latency_us"]) if feasible else None
        if best:
            best_counts[best["name"]] += 1
        rankings.append(
            {
                "workload": workload_name,
                "head_dim": workload_rows[0]["workload"]["head_dim"],
                "state_update_macs_per_element": workload_rows[0]["workload"]["state_update_macs"],
                "feasible_fpga_count": len(feasible),
                "best_fpga": best["name"] if best else None,
                "best_fpga_latency_us": best["latency_us"] if best else None,
                "gpu_control_latency_us": gpu_row["latency_us"],
                "best_fpga_to_gpu_latency_ratio": (
                    best["latency_us"] / gpu_row["latency_us"] if best else None
                ),
            }
        )

    base = KDAWorkload()
    ablation_specs = [
        ("fusion", {"fused": False}, {"fused": True}),
        ("double_buffering", {"double_buffered": False}, {"double_buffered": True}),
        ("local_state_and_weights", {"local_state": False, "weights_local": False}, {"local_state": True, "weights_local": True}),
    ]
    ablations = []
    ablation_base = Architecture(
        name="ablation_base",
        kind="fpga",
        mac_units=256,
        clock_mhz=200,
        external_bandwidth_gbps=64.0,
        local_bandwidth_gbps=256.0,
        sram_kb=256,
        fused=True,
        local_state=False,
        weights_local=False,
        double_buffered=True,
        compute_efficiency=0.70,
        memory_efficiency=0.75,
        vector_lanes=32,
        launch_overhead_ns=0.0,
        static_power_w=2.5,
    )
    for label, left_changes, right_changes in ablation_specs:
        left = Architecture(**{**asdict(ablation_base), "name": f"{label}_off", **left_changes})
        right = Architecture(**{**asdict(ablation_base), "name": f"{label}_on", **right_changes})
        left_row = evaluate(base, left)
        right_row = evaluate(base, right)
        ablations.append(
            {
                "feature": label,
                "off": compact(left_row),
                "on": compact(right_row),
                "latency_change_percent": (right_row["latency_us"] / left_row["latency_us"] - 1.0) * 100.0,
                "external_bytes_change_percent": (right_row["external_bytes"] / left_row["external_bytes"] - 1.0) * 100.0,
            }
        )

    bandwidth_rows = []
    for external_bw in (16.0, 32.0, 64.0, 128.0, 256.0):
        for architecture in architectures[:4]:
            variant = Architecture(**{**asdict(architecture), "external_bandwidth_gbps": external_bw})
            row = compact(evaluate(base, variant))
            row["external_bandwidth_gbps"] = external_bw
            bandwidth_rows.append(row)

    amdahl = []
    for kda_fraction, unit_speedup in itertools.product(
        (0.10, 0.25, 0.50, 0.75), (2.0, 5.0, 10.0, 30.0)
    ):
        amdahl.append(
            {
                "kda_fraction_of_total_time": kda_fraction,
                "kda_unit_speedup": unit_speedup,
                "whole_model_speedup": 1.0 / (1.0 - kda_fraction + kda_fraction / unit_speedup),
                "whole_model_latency_reduction_percent": (
                    1.0 - 1.0 / (1.0 - kda_fraction + kda_fraction / unit_speedup)
                )
                * 100.0,
            }
        )

    result = {
        "experiment": {
            "name": "kimi_k3_kda_second_pass_exploration",
            "evidence_class": "analytical",
            "hypothesis": "fused streaming and persistent KDA state reduce memory and launch cost, but state locality only helps when local bandwidth and capacity justify it",
            "stock_control": "generic GPU control from the first sweep; it is not a B300 or Vera Rubin execution",
            "scope": "one KDA decode head; head dimensions 64/128/256; state-update density 1/2/4/8; INT4/INT8-like weights; 8/16-bit activations",
            "quality_gate": "all rows use the same deterministic workload-count model and only FPGA rows within KV260 proxy limits enter rankings",
            "transfer_limit": "does not establish model quality, full-layer performance, FPGA timing closure, ASIC frequency, or product GPU comparison",
        },
        "architectures": [asdict(architecture) for architecture in architectures],
        "workloads": [asdict(workload) for workload in workloads],
        "rows": rows,
        "rankings": rankings,
        "best_counts": dict(best_counts),
        "ablations": ablations,
        "bandwidth_rows": bandwidth_rows,
        "amdahl": amdahl,
        "opportunities": [
            {
                "id": "persistent_state_sram",
                "observation": "state locality reduces external bytes but adds local traffic and SRAM capacity pressure",
                "evidence_scope": "analytical one-head sweep",
                "competing_explanations": ["local bandwidth is too low", "state update density is too low", "state does not fit in the selected SRAM"],
                "mechanism": "keep the recurrent KDA state on chip across tokens",
                "falsifier": "RTL or KV260 design shows state-local mode slower at matched clock and bandwidth",
                "next_measurement": "state-local versus streamed-state RTL at head dimensions 128 and 256",
                "cost_usd": 0,
                "decision_impact": 0.9,
                "uncertainty": 0.8,
                "discrimination_power": 0.9,
                "readiness": 0.5,
                "transfer_penalty": 0.6,
            },
            {
                "id": "fused_pipeline",
                "observation": "fusion removes intermediate writes and permits overlap",
                "evidence_scope": "analytical ablation",
                "competing_explanations": ["the assumed memory efficiency is optimistic", "the intermediate tensor is already cached"],
                "mechanism": "wire projection, gate, state, and output stages as a streaming pipeline",
                "falsifier": "RTL timing or buffering hazards erase the predicted latency reduction",
                "next_measurement": "cycle-accurate pipeline simulation with backpressure and state feedback",
                "cost_usd": 0,
                "decision_impact": 0.9,
                "uncertainty": 0.6,
                "discrimination_power": 0.8,
                "readiness": 0.7,
                "transfer_penalty": 0.4,
            },
            {
                "id": "mac_array_sizing",
                "observation": "more MACs help only until memory or resource limits dominate",
                "evidence_scope": "analytical candidate ranking",
                "competing_explanations": ["the model underestimates control overhead", "FPGA DSP packing changes the resource curve"],
                "mechanism": "size the reusable GEMV engine for the dominant projection work",
                "falsifier": "larger arrays reduce measured frequency or leave DSPs idle",
                "next_measurement": "sweep 64/128/256/512 MAC RTL blocks with real memory schedules",
                "cost_usd": 0,
                "decision_impact": 0.8,
                "uncertainty": 0.7,
                "discrimination_power": 0.8,
                "readiness": 0.6,
                "transfer_penalty": 0.5,
            },
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "exploration.json").write_text(json.dumps(result, indent=2) + "\n")
    with (output_dir / "exploration_rows.csv").open("w", newline="") as handle:
        fieldnames = ["workload", *sorted(rows[0].keys())]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({"workload": row["workload"]["name"], **row})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the second-pass KDA exploration")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results")
    args = parser.parse_args()
    result = run(args.output_dir)
    print(f"workloads={len(result['workloads'])}")
    print(f"architectures={len(result['architectures'])}")
    print(f"rows={len(result['rows'])}")
    print("best_counts=" + json.dumps(result["best_counts"], sort_keys=True))
    for ablation in result["ablations"]:
        print(
            f"ablation={ablation['feature']} latency_change_percent="
            f"{ablation['latency_change_percent']:.2f} external_bytes_change_percent="
            f"{ablation['external_bytes_change_percent']:.2f}"
        )


if __name__ == "__main__":
    main()
