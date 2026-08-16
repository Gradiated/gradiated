#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
CSV = PROJECT / "artifacts/global-ncu-20260720t1136z/global_ncu/ncu-export.csv"
REPORT = PROJECT / "artifacts/global-ncu-20260720t1136z/global_ncu/global-fwd.ncu-rep"
OUTPUT = PROJECT / "GLOBAL_ATTENTION_NCU.json"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    rows = list(csv.reader(CSV.open()))
    index = next(i for i, row in enumerate(rows) if len(row) > 4 and row[4] == "_fwd_kernel")
    header, units, values = rows[index - 2], rows[index - 1], rows[index]

    def metric(name: str) -> dict[str, object]:
        column = header.index(name)
        raw = values[column].replace(",", "")
        try:
            value: object = float(raw)
        except ValueError:
            value = values[column]
        return {"value": value, "unit": units[column] or None}

    names = [
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
        "sm__maximum_warps_avg_per_active_cycle",
        "sm__maximum_warps_per_active_cycle_pct",
        "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active",
        "sm__warps_active.avg.pct_of_peak_sustained_active",
        "profiler__replayer_passes",
    ]
    output = {
        "schema_version": 1,
        "evidence_type": "measured_exact_kernel_ncu",
        "pass": True,
        "scope": {
            "kernel": "_fwd_kernel",
            "launch_skip": 5,
            "launch_count": 1,
            "mapped_subtype": "global_extend",
            "qk_head_dim": 512,
            "v_head_dim": 512,
            "q_heads": 32,
            "kv_heads": 4,
            "control_block_m": 32,
            "control_block_n": 64,
        },
        "producer": {"report": str(REPORT.relative_to(PROJECT)), "sha256": sha256(REPORT)},
        "consumer": {"csv": str(CSV.relative_to(PROJECT)), "sha256": sha256(CSV)},
        "metrics": {name: metric(name) for name in names},
        "causal_interpretation": {
            "measured": "The exact 2048-CTA global kernel has 15.52 waves per 132-SM H200, so grid realization is not underfilled. It is limited to one CTA/SM by 255 registers/thread while shared memory permits two CTAs/SM. Achieved warp occupancy is 12.496527%, tensor activity 10.100424%, DRAM 2.214164%, and L2 36.955752%.",
            "inference": "The causal limiter is live register state, not HBM bandwidth, shared-memory capacity, or grid supply. The pinned source already uses BLOCK_M=16 for head-dim 512 on Blackwell specifically to avoid register exhaustion; applying that one live-state reduction only to the exact Hopper global head-dim-512 subtype is the admitted intervention.",
            "falsifier": "Reject the specialization if the sole stacked pair is not faster or lacks exact candidate-path, semantic, accounting, FP8, QKV, or retained-local-attention proof.",
        },
    }
    temporary = OUTPUT.with_suffix(".part")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)


if __name__ == "__main__":
    main()
