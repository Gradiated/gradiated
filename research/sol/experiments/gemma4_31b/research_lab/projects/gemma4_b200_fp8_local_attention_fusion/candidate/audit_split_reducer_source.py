#!/usr/bin/env python3
"""Bench-free source and algebra audit for the split-reducer candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge(states: list[tuple[list[float], float]]) -> tuple[list[float], float]:
    max_lse = max(lse for _, lse in states)
    weights = [2.0 ** (lse - max_lse) for _, lse in states]
    denom = sum(weights)
    out = [
        sum(state[component] * weight for (state, _), weight in zip(states, weights))
        / denom
        for component in range(len(states[0][0]))
    ]
    return out, max_lse + math.log2(denom)


def direct(logits: list[float], values: list[list[float]]) -> list[float]:
    maximum = max(logits)
    weights = [math.exp(logit - maximum) for logit in logits]
    denom = sum(weights)
    return [
        sum(value[component] * weight for value, weight in zip(values, weights))
        / denom
        for component in range(len(values[0]))
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    pinned = root / "inputs/pinned/flashinfer-0.6.6/split-reducer-source"

    decode = (pinned / "include/flashinfer/attention/decode.cuh").read_text()
    cascade = (pinned / "include/flashinfer/attention/cascade.cuh").read_text()
    stock_cache = (root / "inputs/pinned/vllm-6d4a8e6d/csrc/cache_kernels.cu").read_text()
    failed = (root / "candidate/local_paged_gqa_split_kv_fused.py").read_text()
    successor = (root / "candidate/split_reducer_src/batch_decode_kernel.cu").read_text()

    assert sha(pinned / "include/flashinfer/attention/decode.cuh") == (
        "019d673aa848a938798a2c58b34b9b5813a3f137962cbbd90ef7bd71f636f373"
    )
    assert "dim3 nblks(padded_batch_size, num_kv_heads);" in decode
    assert "const uint32_t kv_head_idx = by;" in decode
    assert "const uint32_t qo_head_idx = kv_head_idx * bdy + ty;" in decode
    assert "VariableLengthMergeStates(" in decode
    assert "st.merge(v, s, 1);" in cascade
    assert "int block_size = key_cache.size(1);" in stock_cache
    assert "int64_t page_stride = key_cache.stride(1);" in stock_cache
    assert "int64_t head_stride = key_cache.stride(2);" in stock_cache
    assert "REGISTER_OUTPUT_TRANSFORM" in failed
    assert "state.merge(value, fresh_lse, 1.f);" in successor
    assert "qo_head_idx % group_size == 0" in successor

    # The failed oracle passed [page, head, entry, dim] to an ABI indexing
    # [page, entry, head, dim].  Only diagonal (head == entry) rows coincide.
    wrong_matches = []
    wrong_mismatches = []
    for entry in range(16):
        for head in range(16):
            correct = head * 256 + entry * 4096
            failed_oracle = entry * 256 + head * 4096
            (wrong_matches if correct == failed_oracle else wrong_mismatches).append(
                [entry, head]
            )

    owner_map = [
        {
            "qo_head": qo_head,
            "kv_head": qo_head // 2,
            "cache_owner": qo_head % 2 == 0,
        }
        for qo_head in range(32)
    ]
    owner_counts = {
        kv_head: sum(
            int(row["cache_owner"] and row["kv_head"] == kv_head)
            for row in owner_map
        )
        for kv_head in range(16)
    }
    assert set(owner_counts.values()) == {1}

    # Numerically prove the reducer identity on deterministic split states.
    logits = [-1.2, 0.4, 1.1, -0.7, 0.2]
    values = [
        [0.5, -0.2, 0.1],
        [-0.3, 0.7, 0.2],
        [1.2, 0.1, -0.4],
        [0.0, -0.6, 0.8],
        [0.9, 0.3, 0.5],
    ]
    partitions = [(logits[:2], values[:2]), (logits[2:4], values[2:4])]
    partial_states = []
    for part_logits, part_values in partitions:
        part_out = direct(part_logits, part_values)
        part_max = max(part_logits)
        part_lse = (part_max + math.log(sum(math.exp(x - part_max) for x in part_logits))) / math.log(2)
        partial_states.append((part_out, part_lse))
    fresh_lse = logits[-1] / math.log(2)
    reducer_out, _ = merge(partial_states + [(values[-1], fresh_lse)])
    direct_out = direct(logits, values)
    max_error = max(abs(a - b) for a, b in zip(reducer_out, direct_out))
    assert max_error < 1e-12

    payload = {
        "schema_version": 1,
        "classification": "source_complete_split_reducer_candidate",
        "gpu_used": False,
        "provider_operations": False,
        "measured_failure_localization": {
            "cache_first_divergence": (
                "failed stock comparator supplied HND [page,head,entry,dim] "
                "directly to an append ABI indexing [page,entry,head,dim]"
            ),
            "cache_offset_matches": len(wrong_matches),
            "cache_offset_mismatches": len(wrong_mismatches),
            "cache_rows_wrong_per_request": 15,
            "output_first_divergence": (
                "failed tail OutputTransform amended tmp_v after normalization "
                "but left tmp_s as prefix-only LSE, violating the native (V,LSE) "
                "split-state pair before VariableLengthMergeStates"
            ),
        },
        "launch_mapping": {
            "grid_y": "num_kv_heads",
            "kv_head": "blockIdx.y",
            "qo_head": "kv_head * 2 + threadIdx.y",
            "director_tentative_blockidx_mapping_hypothesis": "falsified_by_pinned_source",
        },
        "successor_ownership": {
            "mapping": owner_map,
            "owners_per_kv_head": owner_counts,
            "all_kv_heads_have_exactly_one_owner": True,
        },
        "reducer_algebra": {
            "method": "merge native normalized partial V with base-2 LSE, then merge (fresh V, fresh logit*log2e)",
            "max_abs_vs_direct_softmax": max_error,
            "exact_within_fp64_test": True,
        },
        "source_hashes": {
            "decode_cuh": sha(pinned / "include/flashinfer/attention/decode.cuh"),
            "cascade_cuh": sha(pinned / "include/flashinfer/attention/cascade.cuh"),
            "pinned_manifest": sha(pinned / "MANIFEST.sha256"),
            "successor_kernel": sha(root / "candidate/split_reducer_src/batch_decode_kernel.cu"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
