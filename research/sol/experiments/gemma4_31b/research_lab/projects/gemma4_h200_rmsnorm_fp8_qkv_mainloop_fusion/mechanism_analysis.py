#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib


M_VALUES = (1, 16, 32)
K = 5376
N = 16384
N_TILE = 64
K_TILE = 256
SMS = 132
PORTABLE_CLUSTER_BLOCKS = 8
CONTROL_TILE_SLOTS = 2
WEIGHT_BYTES = K * N
QUALIFIED_SECONDS = 0.625149101968745
LAYERS = 60
DECODE_STEPS = 358
COMPLETED_REQUESTS = 32

PINNED = {
    "producer": (
        "../gemma4_h200_current_norm_fp8_hotblock/"
        "norm_fp8_decode_exact_order.cu",
        "fba1452c2cf460a92d229f9944b8fc14f77b10ce7490269e6c9307feb772c792",
    ),
    "runtime_adapter": (
        "../gemma4_h200_current_norm_fp8_hotblock/runtime_adapter.py",
        "adbd48db4599b05920026fdd070b893ee885ae08d63e5b6235cee0cd8d379471",
    ),
    "fp8_gemm_entry": (
        "../gemma4_h200_dense_fp8_linear_schedule/inputs/sgl-kernel-v0513/"
        "csrc/gemm/fp8_gemm_kernel.cu",
        "be6f95bb0ef108ebf08b8b84336b6840726beb7fa5bbb90aa6eb4038ce778767",
    ),
    "sm90_dispatch": (
        "../gemma4_h200_dense_fp8_linear_schedule/inputs/sgl-kernel-v0513/"
        "csrc/cutlass_extensions/gemm/fp8_gemm_sm90_dispatch.cuh",
        "4fcb4321942f326761ba5b0a968086acbd458fb57c5429d2706653a94b199620",
    ),
}


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind_sources(root: pathlib.Path) -> dict[str, object]:
    identities = {}
    for name, (relative, expected) in PINNED.items():
        path = (root / relative).resolve()
        observed = sha256(path)
        if observed != expected:
            raise RuntimeError(
                f"{name} source mismatch: expected {expected}, observed {observed}"
            )
        identities[name] = {
            "path": str(path),
            "sha256": observed,
        }
    return identities


def cluster_row(m: int, blocks: int, clusters: int) -> dict[str, object]:
    consumer_ctas = blocks * clusters
    tile_slots = math.ceil((N // N_TILE) / consumer_ctas)
    rows_per_block = math.ceil(m / blocks)
    activation_bytes = m * K
    producer_global_load_bytes_per_copy = m * K * 4
    normalized_peak_bytes_per_cluster = m * K * 2
    mainloop_stage_payload_bytes = (
        N_TILE * K_TILE + (16 if m <= 16 else 32) * K_TILE
    )
    persistent_activation_bytes_per_block = rows_per_block * K
    return {
        "cluster_blocks": blocks,
        "clusters": clusters,
        "consumer_ctas": consumer_ctas,
        "consumer_tile_slots_per_cta": tile_slots,
        "scheduled_sms": min(SMS, consumer_ctas),
        "scheduled_sm_fraction": min(SMS, consumer_ctas) / SMS,
        "producer_copies": clusters,
        "exact_row_rounds_per_cta": rows_per_block,
        "producer_global_load_bytes": (
            producer_global_load_bytes_per_copy * clusters
        ),
        "producer_activation_dsm_store_bytes": activation_bytes * clusters,
        "consumer_activation_dsm_read_bytes": activation_bytes * (N // N_TILE),
        "normalized_bf16_peak_dsm_bytes_per_cluster": (
            normalized_peak_bytes_per_cluster
        ),
        "normalized_bf16_peak_dsm_bytes_per_block": (
            rows_per_block * K * 2
        ),
        "persistent_fp8_activation_bytes_per_block": (
            persistent_activation_bytes_per_block
        ),
        "cutlass_mainloop_ab_payload_bytes_per_stage": (
            mainloop_stage_payload_bytes
        ),
        "persistent_activation_fraction_of_one_ab_stage_payload": (
            persistent_activation_bytes_per_block
            / mainloop_stage_payload_bytes
        ),
        "shared_storage_consequence": (
            "The FP8 row fragments must remain resident through the mainloop. "
            "They either consume the auto-stage residual or remove a TMA "
            "pipeline stage; the normalized-BF16 producer scratch may alias "
            "mainloop storage only after quantization and cluster publication."
        ),
        "minimum_cluster_barriers_before_first_wgmma": 3,
    }


def shape_analysis(m: int) -> dict[str, object]:
    output_tiles = N // N_TILE
    materialized = {
        "producer_copies": 1,
        "producer_global_input_and_norm_weight_load_bytes": m * K * 4,
        "activation_global_store_bytes": m * K,
        "scale_global_store_bytes": m * 4,
        "logical_consumer_activation_l2_read_bytes": output_tiles * m * K,
        "consumer_weight_bytes": WEIGHT_BYTES,
        "consumer_ctas": output_tiles,
        "consumer_grid_waves": output_tiles / SMS,
        "consumer_tile_slots_critical_depth": CONTROL_TILE_SLOTS,
    }
    one_cluster = cluster_row(m, PORTABLE_CLUSTER_BLOCKS, 1)
    parity_clusters = math.ceil(
        output_tiles / (PORTABLE_CLUSTER_BLOCKS * CONTROL_TILE_SLOTS)
    )
    parity = cluster_row(m, PORTABLE_CLUSTER_BLOCKS, parity_clusters)
    bounded_groups = []
    for group_tiles in (1, 2, 4, 8):
        bounded_groups.append(
            {
                "n_tiles_per_producer_copy": group_tiles,
                "producer_copies": math.ceil(output_tiles / group_tiles),
                "producer_global_load_bytes": (
                    math.ceil(output_tiles / group_tiles) * m * K * 4
                ),
                "minimum_cluster_syncs": (
                    3 * math.ceil(output_tiles / group_tiles)
                ),
            }
        )
    return {
        "m": m,
        "k_tiles": math.ceil(K / K_TILE),
        "last_k_tile_elements": K % K_TILE,
        "output_n_tiles": output_tiles,
        "dispatch": {
            "swap_ab": True,
            "kernel_tile": (
                [64, 16, 256] if m <= 16 else [64, 32, 256]
            ),
            "cluster": [1, 1, 1],
            "schedule": "KernelTmaWarpSpecializedFP8FastAccum",
            "scheduler": "PersistentScheduler",
        },
        "materialized_control": materialized,
        "single_cluster_handoff": one_cluster,
        "concurrency_parity_cluster_handoff": parity,
        "bounded_n_tile_recomputation": bounded_groups,
        "parity_penalties_vs_materialized": {
            "producer_copy_multiplier": parity["producer_copies"],
            "added_producer_global_load_bytes": (
                parity["producer_global_load_bytes"]
                - materialized[
                    "producer_global_input_and_norm_weight_load_bytes"
                ]
            ),
            "added_exact_row_rounds_per_cta": max(
                0, parity["exact_row_rounds_per_cta"] - 1
            ),
            "global_activation_store_bytes_removed": m * K,
            "logical_l2_activation_reads_replaced_by_dsm_reads": (
                output_tiles * m * K
            ),
            "weight_bytes_unchanged": WEIGHT_BYTES,
        },
    }


def opportunity_register() -> dict[str, object]:
    return {
        "schema_version": 1,
        "opportunities": [
            {
                "id": "cluster_dsm_exact_qkv_handoff",
                "observation": (
                    "The pinned M<=32 QKV path launches 256 cluster-1 CTAs; "
                    "DSM visibility ends at the cluster boundary."
                ),
                "evidence_scope": (
                    "Gemma 4 layer-0 decode M=1/16/32, K=5376, N=16384, "
                    "SGLang v0.5.13 SM90 CUTLASS consumer on H200"
                ),
                "competing_explanations": [
                    "one persistent cluster can serialize enough N tiles",
                    "multiple clusters can duplicate the producer cheaply",
                    "the materialized activation is already L2-resident",
                ],
                "mechanism": (
                    "publish exact E4M3 rows and FP32 scales in cluster DSM "
                    "and copy fragments into each CTA's WGMMA staging storage"
                ),
                "falsifier": (
                    "one exact H200 M=32 full-output component beats the "
                    "corrected materialized control with 16x8 cluster geometry"
                ),
                "next_measurement": (
                    "Only after a new source implementation exists: one "
                    "M=32 real layer-0 QKV corrected-materialized versus "
                    "16-cluster x 8-CTA DSM comparison"
                ),
                "cost_usd": 0.0,
                "decision_impact": 0.75,
                "uncertainty": 0.25,
                "discrimination_power": 0.95,
                "readiness": 0.15,
                "transfer_penalty": 0.6,
            },
            {
                "id": "bounded_n_tile_recomputation",
                "observation": (
                    "Each original output-N tile consumes every activation "
                    "row and all 5376 K elements."
                ),
                "evidence_scope": (
                    "same exact consumer; tile groups limited to the portable "
                    "eight-CTA cluster"
                ),
                "competing_explanations": [
                    "scalar normalization can hide under weight TMA",
                    "larger persistent groups can amortize production",
                ],
                "mechanism": "recompute the exact row producer per N-tile group",
                "falsifier": (
                    "a group size <=8 with complete exact bytes has lower "
                    "component latency than the materialized control"
                ),
                "next_measurement": "none; dominated analytically by cluster scope",
                "cost_usd": 0.0,
                "decision_impact": 0.7,
                "uncertainty": 0.1,
                "discrimination_power": 0.9,
                "readiness": 0.0,
                "transfer_penalty": 0.7,
            },
            {
                "id": "materialized_exact_producer",
                "observation": (
                    "The standalone corrected producer already removes one "
                    "launch and the normalized-BF16 global intermediate."
                ),
                "evidence_scope": (
                    "source-complete corrected exact-order producer; target "
                    "H200 timing intentionally belongs to its funded project"
                ),
                "competing_explanations": [
                    "corrected 672-thread resource geometry erases the prior gain",
                    "activation remains hot in L2 for fp8_scaled_mm",
                ],
                "mechanism": (
                    "one exact producer copy and a global E4M3/FP32 interface"
                ),
                "falsifier": (
                    "the funded exact-order target-H200 component is non-positive"
                ),
                "next_measurement": (
                    "consume the separately funded exact-order component result"
                ),
                "cost_usd": 0.0,
                "decision_impact": 0.9,
                "uncertainty": 0.35,
                "discrimination_power": 0.9,
                "readiness": 1.0,
                "transfer_penalty": 0.25,
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--opportunities", required=True, type=pathlib.Path)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parent
    sources = bind_sources(root)
    shapes = [shape_analysis(m) for m in M_VALUES]
    prior_candidate_producer_ms_m32 = 0.017664000391960144
    absolute_ceiling_seconds = (
        prior_candidate_producer_ms_m32
        / 1000.0
        * LAYERS
        * DECODE_STEPS
        / COMPLETED_REQUESTS
    )
    result = {
        "schema_version": 1,
        "classification": (
            "typed_analytical_negative_cluster_scope_and_qkv_fanout"
        ),
        "pass": True,
        "evidence_class": "source_bound_analytical_conservation_model",
        "source_identities": sources,
        "hardware_facts": {
            "sms": SMS,
            "portable_cluster_blocks": PORTABLE_CLUSTER_BLOCKS,
            "shared_memory_per_sm_kib": 228,
            "shared_memory_per_block_kib": 227,
            "l2_mib": 50,
            "hbm_bandwidth_gb_s_vendor_reported": 4800,
            "fp8_tflops_vendor_reported": 1979,
            "official_cluster_scope": (
                "DSM is visible only to blocks in one co-scheduled cluster; "
                "portable maximum cluster size is eight blocks."
            ),
            "official_sources": [
                "https://docs.nvidia.com/cuda/archive/12.5.0/cuda-c-programming-guide/index.html#thread-block-clusters",
                "https://docs.nvidia.com/cuda/archive/13.1.0/cuda-c-programming-guide/index.html#distributed-shared-memory",
            ],
        },
        "consumer_trace": {
            "python_symbol": (
                "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm"
            ),
            "entry": "sgl_kernel::fp8_scaled_mm",
            "sm90_entry": "cutlass_scaled_mm_sm90_fp8",
            "sm90_dispatch": "cutlass_gemm_sm90_fp8_dispatch",
            "mainloop_argument": (
                "CUTLASS MainloopArguments receives global mat_a/mat_b pointers"
            ),
            "activation_layout": "row-major [M,5376], E4M3FN",
            "weight_layout": "column-major [5376,16384], E4M3FN",
            "activation_scale": "contiguous FP32 [M,1]",
            "weight_scale": "contiguous FP32 [1,16384]",
            "output": "row-major BF16 [M,16384]",
            "output_n_tile": N_TILE,
            "k_tile": K_TILE,
            "output_n_tiles": N // N_TILE,
        },
        "shapes": shapes,
        "absolute_incremental_ceiling": {
            "basis": (
                "derived from the prior rejected-source producer median; "
                "mechanism upper bound only, not corrected-source timing"
            ),
            "producer_m32_median_ms": prior_candidate_producer_ms_m32,
            "if_entire_producer_became_free_seconds_per_request": (
                absolute_ceiling_seconds
            ),
            "fraction_of_qualified_denominator": (
                absolute_ceiling_seconds / QUALIFIED_SECONDS
            ),
            "candidate_does_not_reach_bound": (
                "Every nonmaterialized legal decomposition retains and "
                "duplicates producer work rather than making it free."
            ),
        },
        "decision": {
            "pinned_consumer_direct_handoff": (
                "physically unavailable: cluster 1x1x1 and global-pointer "
                "mainloop arguments provide no producer/consumer channel"
            ),
            "single_cluster": (
                "falsified by occupancy/work depth: eight CTAs cover 256 "
                "N tiles only by executing 32 tiles each, versus two stock waves"
            ),
            "bounded_recomputation": (
                "falsified by fan-out: group sizes 1/2/4/8 require "
                "256/128/64/32 exact producer copies"
            ),
            "concurrency_parity_cluster": (
                "falsified for the fixed c32 mechanism: 16 eight-CTA clusters "
                "retain two N-tile slots but require 16 producer copies, four "
                "serial exact row rounds per CTA at M=32, at least three "
                "cluster-wide phase barriers, 21,504 persistent activation "
                "bytes per block (87.5% of one M=32 A/B stage payload), and "
                "DSM-to-local staging while leaving all 84 MiB of QKV weight "
                "traffic and WGMMA work intact"
            ),
            "materialized_control": (
                "retained as the only source-complete decomposition; its "
                "corrected target-H200 result remains owned by the separately "
                "funded exact-order project"
            ),
        },
        "smallest_h200_call_that_would_change_decision": {
            "prerequisite": (
                "a complete custom SM90a consumer implementing the exact "
                "16-cluster x 8-CTA DSM path; no such source is justified by "
                "this negative"
            ),
            "shape": [32, K, N],
            "control": (
                "corrected exact-order materialized producer plus pinned "
                "fp8_scaled_mm"
            ),
            "candidate": (
                "16 clusters x 8 CTAs, two 64-column N tiles per CTA, "
                "cluster-distributed exact producer bytes"
            ),
            "required_evidence": [
                "exact activation and FP32 scale bytes",
                "exact complete BF16 QKV output bytes",
                "candidate symbol and cluster launch proof",
                "registers, shared memory, spills, cluster occupancy",
                "at least three alternating warm medians for M=32",
            ],
            "decision_change": (
                "reopen only if the candidate median is strictly below the "
                "contemporaneous corrected materialized control"
            ),
        },
        "scope_limits": {
            "gpu_used": False,
            "cuda_invoked": False,
            "bench_claimed": False,
            "provider_mutated": False,
            "timing_claim": False,
            "m1_tail_only": (
                "M=1 has one row round but still needs 16 cluster-local copies; "
                "it does not rescue the fixed-c32 endpoint mechanism."
            ),
        },
    }
    atomic(args.output, result)
    atomic(args.opportunities, opportunity_register())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
