#!/usr/bin/env python3
"""Reproduce the zero-provider RTX 6000 Ada bound for the measured student39."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path(__file__).resolve().parent
STUDENT = ROOT / "distilled_depth_student_architecture"
SUMMARY = STUDENT / "artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02/summary.json"
STATUS = STUDENT / "STATUS.json"
PRIOR = ROOT / "rtx6000ada_transfer_bound/rtx6000ada_c16_transfer_bound.json"
INVENTORY = Path("/root/workspace/research/factory/data/accelerator_inventory.json")

TARGET_COST = 0.514
RATES = {"listed_usd_per_hour": 0.77, "conservative_lifecycle_usd_per_hour": 0.847,
         "sensitivity_low_usd_per_hour": 0.70, "sensitivity_high_usd_per_hour": 1.00}
CARD_VISIBLE_MIB = 46068
PEAK_C32_MIB = 44459.51696777344
KV_C16_TO_C32_MIB = 1152.0
LIFECYCLE_UTILIZATION = 0.95
PERFORMANCE_COMPONENTS = {
    "kernel_legality_and_shape": 0.98,
    "sustained_clock_power_cooling": 0.90,
    "runtime_driver_support": 0.98,
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cost_per_million(rate: float, throughput: float) -> float:
    return rate * 1_000_000 / (3600 * throughput)


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    student_status = json.loads(STATUS.read_text())
    prior = json.loads(PRIOR.read_text())
    inventory = json.loads(INVENTORY.read_text())
    profiles = summary["allocation_result"]["performance"]["profiles"]
    measured = {f"c{p['concurrency']}": p["output_tokens_per_second_conservative"] for p in profiles}
    retention_performance = 1.0
    for value in PERFORMANCE_COMPONENTS.values():
        retention_performance *= value
    retention_sustainable = retention_performance * LIFECYCLE_UTILIZATION
    peak_c16 = PEAK_C32_MIB - KV_C16_TO_C32_MIB
    capacity = {
        "source_card_visible_mib_measured": CARD_VISIBLE_MIB,
        "same_nominal_memory_vendor_reported_gb": 48,
        "c16_peak_mib_derived_from_corrected_c32_minus_exact_kv_delta": peak_c16,
        "c32_peak_mib_corrected_analytical": PEAK_C32_MIB,
        "c16_headroom_mib_if_target_reports_source_visible_capacity": CARD_VISIBLE_MIB - peak_c16,
        "c32_headroom_mib_if_target_reports_source_visible_capacity": CARD_VISIBLE_MIB - PEAK_C32_MIB,
        "c32_headroom_fraction_of_visible_capacity": (CARD_VISIBLE_MIB - PEAK_C32_MIB) / CARD_VISIBLE_MIB,
        "c32_admission_gate": {
            "target_nvidia_smi_memory_total_mib_min": CARD_VISIBLE_MIB,
            "target_loaded_and_8k_1k_c32_memory_used_mib_max": PEAK_C32_MIB,
            "reason": "The source L40S reports 46,068 MiB rather than treating nominal 48 GB as card-visible memory. The RTX has the same vendor-reported 48-GB ECC GDDR6 capacity, but its driver-visible value is unmeasured."
        },
    }
    arms = {}
    for name in ("c16", "c32"):
        baseline = measured[name]
        performance_low = baseline * retention_performance
        sustainable_low = baseline * retention_sustainable
        economics = {}
        for rate_name, rate in RATES.items():
            required_util = rate * 1_000_000 / (3600 * TARGET_COST * performance_low)
            economics[rate_name] = {
                "rate_usd_per_hour": rate,
                "required_productive_utilization": required_util,
                "maximum_lifecycle_overhead_fraction": 1 - required_util,
                "cost_at_95pct_productive_utilization_usd_per_million": cost_per_million(rate, sustainable_low),
            }
        arms[name] = {
            "measured_l40s_output_tok_s": baseline,
            "performance_retention_interval": [retention_performance, 1.0],
            "performance_retained_output_tok_s_interval": [performance_low, baseline],
            "productive_utilization_interval": [LIFECYCLE_UTILIZATION, 0.99],
            "sustainable_retention_interval": [retention_sustainable, 0.99],
            "sustainable_output_tok_s_interval": [sustainable_low, baseline * 0.99],
            "required_output_tok_s_at_conservative_rate": RATES["conservative_lifecycle_usd_per_hour"] * 1_000_000 / (3600 * TARGET_COST),
            "economics": economics,
        }
    c32 = arms["c32"]
    later_arm = {
        "nominate": True,
        "status": "conditional_after_quality_recovery",
        "why_decisive": "At the conservative 0.821142 sustainable retention floor, c32 is 603.175 output tok/s and $0.3901/M at $0.847/h, leaving 21.58% cost margin below the $0.514/M gate. The one remaining material uncertainty is exact RTX card-visible capacity and sustained runtime behavior.",
        "runtime_and_workload": "Pinned vLLM 0.15.0 compressed-tensors AWQ path; BF16 activations, KV auto, --max-model-len 32768, --max-num-seqs 32, --max-num-batched-tokens 65536, --gpu-memory-utilization 0.90, prefix cache disabled, seed 1234; exact 8,192-input/1,024-output c32 workload with two 32-request waves.",
        "quality_gate": "Use the recovered 39-layer checkpoint only after its recovery project passes the campaign quality gate; preserve the manifest/revision and perform paired quality output capture before economic interpretation.",
        "minimum_raw_throughput_output_tok_s_at_minimum_utilization": c32["performance_retained_output_tok_s_interval"][0],
        "minimum_lifecycle_adjusted_throughput_output_tok_s": c32["required_output_tok_s_at_conservative_rate"],
        "minimum_productive_utilization_at_0_847_per_hour": c32["economics"]["conservative_lifecycle_usd_per_hour"]["required_productive_utilization"],
        "memory_gate": capacity["c32_admission_gate"],
        "reliability_gate": "All 64 requests succeed at exact geometry; prefix-cache deltas remain zero; record interruption/reload/retry time and retain at least the required productive utilization.",
        "spend_and_cleanup_gate": "No allocation is authorized by this bound. Any later owner must set a capped spend and absolute watchdog before creation, retain raw telemetry plus request rows, and verify instance and disk absence after the arm.",
        "falsifiers": [
            "RTX 6000 Ada nvidia-smi reports less than 46,068 MiB visible memory or c32 used memory exceeds 44,459.517 MiB.",
            "Raw c32 output is below 634.921 tok/s at the 72.094% productive-utilization floor, or their product is below 457.739 lifecycle-adjusted tok/s.",
            "The RTX dispatches a materially different compressed-tensors kernel, throttles, or fails the recovered-quality contract."
        ],
    }
    result = {
        "schema_version": 1,
        "question": "Exact zero-provider RTX 6000 Ada capacity, retention, utilization, and lifecycle bound for measured student39 c16/c32.",
        "evidence_labels": {"student_throughput_and_source_memory": "measured", "chip_identity": "vendor_reported/shared_inventory", "transfer_and_economics": "derived_conservative", "0.77_rate": "vendor_listed_prior_evidence", "later_arm": "conditional_inferred"},
        "evidence_hashes": {"student_summary_sha256": digest(SUMMARY), "student_terminal_artifact_sha256": student_status["result"]["artifact_sha256"], "student_status_sha256": digest(STATUS), "prior_transfer_sha256": digest(PRIOR), "accelerator_inventory_sha256": digest(INVENTORY)},
        "invariants": ["SM89", "142 SMs", "568 Tensor Cores", "96 MB L2", "48-GB ECC GDDR6 nominal capacity", "PCIe Gen4 x16", "vLLM compressed-tensors legality"],
        "unmeasured_target_differences": ["driver-visible memory total", "sustained clocks/cooling under c32", "actual kernel dispatch", "runtime workspace/fragmentation", "interruption/reload behavior"],
        "source_runtime": {"gpu": "L40S", "driver": "580.159.04", "cuda": "13.0", "runtime": "vLLM 0.15.0", "quantization": "compressed-tensors", "source_c32_telemetry_memory_used_mib": 43665, "source_c32_telemetry_memory_total_mib": CARD_VISIBLE_MIB},
        "transfer_components": {"performance_only": PERFORMANCE_COMPONENTS, "lifecycle_productive_utilization": LIFECYCLE_UTILIZATION, "prior_c16_full_model_sustainable_floor": prior["transfer_interval"]["retained_fraction"][0], "method": "Separate same-chip performance transfer from productive utilization; do not claim the 960/864 GB/s bandwidth ratio as realized throughput."},
        "capacity": capacity,
        "arms": arms,
        "decision": {"placement": "conditional_candidate_only", "economics": "c16 and c32 pass at the conservative floor; c32 has the stronger 0.3901/M bound at $0.847/h.", "nominate_later_arm": later_arm},
    }
    output = PROJECT / "STUDENT39_RTX6000ADA_BOUND.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
