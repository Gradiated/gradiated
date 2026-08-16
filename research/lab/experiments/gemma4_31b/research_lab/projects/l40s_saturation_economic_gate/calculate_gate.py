#!/usr/bin/env python3
"""Reproduce the zero-cost L40S economic and conservative-memory gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--memory", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    market = json.loads(args.market.read_text())
    memory = json.loads(args.memory.read_text())
    prices = json.loads(args.prices.read_text())
    mix = market["campaign_mix"]
    targets = {
        name: row["request_cost"]
        for name, row in market["campaign_mix_normalization_usd"].items()
        if isinstance(row, dict) and "request_cost" in row
    }
    targets["AA_7_2_1_blend"] = market["artificial_analysis_methodology_view"][
        "lowest_price_campaign_request_cost_if_blend_applied"
    ]

    accelerators = prices["accelerators"]
    l40s = (accelerators["nvidia-l40s"] if isinstance(accelerators, dict)
            else next(row for row in accelerators if row["id"] == "nvidia-l40s"))
    planning_rate = l40s["production_planning_usd_per_gpu_hour"]
    rate_range = l40s["production_evidence_range_usd_per_gpu_hour"]
    factors = {
        "ideal": {"utilization": 1.0, "replica_headroom": 1.0, "non_gpu": 1.0, "reliability": 1.0, "storage_orchestration": 1.0},
        "planning_base": {"utilization": 0.85, "replica_headroom": 1.10, "non_gpu": 1.05, "reliability": 1.03, "storage_orchestration": 1.03},
        "conservative": {"utilization": 0.70, "replica_headroom": 1.25, "non_gpu": 1.15, "reliability": 1.05, "storage_orchestration": 1.08},
    }

    def required_rps(rate: float, hurdle: float, scenario: dict) -> float:
        multiplier = (scenario["replica_headroom"] * scenario["non_gpu"] *
                      scenario["reliability"] * scenario["storage_orchestration"] /
                      scenario["utilization"])
        return rate / 3600.0 / hurdle * multiplier

    economic_surface = {}
    for scenario_name, scenario in factors.items():
        economic_surface[scenario_name] = {
            target: {
                "required_completed_requests_per_second": {
                    "planning": required_rps(planning_rate, hurdle, scenario),
                    "production_range": [required_rps(rate, hurdle, scenario) for rate in rate_range],
                },
                "required_prompt_tokens_per_second": {
                    "planning": required_rps(planning_rate, hurdle, scenario) * mix["prompt_tokens"],
                    "production_range": [required_rps(rate, hurdle, scenario) * mix["prompt_tokens"] for rate in rate_range],
                },
                "required_output_tokens_per_second": {
                    "planning": required_rps(planning_rate, hurdle, scenario) * mix["output_tokens"],
                    "production_range": [required_rps(rate, hurdle, scenario) * mix["output_tokens"] for rate in rate_range],
                },
                "required_total_tokens_per_second": {
                    "planning": required_rps(planning_rate, hurdle, scenario) * mix["total_tokens"],
                    "production_range": [required_rps(rate, hurdle, scenario) * mix["total_tokens"] for rate in rate_range],
                },
            }
            for target, hurdle in targets.items()
        }

    bound = memory["steady_state_bound"]
    capacity = bound["l40s_capacity_gib_assumed"]
    weights = bound["weights_and_scales_gib_conservative"]
    runtime = bound["runtime_reservation_gib"]
    kv = {"c1": bound["kv_primary_4214_tokens_gib"], "c2": bound["kv_primary_4214_tokens_gib"] * 2,
          "c4": bound["kv_primary_4214_tokens_gib"] * 4, "c8": bound["kv_primary_4214_tokens_gib"] * 8,
          "c16": bound["kv_primary_4214_tokens_gib"] * 16}
    memory_surface = {}
    for label, kv_gib in kv.items():
        total = weights + runtime + kv_gib
        memory_surface[label] = {"primary_kv_gib": kv_gib, "total_gib": total,
                                 "headroom_gib": capacity - total, "guaranteed_fit": total <= capacity}
    single_10k = weights + runtime + bound["kv_10k_tokens_gib"]

    # The latency figures are sensitivities, not acceptance SLOs: Little's law gives C / throughput.
    planning = economic_surface["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"]
    latency_sensitivity = {
        f"c{c}": {"p50_completion_time_ceiling_seconds": c / planning,
                   "p95_completion_time_ceiling_seconds": c / planning}
        for c in (1, 2, 4, 8, 16)
    }

    result = {
        "schema_version": 1,
        "evidence_type": "derived_decision_surface_from_content_addressed_inputs",
        "inputs": {"market": {"path": str(args.market), "sha256": sha256(args.market)},
                   "memory": {"path": str(args.memory), "sha256": sha256(args.memory)},
                   "prices": {"path": str(args.prices), "sha256": sha256(args.prices)}},
        "target_costs_usd_per_request": targets,
        "planning_rate_usd_per_gpu_hour": planning_rate,
        "production_rate_range_usd_per_gpu_hour": rate_range,
        "scenario_factors": factors,
        "economic_surface": economic_surface,
        "memory_bound": {"capacity_gib": capacity, "weights_and_scales_gib": weights,
                         "runtime_reservation_gib": runtime, "primary_kv_gib_by_concurrency": kv,
                         "surface": memory_surface, "single_10k_total_gib": single_10k,
                         "single_10k_headroom_gib": capacity - single_10k},
        "latency_sensitivity": {"basis": "Little's law, C / required planning-base request rate for DeepInfra hurdle; p50/p95 are sensitivities only", "values": latency_sensitivity},
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
