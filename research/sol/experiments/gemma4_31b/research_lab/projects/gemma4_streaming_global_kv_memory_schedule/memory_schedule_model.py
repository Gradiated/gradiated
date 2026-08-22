"""Closed-form intervention memory model for the layer-local schedule."""

from __future__ import annotations

import argparse
import json
import math


H = 4
D = 512
FP32_BYTES = 4
INT32_BYTES = 4
INT64_BYTES = 8
RECENT = 8
PROTECTED = 8
STREAM_CHUNK = 8


def retained_state_bytes(tokens: int, element_bytes: int) -> dict[str, int]:
    full_summaries = tokens // 512
    return {
        "stock_exact_kv": 2 * tokens * H * D * element_bytes,
        "fp32_full_and_partial_summaries": 2
        * (full_summaries + 1)
        * H
        * D
        * FP32_BYTES,
    }


def materialization_peak_upper_bytes(
    compact_tokens: int, query_rows: int, element_bytes: int
) -> int:
    exact_entries = min(compact_tokens, PROTECTED + RECENT + query_rows)
    retained_exact_fp32_bases = 2 * exact_entries * H * D * FP32_BYTES
    partial_fp32_clone_and_average_overlap = 2 * H * D * FP32_BYTES
    stack_and_return_overlap = (
        compact_tokens * H * D * (FP32_BYTES + 2 * element_bytes)
    )
    metadata_and_indices = (
        2 * compact_tokens * INT32_BYTES
        + exact_entries * INT64_BYTES
        + RECENT * INT64_BYTES
        + query_rows * INT32_BYTES
    )
    return (
        retained_exact_fp32_bases
        + partial_fp32_clone_and_average_overlap
        + stack_and_return_overlap
        + metadata_and_indices
    )


def scenario(
    *,
    concurrency: int,
    compact_tokens: int,
    query_rows: int,
    element_bytes: int,
) -> dict[str, int]:
    returned_compact = (
        2 * compact_tokens * H * D * element_bytes
        + 2 * compact_tokens * INT32_BYTES
    )
    fresh_output = query_rows * 32 * D * element_bytes
    materialization = materialization_peak_upper_bytes(
        compact_tokens, query_rows, element_bytes
    )
    current_single = max(materialization, returned_compact + fresh_output)
    current_eager = max(
        concurrency * (returned_compact + fresh_output),
        (concurrency - 1) * (returned_compact + fresh_output) + materialization,
    )
    streamed_partial = 2 * H * D * FP32_BYTES
    streamed_running = 32 * (D + 2) * FP32_BYTES
    streamed_chunk = (
        2 * STREAM_CHUNK * H * D * element_bytes
        + 2 * STREAM_CHUNK * INT32_BYTES
    )
    streamed_conversion_upper = (
        2 * STREAM_CHUNK * H * D * element_bytes
    )
    streamed_peak = (
        streamed_partial
        + streamed_running
        + streamed_chunk
        + streamed_conversion_upper
    )
    return {
        "current_single_call_peak_upper": current_single,
        "current_eager_c32_peak_upper": current_eager,
        "proposed_streamed_layer_local_peak_upper": streamed_peak,
        "largest_proposed_explicit_allocation_upper": max(
            32 * D * FP32_BYTES,
            STREAM_CHUNK * H * D * element_bytes,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokens", type=int, default=4096)
    args = parser.parse_args()
    payload = {
        "assumptions": {
            "tokens": args.tokens,
            "element_bytes": 2,
            "global_kv_heads": H,
            "head_dim": D,
        },
        "retained_per_request_global_layer": retained_state_bytes(args.tokens, 2),
        "c1_measured_compact_26_decode": scenario(
            concurrency=1,
            compact_tokens=26,
            query_rows=1,
            element_bytes=2,
        ),
        "c32_source_cap_decode": scenario(
            concurrency=32,
            compact_tokens=64,
            query_rows=1,
            element_bytes=2,
        ),
        "c32_source_cap_prefill_or_verify": scenario(
            concurrency=32,
            compact_tokens=64,
            query_rows=32,
            element_bytes=2,
        ),
        "summary_blocks": math.floor(args.tokens / 512),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
