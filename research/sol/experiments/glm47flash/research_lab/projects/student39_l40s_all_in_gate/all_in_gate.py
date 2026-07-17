#!/usr/bin/env python3
"""Reproduce the zero-cost L40S ancillary-cost gate from committed inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
REPO = PROJECT.parents[6]
LIFECYCLE = LAB / "projects/student39_l40s_lifecycle_bound/STUDENT39_L40S_LIFECYCLE_BOUND.json"
PRICES = REPO / "research/factory/data/gpu_prices.json"
EXPERIMENT = LAB / "projects/nebius_current_awq_c16_direct/artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/summary.json"
LEDGER = REPO / "research/sol/experiments/glm47flash/campaign_100/CAMPAIGN_LEDGER.jsonl"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_case(lifecycle: dict, hours: float) -> dict:
    return next(
        row
        for row in lifecycle["representative_90pct_utilization_5pct_retry"]
        if row["rate_usd_per_hour"] == 1.1 and row["session_hours"] == hours
    )


def main() -> None:
    lifecycle = json.loads(LIFECYCLE.read_text())
    prices = json.loads(PRICES.read_text())
    experiment = json.loads(EXPERIMENT.read_text())
    l40s = next(item for item in prices["accelerators"] if item["id"] == "nvidia-l40s")
    gpu_rate = l40s["production_planning_usd_per_gpu_hour"]
    caps = {8: 1.113384, 24: 1.145885}
    cases = {}
    for hours, cap in caps.items():
        reference = reference_case(lifecycle, hours)
        cases[str(hours)] = {
            "hours": hours,
            "lifecycle_reference_usd_per_million": reference["all_in_usd_per_million_output_tokens"],
            "total_rate_cap_usd_per_hour": cap,
            "gpu_planning_rate_usd_per_hour": gpu_rate,
            "maximum_ancillary_rate_usd_per_hour": cap - gpu_rate,
            "target_usd_per_million": 0.514,
            "at_cap_usd_per_million": reference["all_in_usd_per_million_output_tokens"] * cap / gpu_rate,
            "classification": "unbound",
        }
    result = {
        "schema_version": 1,
        "decision": "unbound",
        "decision_scope": "committed_non_preemptible_8_to_64_gpu_l40s_production_topology",
        "decision_reason": "No current content-bound committed topology term in the allowed local evidence prices CPU, RAM, persistent boot/model storage, network/egress, orchestration/control, or mandatory support alongside the $1.10/GPU-hour planning base; no allowed source binds its interruption, replacement, billing-minimum, or restart semantics. Missing costs are not set to zero.",
        "fixed_workload": {
            "output_tokens_per_second": 734.5565331529764,
            "background_productive_utilization": 0.9,
            "retry_or_interruption_loss_fraction": 0.05,
            "cold_lifecycle_seconds": 1208.167873272,
            "target_usd_per_million_output_tokens": 0.514,
        },
        "cases": cases,
        "observed_but_nontransferable_experimental_topology": {
            "evidence_type": "measured",
            "rate_usd_per_hour": experiment["allocation_result"]["performance"]["l40s_full_vm_plus_disk_hourly_usd"],
            "topology": "Nebius preemptible gpu-l40s-a / 1gpu-16vcpu-64gb with 100 GiB NETWORK_SSD boot disk",
            "exclusions_and_semantics": [
                "Campaign ledger identifies the rate as authenticated preemptible full-VM plus disk and explicitly excludes public IPv4 and egress; invoice was pending.",
                "Available instance specifications use preemptible.on_preemption=STOP and recovery_policy=FAIL.",
                "This is an experimental single-VM observation, not a committed 12-24 month 8-64 GPU production quote; it cannot bind ancillary cost or restart count for the decision.",
            ],
        },
        "required_unbound_terms": [
            "CPU and RAM allocation/inclusion at production scale",
            "persistent boot/model/checkpoint storage price and persistence after interruption",
            "network, public IP, and egress price/inclusion",
            "orchestration/control-plane and mandatory support/reservation charges",
            "committed-capacity billing minimum and interruption/SLA/replacement semantics",
            "restart semantics sufficient to prove one cold lifecycle for 8h and the bound restart count for 24h",
        ],
        "interpretation": "Neither the 8h nor 24h L40S production envelope passes or fails on current permitted evidence. The GPU-only planning rate leaves only the stated ancillary headroom, while the experimental record demonstrates that at least public IPv4/egress are separately unpriced. A production claim remains closed until a matching content-bound committed topology term binds all required components and restart semantics.",
        "sources": {
            str(PRICES.relative_to(REPO)): {"sha256": digest(PRICES), "evidence_type": "derived_planning_rate"},
            str(LIFECYCLE.relative_to(REPO)): {"sha256": digest(LIFECYCLE), "evidence_type": "measured_and_derived"},
            str(EXPERIMENT.relative_to(REPO)): {"sha256": digest(EXPERIMENT), "evidence_type": "measured_experimental"},
            str(LEDGER.relative_to(REPO)): {"sha256": digest(LEDGER), "evidence_type": "measured_experimental"},
        },
    }
    (PROJECT / "STUDENT39_L40S_ALL_IN_GATE.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
