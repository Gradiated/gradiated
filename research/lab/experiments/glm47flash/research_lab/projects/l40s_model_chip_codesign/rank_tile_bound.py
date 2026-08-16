#!/usr/bin/env python3
"""Zero-cost rank/tile bound calibrated to the retained L40S MLA compiler results."""

from __future__ import annotations

import json
import math
from pathlib import Path


LIMIT = 101_376
STOCK_RANK = 512
STOCK_HEAD = 64
STOCK_BN = 64
STOCK_STAGES = 2
STOCK_SHARED = 159_744
STOCK_BN32_STOCK_SHARED = 89_088
STOCK_BN64_STAGE1_SHARED = 108_544
BYTES_PER_TOKEN = 47 * 2 * (STOCK_RANK + 64)
NON_KV_GIB = 10.0
DEVICE_GIB = 43.2
SPLIT_COMPONENT_REDUCTION = 0.1435
SPLIT_ENDPOINT_REDUCTION = 0.0105
SPLIT_ENDPOINT_SHARE = SPLIT_ENDPOINT_REDUCTION / SPLIT_COMPONENT_REDUCTION
ATTENTION_CRITICAL_SHARE_DIAGNOSTIC = 0.3738261181394841


def shared_envelope(rank: int, block_n: int, stages: int) -> int:
    """Conservative linear envelope through observed compiler allocations.

    The two rank-512 points are compiler observations: BN=32/stage=2 from
    the retained microbench and BN=64/stage=2 from the failed V22 launch.
    This is an admission bound, not a substitute for compiling the new source.
    """
    x = block_n * (2 * rank + 64)
    x32 = 32 * (2 * STOCK_RANK + 64)
    x64 = 64 * (2 * STOCK_RANK + 64)
    slope = (STOCK_SHARED - STOCK_BN32_STOCK_SHARED) / (x64 - x32)
    intercept = STOCK_BN32_STOCK_SHARED - slope * x32
    if stages == 2:
        value = intercept + slope * x
    elif stages == 1:
        # The retained compiler rejection at BN=64/stage=1 anchors this arm.
        s2 = intercept + slope * x
        value = s2 - (STOCK_SHARED - STOCK_BN64_STAGE1_SHARED)
    else:
        value = intercept + slope * x + (stages - 2) * (STOCK_SHARED - STOCK_BN32_STOCK_SHARED) / 2
    return int(math.ceil(value / 256.0) * 256)


def kv_gib(rank: int, concurrency: int) -> float:
    bytes_per_token = 47 * 2 * (rank + 64)
    # vLLM's fixed profile reserves 9,216 live tokens per sequence at c32
    # (18,432 16-token pages), matching the corrected campaign bound.
    live_tokens = {8: 73_728, 16: 147_456, 32: 294_912}[concurrency]
    return (bytes_per_token * live_tokens) / 2**30


def main() -> None:
    rows = []
    for rank in (512, 384, 256):
        for block_n in (32, 64):
            for stages in (1, 2):
                shared = shared_envelope(rank, block_n, stages)
                rows.append({
                    "kv_lora_rank": rank,
                    "query_width": rank + 64,
                    "value_width": rank,
                    "block_n": block_n,
                    "num_stages": stages,
                    "shared_bytes_envelope": shared,
                    "hardware_legal_envelope": shared <= LIMIT,
                    "warps": 4,
                    "blocks_per_sm_shared_only": LIMIT // shared,
                    "kv_bytes_per_token": int(BYTES_PER_TOKEN * (rank + 64) / (STOCK_RANK + 64)),
                })
    candidates = []
    for row in rows:
        if row["block_n"] == 64 and row["num_stages"] == 2 and row["hardware_legal_envelope"]:
            rank = row["kv_lora_rank"]
            reduction = 1.0 - (rank + 64) / (STOCK_RANK + 64)
            # Transfer bound uses the only scope-adjacent endpoint attribution:
            # retained split A/B, not the unscoped summed-kernel share.
            endpoint_bound = reduction * SPLIT_ENDPOINT_SHARE
            candidates.append({
                "rank": rank,
                "tile": row,
                "attention_work_reduction_proxy": reduction,
                "endpoint_transfer_bound_from_retained_split": endpoint_bound,
                "c32_kv_gib": kv_gib(rank, 32),
                "c32_conservative_headroom_gib": DEVICE_GIB - NON_KV_GIB - kv_gib(rank, 32),
                "decision_relevant": endpoint_bound >= 0.10,
            })
    result = {
        "schema_version": 1,
        "evidence_class": "derived_calibrated_proxy; no provider or GPU mutation",
        "question": "Can a tile-aligned MLA rank make BLOCK_N=64/stage=2 legal and clear the 10% endpoint-cost path?",
        "hardware": {"chip": "L40S Ada SM89", "shared_limit_bytes": LIMIT, "sm_count": 142, "register_file_32bit_per_sm": 65536},
        "source_calibration": {
            "retained_microbench": "campaign_100/allocations/nebius_l40s_mla_microbench_v23r1/summary.json",
            "stock_bn32_stage2_shared_bytes": STOCK_BN32_STOCK_SHARED,
            "failed_v22_bn64_stage2_shared_bytes": STOCK_SHARED,
            "failed_v23r1_bn64_stage1_shared_bytes": STOCK_BN64_STAGE1_SHARED,
            "unscoped_trace_share": ATTENTION_CRITICAL_SHARE_DIAGNOSTIC,
            "retained_split_component_reduction": SPLIT_COMPONENT_REDUCTION,
            "retained_split_endpoint_reduction": SPLIT_ENDPOINT_REDUCTION,
            "inferred_scope_matched_endpoint_share": SPLIT_ENDPOINT_SHARE,
        },
        "capacity_model": {"device_budget_gib": DEVICE_GIB, "conservative_non_kv_gib": NON_KV_GIB, "tokens_per_sequence": 8192, "sequences": [8, 16, 32]},
        "rows": rows,
        "legal_two_stage_block64_candidates": candidates,
        "decision": "CLOSE_MLA_RANK_TILE_LINEAGE",
        "decision_reason": "Rank 256 is the only envelope-legal two-stage BLOCK_N=64 candidate, but its retained-transfer endpoint bound is 3.25%, below the 10% gate; it makes c32 capacity plausible but does not establish c32 throughput or a cheaper-chip boundary.",
        "next_move": "Return capacity to depth or draft-head architecture; compile rank 256 only if a future independent exact-source GPU slot exists and the campaign reopens MLA.",
    }
    out = Path(__file__).with_name("RANK_TILE_BOUND.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": result["decision"], "candidates": candidates}, indent=2))


if __name__ == "__main__":
    main()
