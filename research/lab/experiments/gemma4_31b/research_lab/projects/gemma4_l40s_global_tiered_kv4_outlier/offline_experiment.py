#!/usr/bin/env python3
"""Generate fresh D512 numerical, ownership, memory, and physical evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from global_tiered_kv4_reference import (
    GROUPS,
    HEAD_DIM,
    OLD_VECTOR_BYTES,
    OUTLIERS,
    RECENT_TOKENS,
    bf16_round,
    decode_old_vector,
    dense_attention_reference,
    e5m2_decode,
    e5m2_encode,
    encode_old_vector,
    error_metrics,
    mixed_tier_paged_attention,
    produce_cache,
)


SEED = 20260727
CONCURRENCY = 32
KV_HEADS = 4
QUERY_HEADS = 32
GLOBAL_LAYERS = 10
PHYSICAL_CAPACITY = 129_688
PEAK_PHYSICAL_ROWS = 129_687
RECENT_CAPACITY = CONCURRENCY * RECENT_TOKENS + 2048
OLD_CAPACITY = PEAK_PHYSICAL_ROWS - CONCURRENCY * RECENT_TOKENS
BASELINE_GLOBAL_BYTES = 5_312_020_480
LOCAL_STATIC_REQUIRED_LOWER = 45_077_378_048
LOCAL_STATIC_REQUIRED_UPPER = 46_028_104_408
LOCAL_GLOBAL_PAYLOAD = 5_311_979_520
LOCAL_GLOBAL_PADDING = 20_480
DYNAMIC_RESERVE = 7_245_869_876
PHYSICAL_BYTES = 48_305_799_168
STATIC_LIMIT = 41_059_929_292


def vector_evidence(rng: np.random.Generator) -> dict[str, Any]:
    count = 2048
    source = rng.standard_normal((count, HEAD_DIM), dtype=np.float32)
    source *= rng.uniform(0.04, 1.5, (count, 1)).astype(np.float32)
    rows = np.arange(count)
    for group in range(GROUPS):
        channels = group * 64 + (rows * (17 + group) + 3 * group) % 64
        source[rows, channels] += np.where(
            (rows + group) % 2, -1.0, 1.0
        ) * rng.uniform(5.0, 14.0, count)
    source[0] = 0.0
    source[1] = np.ldexp(np.ones(HEAD_DIM, np.float32), -20)
    source[2, ::2] = 57344.0
    source[2, 1::2] = -57344.0
    source = bf16_round(source)
    base = np.empty_like(source)
    corrected = np.empty_like(source)
    saturation_count = 0
    selected = np.zeros(HEAD_DIM, np.int64)
    uniqueness = True
    deterministic = True
    for row_index in range(count):
        first = encode_old_vector(source[row_index])
        second = encode_old_vector(source[row_index])
        deterministic &= bool(np.array_equal(first.bytes, second.bytes))
        uniqueness &= len(set(first.outlier_channels)) == OUTLIERS
        base[row_index] = decode_old_vector(first.bytes, corrected=False)
        corrected[row_index] = decode_old_vector(first.bytes, corrected=True)
        saturation_count += first.saturation_count
        selected[list(first.outlier_channels)] += 1
    return {
        "fixture": {
            "kind": "fresh_synthetic_checkpoint_free_bf16_d512",
            "seed": SEED,
            "vectors": count,
            "elements": int(source.size),
            "includes": [
                "zero",
                "tiny",
                "alternating_e5m2_extreme",
                "eight_group_distributed_outliers",
            ],
        },
        "base_only": error_metrics(source, base),
        "residual_corrected": error_metrics(source, corrected),
        "deterministic_bytes": deterministic,
        "outlier_indices_unique": uniqueness,
        "outlier_selection_min_channel_count": int(selected.min()),
        "outlier_selection_max_channel_count": int(selected.max()),
        "int4_saturation_count": saturation_count,
        "int4_saturation_fraction": saturation_count / source.size,
    }


def full_history_evidence(rng: np.random.Generator) -> dict[str, Any]:
    tokens = 4572
    positions = np.arange(tokens, dtype=np.int64)
    owners = np.zeros(tokens, dtype=np.int32)
    keys = rng.standard_normal((tokens, KV_HEADS, HEAD_DIM), dtype=np.float32) * 0.32
    values = (
        rng.standard_normal((tokens, KV_HEADS, HEAD_DIM), dtype=np.float32) * 0.28
    )
    token_grid, head_grid = np.indices((tokens, KV_HEADS))
    signs = np.where((token_grid + head_grid) % 2, -1.0, 1.0)
    for group in range(GROUPS):
        key_channel = (
            group * 64 + token_grid * (11 + group) + head_grid * 7 + group
        ) % HEAD_DIM
        value_channel = (
            group * 64 + token_grid * (19 + group) + head_grid * 5 + 2 * group
        ) % HEAD_DIM
        keys[token_grid, head_grid, key_channel] += signs * (5.0 + 0.25 * group)
        values[token_grid, head_grid, value_channel] -= signs * (
            4.0 + 0.20 * group
        )
    keys = bf16_round(keys)
    values = bf16_round(values)
    cache = produce_cache(
        keys,
        values,
        owners=owners,
        positions=positions,
        transition_from_e5m2_at_or_after=3191,
    )
    query = bf16_round(
        rng.standard_normal((2, QUERY_HEADS, HEAD_DIM), dtype=np.float32) * 0.18
    )
    request_slots = [np.concatenate([np.arange(tokens), np.asarray([-1])])]
    common = {
        "q_request": np.asarray([0, 0], np.int32),
        "q_position": np.asarray([4214, 4571], np.int64),
        "owners": owners,
        "positions": positions,
        "request_slots": request_slots,
    }
    high_precision = dense_attention_reference(
        query, keys=keys, values=values, **common
    )
    current_e5m2 = dense_attention_reference(
        query, keys=keys, values=values, e5m2_baseline=True, **common
    )
    candidate = mixed_tier_paged_attention(
        query,
        q_request=common["q_request"],
        q_position=common["q_position"],
        cache=cache,
        request_slots=request_slots,
    )
    base_only = mixed_tier_paged_attention(
        query,
        q_request=common["q_request"],
        q_position=common["q_position"],
        cache=cache,
        request_slots=request_slots,
        corrected=False,
    )
    rows = []
    for query_index, query_position in enumerate((4214, 4571)):
        rows.append(
            {
                "query_position": query_position,
                "old_tokens": query_position + 1 - RECENT_TOKENS,
                "recent_tokens": RECENT_TOKENS,
                "transitioned_old_tokens": (
                    0 if query_position == 4214 else query_position - 4214
                ),
                "base_only_vs_high_precision": error_metrics(
                    high_precision[query_index], base_only[query_index]
                ),
                "corrected_vs_high_precision": error_metrics(
                    high_precision[query_index], candidate[query_index]
                ),
                "corrected_vs_current_e5m2": error_metrics(
                    current_e5m2[query_index], candidate[query_index]
                ),
                "output_elements_consumed": int(candidate[query_index].size),
            }
        )
    return {
        "shape": {
            "batch_executed": 1,
            "production_batch": CONCURRENCY,
            "query_heads": QUERY_HEADS,
            "kv_heads": KV_HEADS,
            "gqa_group": QUERY_HEADS // KV_HEADS,
            "head_dim": HEAD_DIM,
            "page_size": 1,
            "full_history_tokens": tokens,
        },
        "rows": rows,
        "complete_output": error_metrics(high_precision, candidate),
        "current_e5m2_comparator": error_metrics(current_e5m2, candidate),
        "producer": {
            "k_saturation_count": cache.k_saturations,
            "v_saturation_count": cache.v_saturations,
            "vectors_per_k_or_v": tokens * KV_HEADS,
            "transition_source": "positions 3191 onward pack old rows from decoded E5M2; only positions 3191..3547 are consumed as transitioned old rows at q=4571",
        },
    }


def ownership_and_transition_evidence(rng: np.random.Generator) -> dict[str, Any]:
    lengths = (1023, 1024, 1025)
    transition_rows = []
    for length in lengths:
        keys = bf16_round(
            rng.standard_normal((length, 1, HEAD_DIM), dtype=np.float32) * 0.2
        )
        values = bf16_round(
            rng.standard_normal((length, 1, HEAD_DIM), dtype=np.float32) * 0.2
        )
        cache = produce_cache(
            keys,
            values,
            owners=np.zeros(length, np.int32),
            positions=np.arange(length),
        )
        query = bf16_round(
            rng.standard_normal((1, 1, HEAD_DIM), dtype=np.float32) * 0.2
        )
        output = mixed_tier_paged_attention(
            query,
            q_request=np.asarray([0]),
            q_position=np.asarray([length - 1]),
            cache=cache,
            request_slots=[np.arange(length)],
        )
        transition_rows.append(
            {
                "length": length,
                "old_tokens": max(0, length - RECENT_TOKENS),
                "recent_tokens": min(length, RECENT_TOKENS),
                "finite": bool(np.isfinite(output).all()),
            }
        )

    tokens_per_request = 3
    total = 2 * tokens_per_request
    keys = bf16_round(
        rng.standard_normal((total, 1, HEAD_DIM), dtype=np.float32) * 0.3
    )
    values = bf16_round(
        rng.standard_normal((total, 1, HEAD_DIM), dtype=np.float32) * 0.3
    )
    owners = np.repeat(np.arange(2, dtype=np.int32), tokens_per_request)
    positions = np.tile(np.asarray([0, 1023, 1024], np.int64), 2)
    cache = produce_cache(keys, values, owners=owners, positions=positions)
    request_slots = [
        np.asarray([0, 1, 2, -1]),
        np.asarray([3, 4, 5, -1]),
    ]
    query = bf16_round(
        rng.standard_normal((2, 2, HEAD_DIM), dtype=np.float32) * 0.2
    )
    output = mixed_tier_paged_attention(
        query,
        q_request=np.asarray([0, 1]),
        q_position=np.asarray([1024, 1024]),
        cache=cache,
        request_slots=request_slots,
    )
    ownership_rejected = False
    crossed = [request_slots[1], request_slots[0]]
    try:
        mixed_tier_paged_attention(
            query,
            q_request=np.asarray([0, 1]),
            q_position=np.asarray([1024, 1024]),
            cache=cache,
            request_slots=crossed,
        )
    except ValueError:
        ownership_rejected = True
    return {
        "transition_rows": transition_rows,
        "empty_old_tier": transition_rows[1]["old_tokens"] == 0,
        "first_old_token": transition_rows[2]["old_tokens"] == 1,
        "padded_negative_page_noop": bool(np.isfinite(output).all()),
        "request_isolation": {
            "canonical_owner_mismatch_rejected": ownership_rejected,
            "two_request_output_finite": bool(np.isfinite(output).all()),
        },
        "page_boundary_positions": [0, 63, 64, 1023, 1024, 4214, 4571],
    }


def memory_evidence() -> dict[str, Any]:
    old_payload = (
        OLD_CAPACITY
        * KV_HEADS
        * 2
        * GLOBAL_LAYERS
        * OLD_VECTOR_BYTES
    )
    recent_payload = (
        RECENT_CAPACITY * KV_HEADS * 2 * GLOBAL_LAYERS * HEAD_DIM
    )
    physical_directories = PHYSICAL_CAPACITY * 2 * 4
    free_stacks = (OLD_CAPACITY + RECENT_CAPACITY) * 4
    exact_candidate = (
        old_payload + recent_payload + physical_directories + free_stacks
    )
    saved = BASELINE_GLOBAL_BYTES - exact_candidate
    static_lower = (
        LOCAL_STATIC_REQUIRED_LOWER
        - LOCAL_GLOBAL_PAYLOAD
        - LOCAL_GLOBAL_PADDING
        + exact_candidate
    )
    allocator_rounding_upper = 8 * 2 * 1024 * 1024
    static_upper = (
        LOCAL_STATIC_REQUIRED_UPPER
        - LOCAL_GLOBAL_PAYLOAD
        - LOCAL_GLOBAL_PADDING
        + exact_candidate
        + allocator_rounding_upper
    )
    complete_lower = static_lower + DYNAMIC_RESERVE
    complete_upper = static_upper + DYNAMIC_RESERVE
    return {
        "evidence": "derived exact representation/geometry bytes plus an explicitly one-sided eight-allocation rounding envelope; inherited non-KV interval is direct-bound",
        "capacities": {
            "canonical_physical_rows_with_sentinel": PHYSICAL_CAPACITY,
            "peak_live_physical_rows": PEAK_PHYSICAL_ROWS,
            "old_rows": OLD_CAPACITY,
            "steady_recent_rows": CONCURRENCY * RECENT_TOKENS,
            "prefill_spill_rows": 2048,
            "allocated_recent_rows": RECENT_CAPACITY,
        },
        "components_bytes": {
            "old_kv_payload": old_payload,
            "recent_e5m2_kv_payload": recent_payload,
            "two_int32_physical_directories": physical_directories,
            "old_and_recent_int32_free_stacks": free_stacks,
            "candidate_exact_semantic_bytes": exact_candidate,
            "allocator_rounding_interval": {
                "lower": 0,
                "upper": allocator_rounding_upper,
                "basis": "four contiguous ten-layer payload allocations plus four metadata allocations, each charged a candidate-adverse 2 MiB",
            },
        },
        "baseline_global_e5m2_bytes": BASELINE_GLOBAL_BYTES,
        "bytes_saved_exact_before_rounding": saved,
        "saving_fraction": saved / BASELINE_GLOBAL_BYTES,
        "static_required_interval_bytes": {
            "lower": static_lower,
            "upper": static_upper,
        },
        "static_allocator_limit_bytes": STATIC_LIMIT,
        "static_allocator_deficit_interval_bytes": {
            "lower": static_lower - STATIC_LIMIT,
            "upper": static_upper - STATIC_LIMIT,
        },
        "complete_required_interval_bytes": {
            "lower": complete_lower,
            "upper": complete_upper,
        },
        "physical_bytes": PHYSICAL_BYTES,
        "physical_deficit_interval_bytes": {
            "lower": complete_lower - PHYSICAL_BYTES,
            "upper": complete_upper - PHYSICAL_BYTES,
        },
        "prior_complete_lower_deficit_bytes": 4_017_448_756,
        "lower_deficit_reduction_bytes": 4_017_448_756
        - (complete_lower - PHYSICAL_BYTES),
        "lower_deficit_reduction_fraction": 1.0
        - (complete_lower - PHYSICAL_BYTES) / 4_017_448_756,
        "complete_fit": complete_upper <= PHYSICAL_BYTES,
        "locked_request_implications": {
            "maximum_live_requests": CONCURRENCY,
            "request_rows": "canonical ReqToTokenPool ownership is unchanged; the tier directories are indexed only by canonical full physical ids",
            "prefill": "the recent arena reserves the frozen chunked-prefill-size=2048 in addition to 32 locked 1024-token tails",
            "recycling": "a physical id and its compact old/recent locations remain leased until the existing full allocator releases that id; directory generation must be cleared before reuse",
            "overflow": "fail closed before producer submission if >32 live requests, >2048 current extend tokens, or the exact old/recent free stacks are exhausted",
        },
    }


def physical_evidence() -> dict[str, Any]:
    sequence = 4571
    old_tokens = sequence - RECENT_TOKENS
    useful_flops = CONCURRENCY * QUERY_HEADS * sequence * 4 * HEAD_DIM
    baseline_unique_read = PEAK_PHYSICAL_ROWS * KV_HEADS * 2 * HEAD_DIM
    candidate_unique_read = (
        OLD_CAPACITY * KV_HEADS * 2 * OLD_VECTOR_BYTES
        + CONCURRENCY * RECENT_TOKENS * KV_HEADS * 2 * HEAD_DIM
    )
    baseline_cta_load = (
        CONCURRENCY * QUERY_HEADS * sequence * 2 * HEAD_DIM
    )
    candidate_cta_load = CONCURRENCY * QUERY_HEADS * (
        old_tokens * 2 * OLD_VECTOR_BYTES + RECENT_TOKENS * 2 * HEAD_DIM
    )
    outlier_channel_checks = (
        CONCURRENCY
        * QUERY_HEADS
        * old_tokens
        * 2
        * HEAD_DIM
        * OUTLIERS
    )
    return {
        "decode_c32_one_global_layer_at_peak": {
            "sequence_tokens_per_request": sequence,
            "old_tokens_per_request": old_tokens,
            "recent_tokens_per_request": RECENT_TOKENS,
            "useful_attention_flops": useful_flops,
            "unique_physical_kv_read_bytes": {
                "current_e5m2": baseline_unique_read,
                "candidate": candidate_unique_read,
                "reduction": baseline_unique_read - candidate_unique_read,
                "reduction_fraction": 1.0
                - candidate_unique_read / baseline_unique_read,
            },
            "cta_issued_kv_load_byte_upper": {
                "current_e5m2": baseline_cta_load,
                "candidate": candidate_cta_load,
                "semantics": "source-level upper assuming every query-head CTA reloads its GQA K/V rows from below L2",
            },
            "arithmetic_intensity_useful_flop_per_unique_kv_byte": {
                "current_e5m2": useful_flops / baseline_unique_read,
                "candidate": useful_flops / candidate_unique_read,
            },
            "outlier_channel_comparisons_upper": outlier_channel_checks,
            "grid_ctas": CONCURRENCY * QUERY_HEADS,
            "sm89_sms": 142,
            "grid_waves_one_cta_per_sm": CONCURRENCY * QUERY_HEADS / 142,
        },
        "decode_producer_per_layer_per_forward": {
            "new_recent_e5m2_write_bytes": CONCURRENCY
            * KV_HEADS
            * 2
            * HEAD_DIM,
            "retiring_recent_e5m2_read_bytes": CONCURRENCY
            * KV_HEADS
            * 2
            * HEAD_DIM,
            "retiring_old_kv4_write_bytes": CONCURRENCY
            * KV_HEADS
            * 2
            * OLD_VECTOR_BYTES,
            "retiring_vectors": CONCURRENCY * KV_HEADS * 2,
            "group64_second_max_reductions_per_retiring_vector": GROUPS,
            "deterministic_residual_selections_per_retiring_vector": OUTLIERS,
        },
        "source_resource_bounds": {
            "consumer_threads_per_cta": HEAD_DIM,
            "consumer_static_shared_bytes": HEAD_DIM * 4 + 3 * 4,
            "producer_threads_per_cta": HEAD_DIM,
            "producer_static_shared_bytes": HEAD_DIM * (4 + 4 + 4 + 1 + 1)
            + GROUPS * 2
            + OUTLIERS * 2
            + OUTLIERS,
            "thread_limit_blocks_per_sm_upper": 3,
            "register_thresholds": {
                "three_blocks_per_sm_if_at_most_registers_per_thread": 42,
                "two_blocks_per_sm_if_at_most_registers_per_thread": 64,
                "one_block_per_sm_if_at_most_registers_per_thread": 128,
                "evidence": "analytical from 65536 32-bit registers/SM and 512 threads/CTA; compiled registers and spills are unmeasured",
            },
            "shared_memory_limiting": False,
            "compiled_registers_spills_occupancy": "unmeasured_until_real_sm89_component",
        },
        "physical_hypothesis": {
            "hypothesis": "the one-pass mixed consumer trades nibble/outlier instructions for 29.9% fewer unique peak global K/V read bytes and no dequantized intermediate; the exact D512 grid still supplies 7.21 CTA waves",
            "prediction": "SM89 DRAM bytes fall materially while integer/conversion instructions rise; producer-plus-consumer wins only if 512-thread register pressure does not force spills that erase the byte reduction",
            "falsifier": "the real current-runtime E5M2 comparator is no slower than the full candidate producer plus mixed consumer, or compiler metadata shows decision-bearing spills/resource collapse",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rng = np.random.default_rng(SEED)
    result = {
        "schema_version": 1,
        "seed": SEED,
        "evidence_label": "measured deterministic synthetic CPU oracle and analytical exact-shape bounds; no checkpoint, CUDA, GPU, provider, or D256 numerical evidence",
        "vector": vector_evidence(rng),
        "full_history": full_history_evidence(rng),
        "ownership_and_transitions": ownership_and_transition_evidence(rng),
        "memory": memory_evidence(),
        "physical": physical_evidence(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
