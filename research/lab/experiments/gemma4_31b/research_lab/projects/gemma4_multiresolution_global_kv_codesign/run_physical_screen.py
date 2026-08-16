#!/usr/bin/env python3
"""Trace-bound physical discriminator for multi-resolution global KV."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from multiresolution_global_kv import (
    COMPACT_TILE_TOKENS,
    QUERY_BLOCK_TOKENS,
    fixture,
)


PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
CONFIG = (
    PROJECTS / "gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json"
)
TRACE = (
    PROJECTS
    / "gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/"
    "exact_c32_profile.trace.json.gz"
)
GEMMA_SOURCE = (
    PROJECTS
    / "gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/upstream/"
    "gemma4_causal.py"
)
BACKEND_SOURCE = (
    PROJECTS
    / "gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/upstream/"
    "triton_backend.py"
)
KERNEL_SOURCE = (
    PROJECTS
    / "gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/upstream/"
    "extend_attention.py"
)
SUBTYPE_MAP = (
    PROJECTS
    / "gemma4_h200_v0513_fp8_qkv_residual_profile/ATTENTION_SUBTYPE_MAP.json"
)
CANDIDATE = PROJECT / "multiresolution_global_kv.py"
OUTPUT = PROJECT / "MULTIRESOLUTION_GLOBAL_KV_PHYSICAL_SCREEN.json"

EXPECTED = {
    CONFIG: "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    TRACE: "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b",
    GEMMA_SOURCE: "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
    BACKEND_SOURCE: "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    KERNEL_SOURCE: "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
    SUBTYPE_MAP: "554dd2c277762b07f4ae9e38057779ecf2ea810bbd5e78205eb6735567f51d2c",
}

BASELINE_SECONDS = 0.625149101968745
TARGET_SECONDS = 0.500119281574996
PROFILE_WINDOW_US = 2_375_141.908203125
PROMPT_TOKENS = 4_214
OUTPUT_TOKENS = 358
CACHED_PREFIX_TOKENS = 535
REQUESTS = 32
VERIFY_DEPTH = 12
VERIFY_ROWS = REQUESTS * VERIFY_DEPTH
GLOBAL_LAYERS = 10
LOCAL_LAYERS = 50
BLOCK_N = 64
BASELINE_PREFIX_TILES = math.ceil(PROMPT_TOKENS / BLOCK_N)
BASELINE_CURRENT_TILES = math.ceil(VERIFY_DEPTH / BLOCK_N)
BASELINE_TILES = BASELINE_PREFIX_TILES + BASELINE_CURRENT_TILES
H200_HBM_BYTES_PER_SECOND = 4_800_000_000_000.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bind_inputs() -> list[dict[str, Any]]:
    rows = []
    for path, expected in EXPECTED.items():
        observed = sha256(path)
        if observed != expected:
            raise RuntimeError(f"bound_input_mismatch:{path}:{observed}")
        rows.append(
            {
                "path": str(path.relative_to(PROJECTS)),
                "sha256": observed,
                "expected_sha256": expected,
                "match": True,
            }
        )
    return rows


def trace_attribution() -> dict[str, Any]:
    with gzip.open(TRACE, "rt", encoding="utf-8") as handle:
        trace = json.load(handle)
    rows = sorted(
        (
            event
            for event in trace["traceEvents"]
            if event.get("ph") == "X"
            and event.get("cat") == "kernel"
            and event.get("name") == "_fwd_kernel"
        ),
        key=lambda event: event["ts"],
    )
    if len(rows) != 900:
        raise RuntimeError(f"unexpected_attention_calls:{len(rows)}")

    local = [
        event
        for event in rows
        if event.get("args", {}).get("shared memory") == 81_920
    ]
    global_rows = [
        event
        for event in rows
        if event.get("args", {}).get("shared memory") == 102_400
    ]
    if len(local) != 750 or len(global_rows) != 150:
        raise RuntimeError("attention_subtype_count_mismatch")
    symbols = [
        "G" if event.get("args", {}).get("shared memory") == 102_400 else "L"
        for event in rows
    ]
    expected_cycle = list("LLLLLG" * 10)
    cycles = [symbols[index : index + 60] for index in range(0, len(symbols), 60)]
    if len(cycles) != 15 or any(cycle != expected_cycle for cycle in cycles):
        raise RuntimeError("layer_order_trace_join_failed")

    def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
        durations = [float(event["dur"]) for event in events]
        first = events[0]["args"]
        return {
            "calls": len(events),
            "summed_us": sum(durations),
            "minimum_us": min(durations),
            "maximum_us": max(durations),
            "grid": first["grid"],
            "block": first["block"],
            "registers_per_thread": first["registers per thread"],
            "dynamic_shared_memory_bytes": first["shared memory"],
        }

    local_result = summarize(local)
    global_result = summarize(global_rows)
    return {
        "captured_cycles": 15,
        "phase": "TARGET_VERIFY",
        "query_rows_per_cycle": VERIFY_ROWS,
        "query_rows_per_request": VERIFY_DEPTH,
        "source_consumer": (
            "TritonAttnBackend.forward_extend -> "
            "sglang.srt.layers.attention.triton_ops.extend_attention._fwd_kernel"
        ),
        "join_evidence": {
            "layer_order_per_cycle": "LLLLLG" * 10,
            "all_cycles_match": True,
            "shape_discriminator": (
                "Pinned source selects BLOCK_M=64 and 81,920 B shared memory for "
                "Lq=Lv=256 local-window calls; Lq=Lv=512 global calls select "
                "BLOCK_M=32 and 102,400 B. Both trace signatures share the same "
                "(32,32,1) grid because each request has 12 query rows."
            ),
            "configuration_layers": {
                "sliding_attention": LOCAL_LAYERS,
                "full_attention": GLOBAL_LAYERS,
                "order": "five local then one global",
            },
        },
        "local_sliding_extend": {
            **local_result,
            "layers_per_cycle": LOCAL_LAYERS,
            "q_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "exact_window_tokens": 1_024,
        },
        "global_extend": {
            **global_result,
            "layers_per_cycle": GLOBAL_LAYERS,
            "q_heads": 32,
            "kv_heads": 4,
            "head_dim": 512,
            "prefix_positions": PROMPT_TOKENS,
            "current_positions": VERIFY_DEPTH,
            "baseline_block_n_tiles": BASELINE_TILES,
        },
        "total_attention_summed_us": local_result["summed_us"]
        + global_result["summed_us"],
        "global_fraction_of_profile_window": (
            global_result["summed_us"] / PROFILE_WINDOW_US
        ),
    }


def source_audit() -> dict[str, bool]:
    candidate = CANDIDATE.read_text()
    gemma = GEMMA_SOURCE.read_text()
    backend = BACKEND_SOURCE.read_text()
    kernel = KERNEL_SOURCE.read_text()
    checks = {
        "pinned_post_rope_key_producer": (
            "q, k = self.rotary_emb(positions, q, k" in gemma
        ),
        "pinned_real_attention_call": "attn_output = self.attn(" in gemma,
        "pinned_extend_consumer": "self.extend_attention_fwd(" in backend,
        "pinned_decode_consumer": "self.decode_attention_fwd(" in backend,
        "pinned_local_window_dispatch": (
            "layer.sliding_window_size is not None" in backend
        ),
        "pinned_online_softmax_prefix": (
            "acc = acc * re_scale[:, None] + tl.dot(p, v) * v_scale" in kernel
        ),
        "candidate_incremental_committed_state": (
            "class IncrementalGlobalSummaryState" in candidate
            and "def append_committed(" in candidate
        ),
        "candidate_post_rope_summary": "post_rope_k" in candidate,
        "candidate_request_position_guard": (
            "summary_request_ownership_or_position_mismatch" in candidate
        ),
        "candidate_information_count_in_logits": (
            "counts.float().log()" in candidate and "tl.log(counts)" in candidate
        ),
        "candidate_causal_summary_end": (
            "causal_ends" in candidate and "<= query_positions" in candidate
        ),
        "candidate_real_value_consumer": (
            'torch.einsum("qhgk,khd->qhgd"' in candidate
            and "output = tl.dot(" in candidate
        ),
        "candidate_fused_global_kernel": (
            "def _compact_global_attention_kernel(" in candidate
        ),
        "candidate_prefill_entry": "def forward_extend(" in candidate,
        "candidate_target_verify_entry": (
            '"target_verify" if forward_mode == "TARGET_VERIFY"' in candidate
        ),
        "candidate_decode_entry": "def forward_decode(" in candidate,
        "candidate_local_fail_closed": (
            "local_attention_must_use_stock_consumer" in candidate
        ),
        "candidate_protected_overflow_fallback_boundary": (
            "protected_position_overflow" in candidate
        ),
        "candidate_compact_overflow_fallback_boundary": (
            "compact_tile_overflow" in candidate
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"source_path_audit_failed:{checks}")
    return checks


def compact_entries(
    block_tokens: int,
    recent_tokens: int,
    protected_tokens: int,
    query_tokens: int,
    query_start: int = PROMPT_TOKENS,
) -> int:
    old_end = max(0, query_start - recent_tokens)
    summaries = math.ceil(old_end / block_tokens)
    return summaries + protected_tokens + recent_tokens + query_tokens


def physical_cost(
    attribution: dict[str, Any],
    *,
    block_tokens: int = 512,
    recent_tokens: int = 8,
    protected_tokens: int = 8,
    fixed_overhead_us: float = 110.0,
    fallback_rate: float = 0.0,
) -> dict[str, Any]:
    global_us_per_cycle = attribution["global_extend"]["summed_us"] / 15
    max_phase_entries = compact_entries(
        block_tokens,
        recent_tokens,
        protected_tokens,
        QUERY_BLOCK_TOKENS,
    )
    target_verify_entries = compact_entries(
        block_tokens,
        recent_tokens,
        protected_tokens,
        VERIFY_DEPTH,
    )
    tiles = math.ceil(max_phase_entries / COMPACT_TILE_TOKENS)

    # The fused mixed-source tile is charged at 1.5x the exact trace's
    # per-BLOCK_N work. This retains query/output work and penalizes gather
    # irregularity rather than assuming ideal linear scaling.
    attention_us = (
        global_us_per_cycle / BASELINE_TILES * tiles * 1.5
    )

    # Worst-case charge all 384 speculative rows as if committed.  The real
    # target path commits fewer. Bytes include BF16 K/V producer reads, FP32
    # accumulator RMW, block snapshots, and compact BF16 K/V materialization.
    input_bytes = VERIFY_ROWS * GLOBAL_LAYERS * 4 * 512 * 2 * 2
    accumulator_rmw_bytes = VERIFY_ROWS * GLOBAL_LAYERS * 4 * 512 * 2 * 4 * 2
    snapshot_bytes = REQUESTS * GLOBAL_LAYERS * 4 * 512 * 2 * 2
    compact_bytes = (
        REQUESTS
        * target_verify_entries
        * GLOBAL_LAYERS
        * 4
        * 512
        * 2
        * 2
    )
    summary_bytes = (
        input_bytes + accumulator_rmw_bytes + snapshot_bytes + compact_bytes
    )
    summary_us = (
        summary_bytes / H200_HBM_BYTES_PER_SECOND * 1e6 * 3.0
    )
    candidate_us = attention_us + summary_us + fixed_overhead_us
    candidate_ratio = candidate_us / global_us_per_cycle
    candidate_ratio_with_fallback = candidate_ratio + fallback_rate * (
        1.0 - candidate_ratio
    )
    global_fraction = attribution["global_fraction_of_profile_window"]
    service = BASELINE_SECONDS * (
        1.0 - global_fraction * (1.0 - candidate_ratio_with_fallback)
    )
    return {
        "summary_block_tokens": block_tokens,
        "recent_exact_tokens": recent_tokens,
        "protected_exact_tokens": protected_tokens,
        "query_block_tokens": QUERY_BLOCK_TOKENS,
        "target_verify_tokens": VERIFY_DEPTH,
        "max_compact_entries_all_claimed_phases": max_phase_entries,
        "target_verify_compact_entries": target_verify_entries,
        "compact_tiles": tiles,
        "baseline_tiles": BASELINE_TILES,
        "attention_cost_us_per_trace_cycle": attention_us,
        "summary_and_materialization_bytes_per_trace_cycle": summary_bytes,
        "summary_cost_us_per_trace_cycle": summary_us,
        "summary_cost_model": (
            "3x impossible H200 4.8 TB/s bandwidth floor; worst-case all "
            "speculative rows committed"
        ),
        "fixed_overhead_us_per_trace_cycle": fixed_overhead_us,
        "fixed_overhead_components_us": {
            "graph_variant_dispatch": 25.0,
            "request_owner_and_position_validation": 25.0,
            "compact_page_metadata": 20.0,
            "stream_ordering": 25.0,
            "fallback_predicate": 15.0,
        },
        "candidate_global_us_per_trace_cycle": candidate_us,
        "baseline_global_us_per_trace_cycle": global_us_per_cycle,
        "retained_global_fraction": candidate_ratio,
        "fallback_rate": fallback_rate,
        "retained_global_fraction_with_fallback": candidate_ratio_with_fallback,
        "derived_service_seconds_per_request": service,
        "target_margin_seconds_per_request": TARGET_SECONDS - service,
        "target_reached": service <= TARGET_SECONDS,
    }


def main() -> None:
    inputs = bind_inputs()
    config = json.loads(CONFIG.read_text())["text_config"]
    if not (
        config["num_hidden_layers"] == 60
        and config["hidden_size"] == 5_376
        and config["sliding_window"] == 1_024
        and config["num_attention_heads"] == 32
        and config["num_key_value_heads"] == 16
        and config["num_global_key_value_heads"] == 4
        and config["head_dim"] == 256
        and config["global_head_dim"] == 512
    ):
        raise RuntimeError("exact_model_geometry_mismatch")

    attribution = trace_attribution()
    audit = source_audit()
    information_fixture = fixture()
    if information_fixture["all_positions_once"] is not True:
        raise RuntimeError("information_path_fixture_failed")

    selected = physical_cost(attribution)
    required_fraction = (BASELINE_SECONDS - TARGET_SECONDS) / BASELINE_SECONDS
    zero_global_service = BASELINE_SECONDS * (
        1.0 - attribution["global_fraction_of_profile_window"]
    )
    maximum_retained_global_fraction = 1.0 - (
        required_fraction / attribution["global_fraction_of_profile_window"]
    )
    if not selected["target_reached"]:
        classification = "typed_none"
        reason = "target_failure_after_complete_global_consumer_accounting"
    else:
        classification = "source_complete_physical_candidate"
        reason = None

    geometry_sensitivity = [
        physical_cost(
            attribution,
            block_tokens=block,
            recent_tokens=recent,
            protected_tokens=protected,
        )
        for block, recent, protected in (
            (256, 8, 8),
            (512, 0, 0),
            (512, 8, 0),
            (512, 8, 8),
            (512, 16, 8),
            (512, 8, 16),
            (1_024, 8, 8),
        )
    ]
    fallback_sensitivity = [
        physical_cost(attribution, fallback_rate=rate)
        for rate in (0.0, 0.0005, 0.001, 0.005, 0.01)
    ]
    fixed_floor_sensitivity = [
        physical_cost(attribution, fixed_overhead_us=floor)
        for floor in (0.0, 55.0, 110.0, 150.0, 220.0)
    ]
    selected_ratio = selected["retained_global_fraction"]
    maximum_fallback_rate = max(
        0.0,
        (maximum_retained_global_fraction - selected_ratio)
        / (1.0 - selected_ratio),
    )

    result = {
        "schema_version": 1,
        "classification": classification,
        "typed_none_reason": reason,
        "question": (
            "Can old global K/V alone be summarized while preserving every "
            "token, layer, full width, and exact local window and reach "
            f"{TARGET_SECONDS} s/request?"
        ),
        "bound_inputs": {
            "checkpoint_identity": (
                "google/gemma-4-31B-it@"
                "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
            ),
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "files": inputs,
        },
        "workload": {
            "concurrency": REQUESTS,
            "prompt_tokens_per_request": PROMPT_TOKENS,
            "output_tokens_per_request": OUTPUT_TOKENS,
            "cached_prefix_tokens_per_request": CACHED_PREFIX_TOKENS,
            "verification_depth": VERIFY_DEPTH,
            "verification_rows": VERIFY_ROWS,
        },
        "geometry": {
            "layers": 60,
            "local_layers": LOCAL_LAYERS,
            "global_layers": GLOBAL_LAYERS,
            "hidden_size": 5_376,
            "query_heads": 32,
            "local_kv_heads": 16,
            "global_kv_heads": 4,
            "local_head_dim": 256,
            "global_head_dim": 512,
            "local_window_tokens": 1_024,
        },
        "trace_attribution": attribution,
        "implemented_mechanism": {
            "source": CANDIDATE.name,
            "source_sha256": sha256(CANDIDATE),
            "runner": Path(__file__).name,
            "runner_sha256": sha256(Path(__file__)),
            "source_path_audit": audit,
            "producer": (
                "Post-RMSNorm, post-RoPE global K and post-RMSNorm V are "
                "accumulated once per committed request/layer token in FP32."
            ),
            "representation": (
                "Aligned 512-token summaries plus one partial summary; up to "
                "8 protected positions, 8 recent positions, and the current "
                "32-row query block remain exact."
            ),
            "consumer": (
                "One fused grouped-query attention tile loads compact K/V, "
                "adds log(summary_count) inside logits, applies causal-end "
                "masks, and consumes all compact V through online attention."
            ),
            "phases": {
                "ordinary_prefill": "forward_extend(..., forward_mode!=TARGET_VERIFY)",
                "target_verification": "forward_extend(..., forward_mode=TARGET_VERIFY)",
                "ordinary_decode": "forward_decode(...)",
            },
            "local_path": (
                "Fail-closed at the candidate entry; every sliding layer stays "
                "on the pinned exact 1,024-token stock consumer."
            ),
            "request_ownership": (
                "Incremental state is request-and-layer owned; committed "
                "position must equal query_start. Slot reuse, shrink, or "
                "reordering mismatches fail to stock fallback."
            ),
            "information_path_fixture": information_fixture,
        },
        "information_path_proof": {
            "every_token_once": True,
            "summary_partition": (
                "Every old non-protected position belongs to exactly one "
                "nonempty aligned/partial summary."
            ),
            "protected_positions": (
                "Excluded from summaries and supplied exactly, avoiding "
                "double counting."
            ),
            "recent_and_current_positions": "Supplied exactly and causally masked.",
            "rope_semantics": (
                "Summaries average already-RoPE-applied K; no invented summary "
                "position is re-rotated. Causal_end is mask metadata only."
            ),
            "softmax_semantics": (
                "log(contributor_count) enters the real attention logits; "
                "summary V reaches the output accumulator."
            ),
            "intervention_class": "intentional_model_semantics_change",
            "quality_claimed": False,
        },
        "physical_accounting": {
            "locked_baseline_seconds_per_request": BASELINE_SECONDS,
            "target_seconds_per_request": TARGET_SECONDS,
            "required_reduction_fraction": required_fraction,
            "impossible_zero_global_cost_seconds_per_request": zero_global_service,
            "maximum_retained_global_fraction": maximum_retained_global_fraction,
            "selected": selected,
            "unrelated_savings_credited": [],
            "excluded": [
                "prompt-state compaction",
                "late GEMM-row removal",
                "local-attention savings",
                "layer, token, width, parameter, or vocabulary deletion",
                "allocator-capacity-only credit",
            ],
        },
        "decision": {
            "target_reached": selected["target_reached"],
            "derived_service_seconds_per_request": selected[
                "derived_service_seconds_per_request"
            ],
            "target_margin_seconds_per_request": selected[
                "target_margin_seconds_per_request"
            ],
            "maximum_fallback_rate_before_target_failure": maximum_fallback_rate,
            "interpretation": (
                "The route clears the locked bound only while every claimed "
                "phase stays within one 64-key tile. The margin is narrow and "
                "is not a target-GPU or quality result."
            ),
        },
        "sensitivities": {
            "geometry": geometry_sensitivity,
            "fallback": fallback_sensitivity,
            "non_scaling_floor": fixed_floor_sensitivity,
            "verification_depth": {
                "12": "37 compact entries in the locked trace",
                "32": "57 compact entries; still one tile",
                "33_or_more": (
                    "split into 32-row query blocks; no query block may exceed "
                    "64 compact entries"
                ),
            },
        },
        "limitations": [
            "No checkpoint bytes, GPU, provider, training, or broad quality evaluation were used.",
            "The fused Triton path is source-complete but was not compiled or timed because the coordinator has neither PyTorch nor an authorized GPU.",
            "The service figure is a conservative trace-scaled physical screen, not transferable target-GPU endpoint evidence.",
            "Any fallback above the reported threshold, a second compact tile, or larger non-scaling overhead invalidates the target.",
            "Protected/tool positions beyond eight fall back; later tool-call calibration must measure that rate.",
            "Quality recovery requires distillation or training and GPQA-Diamond, TauBench, tool-call, long-context retrieval, and exact fallback evaluation.",
        ],
        "quality_recovery_path": [
            "distill per-layer summary K/V behavior from the unchanged full global consumer",
            "calibrate protected system/tool spans and fallback rate",
            "run target-GPU component correctness and profiler-off timing",
            "run the locked c32 endpoint without prompt-state savings",
            "only then run GPQA-Diamond, TauBench, tool calls, and long-context retrieval",
        ],
        "resource_use": {
            "actual_spend_usd": 0.0,
            "checkpoint_downloaded": False,
            "gpu_claimed": False,
            "provider_contacted": False,
        },
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
