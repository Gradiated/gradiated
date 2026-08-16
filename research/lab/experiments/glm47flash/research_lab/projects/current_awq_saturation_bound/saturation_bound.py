#!/usr/bin/env python3
"""Reproducible zero-cost c24/c32 saturation bound from retained c16 evidence."""
import json
from pathlib import Path

C16_TPS = 535.2861037029285
C8_TPS = 352.11187024973486
TARGET_TPS = 562.050  # 1.05 * C16_TPS, campaign promotion hurdle
GPU_MEAN = 98.36 / 100.0
GPU_P95 = 100.0 / 100.0
MEM_TOTAL = 46068.0
MEM_C16_MAX = 44103.0
MEM_C16_MEAN = 42716.65
QUEUE_C16_MEAN_S = 2.072266995874962
TTFT_C16_P95_S = 10.061244281999961
E2E_C16_MAX_S = 30.64113109699997
ARM_ENVELOPE_S = 300.0


def main():
    # The c16 science window is 206 1-Hz samples from the retained telemetry.csv.
    # Use the observed c16 incremental envelope per active sequence as a deliberately
    # simple memory stress model; no claim is made about allocator fragmentation.
    baseline_mem = MEM_C16_MEAN - (MEM_C16_MAX - MEM_C16_MEAN)
    kv_per_seq_mib = (MEM_C16_MAX - baseline_mem) / 16.0
    arms = {}
    for c in (24, 32):
        predicted_max_mib = MEM_C16_MAX + (c - 16) * kv_per_seq_mib
        # Conservative: no throughput credit beyond measured c16, and reject if
        # the linear envelope exceeds device capacity.
        conservative = 0.0 if predicted_max_mib > MEM_TOTAL else C16_TPS
        # Optimistic: grant all observed mean GPU idle as useful work, with no
        # extra scheduling, kernel, memory, or reliability penalty.
        optimistic = C16_TPS / GPU_MEAN
        arms[str(c)] = {
            "predicted_peak_memory_mib_linear": round(predicted_max_mib, 3),
            "memory_headroom_mib_linear": round(MEM_TOTAL - predicted_max_mib, 3),
            "memory_fit_under_linear_envelope": predicted_max_mib <= MEM_TOTAL,
            "conservative_tps": round(conservative, 3),
            "optimistic_tps_perfect_idle_recovery": round(optimistic, 3),
            "optimistic_gain_percent_vs_c16": round((optimistic / C16_TPS - 1) * 100, 3),
            "beats_562_050": optimistic >= TARGET_TPS,
            "nominate": False,
        }
    result = {
        "question": "current-AWQ c24/c32 L40S saturation bound",
        "evidence_class": "measured inputs plus derived conservative/optimistic bounds",
        "source_artifact": "../nebius_current_awq_c16_direct/artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/vllm-awq-batch.tar.gz",
        "geometry": {"input_tokens": 8192, "output_tokens": 1024, "max_num_batched_tokens": 65536,
                     "c16_max_num_seqs": 16, "prefix_cache": False, "vllm": "0.15.0"},
        "c16": {"throughput_tps": C16_TPS, "c8_throughput_tps": C8_TPS,
                "target_tps": TARGET_TPS, "gpu_mean_fraction": GPU_MEAN,
                "gpu_p95_fraction": GPU_P95, "memory_total_mib": MEM_TOTAL,
                "memory_peak_mib": MEM_C16_MAX, "memory_mean_mib": MEM_C16_MEAN,
                "queue_mean_seconds": QUEUE_C16_MEAN_S, "ttft_p95_seconds": TTFT_C16_P95_S,
                "e2e_max_seconds": E2E_C16_MAX_S, "arm_envelope_seconds": ARM_ENVELOPE_S},
        "derived_assumptions": {
            "kv_increment_mib_per_sequence": round(kv_per_seq_mib, 3),
            "optimistic_ceiling": "perfectly convert every sampled mean GPU-idle fraction to useful work; zero new overhead",
            "scheduler": "summed queue time is not treated as wall-time share; no queue credit is granted",
            "reliability": "c16 all 32 requests completed; c24/c32 receive no unmeasured reliability credit",
            "memory": "linear c16 incremental envelope; fragmentation and allocator effects are unresolved"
        },
        "arms": arms,
        "decision": "close_c24_c32_and_retain_c16",
        "decision_reason": "Even the perfect-idle-recovery ceiling is below the 562.050 tps hurdle; c32 also exceeds the linear memory envelope."
    }
    out = Path(__file__).with_name("SATURATION_BOUND.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
