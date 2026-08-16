#!/usr/bin/env python3
"""Bound A40 throughput from the retained exact-current AWQ L40S c8 control."""

import argparse
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parents[2]
V24R2 = ROOT / "campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v24r2"
ADMISSION = ROOT / "research_lab/projects/a40_exact_memory_admission/A40_ADMISSION_RESULT.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(value):
    return round(value, 9)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    summary_path = V24R2 / "summary.json"
    trace_path = V24R2 / "trace-regions.json"
    telemetry_path = V24R2 / "telemetry-summary.json"
    validation_path = V24R2 / "trace-validation.json"
    summary = json.loads(summary_path.read_text())
    trace = json.loads(trace_path.read_text())
    telemetry = json.loads(telemetry_path.read_text())
    admission = json.loads(ADMISSION.read_text())
    c8 = next(
        profile
        for profile in summary["allocation_result"]["performance"]["profiles"]
        if profile["profile_id"] == "fixed_8k_1k_c8"
    )
    l40s_rate = c8["output_tokens_per_second_conservative"]
    gates = admission["economics"]["rate_sensitivity"]
    five_percent_gate = next(row["required_output_tokens_per_second"] for row in gates if row["target_usd_per_million_output"] == 0.6365 and row["lifecycle_overhead_fraction"] == 0.1)
    strong_gate = next(row["required_output_tokens_per_second"] for row in gates if row["target_usd_per_million_output"] == 0.6 and row["lifecycle_overhead_fraction"] == 0.1)

    hardware = {
        "a40_bf16_dense_tensor_tflops": 149.7,
        "l40s_bf16_dense_tensor_tflops": 366.3,
        "a40_memory_bandwidth_gb_s": 696.0,
        "l40s_memory_bandwidth_gb_s": 864.0,
        "sources": [
            "https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a40/proviz-print-nvidia-a40-datasheet-us-nvidia-1469711-r8-web.pdf",
            "https://www.nvidia.com/en-us/data-center/l40s/",
        ],
        "source": "NVIDIA A40 and L40S product materials; dense BF16 tensor peak and stated memory bandwidth",
    }
    compute_ratio = hardware["a40_bf16_dense_tensor_tflops"] / hardware["l40s_bf16_dense_tensor_tflops"]
    memory_ratio = hardware["a40_memory_bandwidth_gb_s"] / hardware["l40s_memory_bandwidth_gb_s"]
    families = {row["family"]: row["share_of_kernel_duration"] for row in trace["decode"]["kernel_families"]}
    memory_families = {"attention_mla", "copy_cast"}
    central_ratio = 1 / sum(share / (memory_ratio if family in memory_families else compute_ratio) for family, share in families.items())

    def band(ratio, mechanism):
        return {
            "transfer_fraction_of_l40s": rounded(ratio),
            "output_tokens_per_second": rounded(l40s_rate * ratio),
            "mechanism": mechanism,
            "five_percent_gate_pass": l40s_rate * ratio >= five_percent_gate,
            "strong_gate_pass": l40s_rate * ratio >= strong_gate,
        }

    result = {
        "schema_version": 1,
        "analysis_id": "a40_archived_trace_transfer_bound_2026-07-15",
        "scope": "Zero-cost archived-evidence transfer falsifier; not an A40 throughput prediction or delivered-cost claim.",
        "evidence_labels": {
            "l40s_c8_rate": "measured",
            "trace_family_mix": "measured summed profiler work, explicitly non-additive wall time",
            "gpu_telemetry": "measured sampled telemetry",
            "hardware_specs": "vendor-reported",
            "bands": "derived conditional scaling scenarios",
        },
        "inputs": {
            "checkpoint_revision": summary["allocation_result"]["model_revision"],
            "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in [summary_path, trace_path, telemetry_path, validation_path, ADMISSION]},
            "c8_profile": {key: c8[key] for key in ["profile_id", "concurrency", "total_input_tokens", "total_output_tokens", "wall_seconds", "output_tokens_per_second_conservative", "tpot_ms", "ttft_ms"]},
            "trace": {"validation_pass": json.loads(validation_path.read_text())["pass"], "decode_status": trace["decode"]["status"], "decode_kernel_family_shares": families},
            "telemetry": telemetry["phases"]["conditional_semantic_quality_performance_batch"]["metrics"],
        },
        "hardware": {**hardware, "compute_transfer_fraction": rounded(compute_ratio), "memory_transfer_fraction": rounded(memory_ratio)},
        "economic_gates": {
            "five_percent_cost_gate_tok_s": five_percent_gate,
            "strong_0_60_per_million_tok_s": strong_gate,
            "required_transfer_fraction_five_percent": rounded(five_percent_gate / l40s_rate),
            "required_transfer_fraction_strong": rounded(strong_gate / l40s_rate),
        },
        "bands": {
            "conservative_compute_bound": band(compute_ratio, "All request-critical serving work scales no better than dense BF16 tensor compute."),
            "central_trace_classification": band(central_ratio, "Non-overlapping surrogate only: attention/MLA and copy/cast scale with HBM; remaining trace families scale with tensor compute."),
            "optimistic_memory_bound": band(memory_ratio, "All request-critical serving work scales with stated HBM bandwidth."),
        },
        "identification": {
            "archive_can_promote_or_close": False,
            "reason": "The retained trace supplies summed GPU component durations rather than a request-critical non-overlapping wall decomposition. It cannot exclude host/scheduler time or prove the selected family mapping; therefore the compute and memory scenarios are conditional bounds, not conservative throughput bounds.",
            "excluded_interpretation": "Kernel-family shares are not summed into an Amdahl coefficient.",
        },
        "decision": "CONDITIONAL_DIRECT_A40_C8_MEASUREMENT_ONLY",
        "next_decisive_signal": {
            "signal": "matched_A40_c8_8192x1024_aggregate_output_tokens_per_second",
            "minimum_contract": "Exact ab31d120 AWQ checkpoint, stock vLLM settings, c8 with 8,192 input and 1,024 output tokens, aggregate output tokens divided by measured arm wall time, plus request rows and GPU telemetry.",
            "decision_rule": f"Promote only if the conservative measured rate is at least {strong_gate:.6f} tok/s; close the 5% route if it is below {five_percent_gate:.6f} tok/s; otherwise retain only the narrower conditional interval.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
