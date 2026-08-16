#!/usr/bin/env python3
"""Deterministic source-accounting bound for Gemma 4 31B automatic prefix caching."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROMPT = 4214
OUTPUT = 358
REQUESTS = 500
GROUPS = 50
BLOCK = 16
H100_HBM_GIB = 80
GPU_UTILIZATION = 0.90
WEIGHT_GIB = 58.256
KV_BYTES_TOKEN_ALL_LAYERS = 491_520
KV_BYTES_TOKEN_FULL_LAYERS = 81_920
SLIDING_WINDOW = 1024


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_requests(prefixes: list[int], rounds_by_group: list[int], ordering: str) -> list[dict]:
    rows: list[dict] = []
    index = 0
    if ordering == "burst":
        sequence = (
            (group, repeat)
            for group, rounds in enumerate(rounds_by_group)
            for repeat in range(rounds)
        )
    else:
        sequence = (
            (group, repeat)
            for repeat in range(max(rounds_by_group))
            for group, rounds in enumerate(rounds_by_group)
            if repeat < rounds
        )
    for group, repeat in sequence:
        shared = prefixes[group]
        rows.append(
            {
                "request_id": f"{ordering}-g{group:02d}-r{repeat:02d}",
                "arrival_ordinal": index,
                "group": group,
                "warmup": repeat == 0,
                "prompt_tokens": PROMPT,
                "output_tokens": OUTPUT,
                "declared_shared_prefix_tokens": shared,
                "cacheable_prefix_tokens": shared // BLOCK * BLOCK,
                "prefix_content_sha256": digest(f"gemma4-prefix-bound-v1/group={group}/tokens={shared}"),
                "unique_suffix_content_sha256": digest(f"gemma4-prefix-bound-v1/group={group}/repeat={repeat}/suffix={PROMPT-shared}"),
            }
        )
        index += 1
    return rows


def simulate(rows: list[dict], capacity_gib: float) -> dict:
    """Content-keyed LRU. A hit exists only after an identical prefix was inserted."""
    cache: OrderedDict[str, int] = OrderedDict()
    capacity = int(capacity_gib * 1024**3)
    resident = 0
    hits = misses = evictions = saved = 0
    for row in rows:
        key = row["prefix_content_sha256"]
        tokens = row["cacheable_prefix_tokens"]
        size = tokens * KV_BYTES_TOKEN_ALL_LAYERS
        if key in cache:
            saved += cache.pop(key)
            cache[key] = tokens
            hits += 1
            continue
        misses += 1
        while cache and resident + size > capacity:
            _, old = cache.popitem(last=False)
            resident -= old * KV_BYTES_TOKEN_ALL_LAYERS
            evictions += 1
        if size <= capacity:
            cache[key] = tokens
            resident += size
    total = len(rows) * PROMPT
    return {
        "requests": len(rows), "cache_hits": hits, "cache_misses": misses,
        "evictions": evictions, "saved_prefill_tokens": saved,
        "saved_prompt_token_fraction": saved / total, "peak_cache_gib_upper_bound": min(capacity, GROUPS * max(r["cacheable_prefix_tokens"] for r in rows) * KV_BYTES_TOKEN_ALL_LAYERS) / 1024**3,
        "cache_capacity_gib": capacity_gib,
    }


def main() -> None:
    # 376 hit prefixes at 592 and 74 at 608 tokens give 267,584 cacheable tokens.
    # The five-token difference from the exact 267,589-token 12.7% target is the
    # non-cacheable tail imposed by the pinned runtime's 16-token block boundary.
    prefixes = [608] * 8 + [592] * 42
    rounds_by_group = [10] * 6 + [11] * 2 + [10] * 41 + [8]
    base = build_requests(prefixes, rounds_by_group, ordering="burst")
    churn = build_requests(prefixes, rounds_by_group, ordering="interleaved")
    conservative = build_requests([304] * GROUPS, rounds_by_group, ordering="burst")
    zero = [{**row, "declared_shared_prefix_tokens": 0, "cacheable_prefix_tokens": 0,
             "prefix_content_sha256": digest(row["request_id"])} for row in base]

    gross_headroom = H100_HBM_GIB * GPU_UTILIZATION - WEIGHT_GIB
    per_request_resident_gib = (
        (10 * PROMPT + 50 * min(PROMPT, SLIDING_WINDOW)) * 8192 / 1024**3
    )
    concurrency = {}
    for c in (1, 8, 16):
        request_gib = c * per_request_resident_gib
        cache_gib = gross_headroom - request_gib
        concurrency[str(c)] = {
            "active_request_kv_gib_derived": request_gib,
            "gross_cache_headroom_before_runtime_reservations_gib": cache_gib,
            "base_burst": simulate(base, max(0, cache_gib)),
            "churn_interleaved": simulate(churn, max(0, cache_gib)),
            "zero_reuse": simulate(zero, max(0, cache_gib)),
            "conservative_half_prefix": simulate(conservative, max(0, cache_gib)),
        }

    intended = 267_589
    achieved = sum(r["cacheable_prefix_tokens"] for r in base if not r["warmup"])
    actual_fraction = achieved / (REQUESTS * PROMPT)
    bound = {
        "schema_version": 1,
        "classification": "derived deterministic token-work and KV accounting; not endpoint timing",
        "model_and_runtime": {
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "vllm_revision": "ab0a20d15129b322f911db578b50c6b35b3167e7",
            "source_sha256": {
                "cache_config": "ee2c0db3e4e6c9e9cab33d8be566c4b8101159d36c0d3787c30d47931ee2a9a4",
                "kv_cache_utils": "87b58ceabe1fe7f1d2bbd3c259a8ef0622bc60bde22e98df953411c20f9ece0f",
            },
            "source_facts": [
                "CacheConfig.DEFAULT_BLOCK_SIZE is 16 tokens.",
                "Hybrid scheduler alignment is the LCM of KV-group block sizes; with default uniform groups it is 16 tokens.",
                "Request hashing stops before a partial final block; a caller-declared partial prefix is not a cache hit.",
            ],
        },
        "base_target": {
            "requests": REQUESTS, "prompt_tokens_each": PROMPT, "output_tokens_each": OUTPUT,
            "reported_cached_prompt_share": 0.127, "reported_cached_prompt_tokens": intended,
            "actual_cacheable_tokens": achieved, "actual_cacheable_share": actual_fraction,
            "block_rounding_loss_tokens": intended - achieved,
            "arrival_order": "50 contiguous groups: 47 groups have one warming request plus nine hits, two have ten hits, and one has seven hits; this is favourable locality, not measured traffic.",
        },
        "geometry": {
            "kv_bytes_per_token_all_60_layers": KV_BYTES_TOKEN_ALL_LAYERS,
            "kv_bytes_per_token_full_attention_10_layers": KV_BYTES_TOKEN_FULL_LAYERS,
            "derived_resident_kv_per_4214_token_request_gib": per_request_resident_gib,
            "cache_block_tokens": BLOCK,
            "cache_block_bytes_all_layers": BLOCK * KV_BYTES_TOKEN_ALL_LAYERS,
            "shared_prefix_storage_per_592_token_key_gib_all_layers": 592 * KV_BYTES_TOKEN_ALL_LAYERS / 1024**3,
            "shared_prefix_storage_per_608_token_key_gib_all_layers": 608 * KV_BYTES_TOKEN_ALL_LAYERS / 1024**3,
            "note": "All-layer prefix storage is a conservative resident upper bound. The pinned hybrid manager may free stale sliding-window gap blocks; only server metrics can establish actual allocation and eviction.",
        },
        "h100_optimistic_capacity_accounting": {
            "hbm_gib": H100_HBM_GIB, "gpu_memory_utilization": GPU_UTILIZATION,
            "bf16_weight_gib": WEIGHT_GIB, "gross_kv_and_runtime_headroom_gib": gross_headroom,
            "warning": "This is before measured vLLM activation, CUDA-graph, allocator, and server reservations; it is not an admission claim.",
        },
        "simulation": concurrency,
        "endpoint_transfer_bound": {
            "target_endpoint_cost_reduction": 0.05,
            "equation": "endpoint_reduction_upper_bound = actual_cacheable_share * hit_realization * prefill_wall_share * net_prefill_recovery_efficiency",
            "best_case_required_prefill_wall_share": 0.05 / actual_fraction,
            "conditions_to_clear_target": {
                "hit_realization": "measured cache-hit tokens / 267584 cacheable synthetic tokens; must be high enough with evictions included",
                "prefill_wall_share": "measured non-overlapping server wall-time share attributable to prefill on the same workload and concurrency",
                "net_prefill_recovery_efficiency": "measured (prefill wall time removed minus cache lookup/queueing/eviction cost) divided by prefill wall time represented by hit tokens",
                "memory_headroom": "measured free KV blocks / bytes, peak allocation, prefix-cache evictions, and preemptions; must cover the selected concurrency without reducing throughput or adding replicas",
                "queueing": "compare queue time and end-to-end latency under identical open/closed-loop arrival semantics; do not count delayed warmups as savings",
            },
            "interaction_warning": "MTP changes decode time; async scheduling and larger batches can overlap or reduce exposed prefill. Recompute the prefill_wall_share and net efficiency after either intervention; APC token savings cannot be added to their endpoint gains.",
        },
    }
    workload = {
        "schema_version": 1, "artifact": "deterministic_prefix_reuse_workload_v1",
        "seed": "sha256 labels; no random draw", "token_abstraction": "Synthetic token-ID identities represented by SHA-256 content labels; not natural-language requests and not an actual tokenizer/server capture.",
        "base_burst_requests": base, "interleaved_churn_requests": churn,
        "conservative_half_prefix_requests": conservative,
    }
    (ROOT / "PREFIX_WORKLOAD.json").write_text(json.dumps(workload, indent=2, sort_keys=True) + "\n")
    (ROOT / "PREFIX_BOUND.json").write_text(json.dumps(bound, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
