#!/usr/bin/env python3
"""Derive the 48-GiB W4 hardware price screen from frozen campaign inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
FACTORY = ROOT.parents[5] / "factory" / "data"
BOUND = LAB / "projects/gemma_l40s_w4_c16_economic_bound/W4_C16_BOUND_V2.json"
PACKET = LAB / "projects/gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json"
SATURATION = LAB / "projects/l40s_saturation_economic_gate/SATURATION_GATE.json"
PRICES = FACTORY / "gpu_prices.json"
INVENTORY = FACTORY / "accelerator_inventory.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    bound = json.loads(BOUND.read_text())
    packet = json.loads(PACKET.read_text())
    saturation = json.loads(SATURATION.read_text())
    prices = json.loads(PRICES.read_text())
    price_rows = {row["id"]: row for row in prices["accelerators"]}
    inventory = {row["id"]: row for row in json.loads(INVENTORY.read_text())["accelerators"]}
    l40s_rate = price_rows["nvidia-l40s"]["production_planning_usd_per_gpu_hour"]
    l40s = inventory["nvidia-l40s"]

    public_rates = {
        "nvidia-a40": 0.44,
        "nvidia-rtx-6000-ada": 0.77,
    }
    source = {
        "id": "ultralytics_cloud_gpu_training_pricing_2026_07_17",
        "label": "vendor_reported_public_on_demand",
        "url": "https://docs.ultralytics.com/platform/train/cloud-training",
        "retrieved_at_utc": "2026-07-17T06:00:00Z",
        "note": "Lists A40 $0.44/h, RTX 6000 Ada $0.77/h, and L40S $0.86/h. This is an on-demand vendor listing, not a 12-24 month committed production quote.",
    }
    discount = 0.85
    rows = []
    for ident in ("nvidia-a40", "nvidia-rtx-6000-ada"):
        gpu = inventory[ident]
        bandwidth_ratio = gpu["memory"]["bandwidth_gb_s"] / l40s["memory"]["bandwidth_gb_s"]
        conservative_ratio = bandwidth_ratio * discount
        public_rate = public_rates[ident]
        rows.append({
            "id": ident,
            "model": gpu["model"],
            "evidence": "inventory + first_party_source + vendor_reported_public_on_demand + derived + inferred",
            "hardware": {
                "architecture_profile": gpu["architecture_profile_id"],
                "sm_count": gpu["execution"]["compute_units"],
                "capacity_gb": gpu["memory"]["capacity_gb"],
                "memory_bandwidth_gb_s": gpu["memory"]["bandwidth_gb_s"],
                "l2_mb": gpu["cache"]["last_level_mb"],
                "power_w": gpu["power_w"],
                "numeric_formats": gpu["numeric_formats"],
                "topology": gpu["interconnect"]["topology"],
            },
            "capacity": {
                "logical_fit": "same 48-GB capacity as L40S; inherits W4 c16 31.158265 GiB and c32 36.973037 GiB logical totals",
                "allocator_risk": "c16 has 13.545735 GiB logical slack; c32 has 7.730963 GiB. 10K c32 has only 0.612795 GiB and remains allocator-sensitive on all three cards.",
            },
            "consumer_support": {
                "source": "pinned vLLM AutoAWQ source; get_min_capability=75 and CUDA Marlin selection is conditional on check_marlin_supported and layer support",
                "capability": "A40 SM86 / RTX 6000 Ada SM89 both exceed the source minimum 75",
                "status": "source-supported candidate only; fresh CUDA six-shape Marlin execution is required before any throughput or production claim",
            },
            "observed_public_rate_usd_per_gpu_hour": public_rate,
            "rate_evidence": source["id"],
            "break_even": {
                "equal_all_in_max_rate_usd_per_gpu_hour": {
                    "bandwidth_proportional": l40s_rate * bandwidth_ratio,
                    "conservative_85pct_efficiency": l40s_rate * conservative_ratio,
                    "measured_live_terminal_parameterized": "1.10 * R_matched, where R_matched = candidate whole-workload throughput / measured L40S whole-workload throughput",
                },
                "ten_percent_better_all_in_max_rate_usd_per_gpu_hour": {
                    "bandwidth_proportional": 0.9 * l40s_rate * bandwidth_ratio,
                    "conservative_85pct_efficiency": 0.9 * l40s_rate * conservative_ratio,
                    "measured_live_terminal_parameterized": "0.99 * R_matched",
                },
                "minimum_matched_throughput_ratio_at_observed_public_rate": {
                    "equal_all_in": public_rate / l40s_rate,
                    "ten_percent_better_all_in": public_rate / (0.9 * l40s_rate),
                },
            },
            "mechanism_risk": (
                "SM86 has 84 SMs, 6-MB L2, and 696 GB/s versus L40S's 142 SMs, 96-MB L2, and 864 GB/s; "
                "the large repeated W4 active stream is likely DRAM-bound, but smaller L2 and fewer SMs can worsen tile/grid occupancy and scale below bandwidth."
                if ident == "nvidia-a40"
                else "Same SM89 count and 96-MB L2 as L40S, with 960 versus 864 GB/s, so bandwidth scaling is a useful but unmeasured prior; workstation cooling/sustained clocks and specialist-cloud host topology can erase it."
            ),
        })

    result = {
        "schema_version": 1,
        "decision": "conditional_matched_gpu_nominee",
        "nominee": "nvidia-rtx-6000-ada",
        "condition": "Only if the separate live L40S W4 mechanism emits a passing typed terminal. Then require one fresh matched CUDA, six-shape, c16/c32 whole-workload measurement and a current written 12-24 month committed quote before a production claim.",
        "non_nominee": {"id": "nvidia-a40", "reason": "Its $0.44/h marketplace-like on-demand rate can beat the L40S cost surface only if it retains at least 44.4% of L40S throughput for 10% improvement; that is plausible but its lower bandwidth/L2 and SM86 kernel behavior create too much unmeasured performance risk for the sole nominee."},
        "decision_basis": "RTX 6000 Ada's observed $0.77/h is below both the $0.99/h conservative 10%-better ceiling and $1.10/h bandwidth-proportional 10%-better ceiling. Its SM89, SM count, 96-MB L2, INT4, and source capability gate match L40S; no throughput has been transferred.",
        "inputs": {str(path.relative_to(ROOT.parents[5])): sha(path) for path in (BOUND, PACKET, SATURATION, PRICES, INVENTORY)},
        "l40s_reference": {"planning_rate_usd_per_gpu_hour": l40s_rate, "shared_price_refreshed_at_utc": prices["refreshed_at_utc"], "shared_price_age_days_at_director_turn": 1.688, "hardware": {"sm": l40s["execution"]["compute_units"], "bandwidth_gb_s": l40s["memory"]["bandwidth_gb_s"], "l2_mb": l40s["cache"]["last_level_mb"], "power_w": l40s["power_w"]}},
        "workload": {"exact_w4_active_text_stream_gib": bound["bytes"]["w4"]["active_text_stream_gib"], "logical_totals_gib": bound["capacity"]["w4_primary_totals_gib"], "concurrency": [16, 32], "six_marlin_shapes": packet["scope"]["shapes"], "request_mix": bound["target"]["workload"]},
        "assumptions": {"all_in_factor": "Candidate and L40S use the same saturation-gate utilization/headroom/non-GPU/reliability/storage factors; therefore they cancel in rate/throughput ratios.", "conservative_efficiency_discount": discount, "bandwidth_proportional": "An analytical decode weight-stream prior only, not transferred performance evidence."},
        "public_rate_source": source,
        "candidates": rows,
        "economic_target": {"planning_required_requests_per_second": saturation["economic_surface"]["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"], "conservative_required_requests_per_second": saturation["economic_surface"]["conservative"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"]},
        "generated_utc": "2026-07-17T06:10:00Z",
    }
    (ROOT / "HARDWARE_SCREEN.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
