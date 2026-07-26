#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from materialize_candidate import materialize
from prompt_token_compaction_runtime import (
    COMPACTION_AFTER_LAYER,
    MAX_ADDITIONAL_PROTECTED_TOKENS,
    MAX_SUMMARY_STATES,
    MIN_SUMMARY_STATES,
    OUTPUT_STATES,
    PROMPT_TOKENS,
    PROTECTED_RECENT_TOKENS,
    PROTECTED_SHARED_PREFIX_TOKENS,
)


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[6]
PROJECTS = ROOT.parent
PLACEMENT_PROJECT = PROJECTS / "gemma4_hybrid_attention_placement_codesign"
FIXED_PROJECT = PROJECTS / "gemma4_h200_ngram_fixed_m384_executor_rewrite"
CONFIG = PLACEMENT_PROJECT / "inputs/bound/config.json"
PLACEMENT = PLACEMENT_PROJECT / "PLACEMENT_SIMULATION_RESULT.json"
TRACE = FIXED_PROJECT / "inputs/trace/exact_c32_profile.trace.json.gz"
OUTPUT = ROOT / "PROMPT_STATE_MERGE_PHYSICAL_SCREEN.json"

EXPECTED_BINDINGS = {
    CONFIG: "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    PLACEMENT: "2af53085953393785204eafb2c2dd0e9d335805f8a8e5963ae46fb57ed99e40b",
    TRACE: "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b",
}

BATCH_SIZE = 32
QUALIFIED_BASELINE = 0.625149101968745
LOCKED_TARGET = 0.500119281574996
CONSERVATIVE_TARGET_PASSES = 33.3125
NONSCALING_ATTENTION_FLOOR = 0.10
NONSCALING_LINEAR_FLOOR = 0.10
OVERHEAD = {
    "hidden_state_norm_scorer": 0.0015,
    "summary_partition_and_score_normalization": 0.0015,
    "weighted_summary_construction": 0.0030,
    "hidden_position_and_metadata_gather": 0.0020,
    "tiered_kv_map_allocation_and_switch": 0.0015,
    "late_attention_metadata_rebuild": 0.0010,
    "fixed_budget_graph_variant": 0.0010,
    "synchronization_and_fragmentation_reserve": 0.0035,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bindings() -> list[dict[str, Any]]:
    rows = []
    for path, expected in EXPECTED_BINDINGS.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"binding_mismatch:{path}:{actual}:{expected}")
        rows.append(
            {
                "path": str(path.relative_to(WORKSPACE)),
                "sha256": actual,
                "match": True,
            }
        )
    return rows


def causal_pairs(length: int, window: int | None) -> int:
    if window is None or window >= length:
        return length * (length + 1) // 2
    return window * (window + 1) // 2 + (length - window) * window


def floored_scale(work_ratio: float, floor: float) -> float:
    return floor + (1.0 - floor) * work_ratio


def accounting(
    placement: dict[str, Any], keep_tokens: int
) -> dict[str, Any]:
    prefill_rows = placement["layer_cost_reconstruction"]["prefill"]["layers"]
    verify_rows = placement["layer_cost_reconstruction"]["target_verification"][
        "layers"
    ]
    prefill_baseline = 0.0
    prefill_candidate = 0.0
    for row in prefill_rows:
        attention = row["attention_kernel_seconds_per_c32_batch"] / BATCH_SIZE
        linear = (
            row[
                "flop_calibrated_attention_plus_mlp_linear_seconds_per_c32_batch"
            ]
            / BATCH_SIZE
        )
        prefill_baseline += attention + linear
        if row["layer_index"] <= COMPACTION_AFTER_LAYER:
            prefill_candidate += attention + linear
            continue
        window = 1024 if row["layer_type"] == "sliding_attention" else None
        pair_ratio = causal_pairs(keep_tokens, window) / causal_pairs(
            PROMPT_TOKENS, window
        )
        row_ratio = keep_tokens / PROMPT_TOKENS
        prefill_candidate += attention * floored_scale(
            pair_ratio, NONSCALING_ATTENTION_FLOOR
        )
        prefill_candidate += linear * floored_scale(
            row_ratio, NONSCALING_LINEAR_FLOOR
        )

    verify_baseline = 0.0
    verify_candidate = 0.0
    for row in verify_rows:
        projections_ms = sum(
            row[name]
            for name in (
                "qkv_median_us",
                "o_median_us",
                "gate_up_median_us",
                "down_median_us",
            )
        ) / 1000
        attention_ms = row["attention_candidate_ms"]
        factor = CONSERVATIVE_TARGET_PASSES / BATCH_SIZE / 1000
        verify_baseline += (projections_ms + attention_ms) * factor
        attention_scale = 1.0
        if (
            row["layer_index"] > COMPACTION_AFTER_LAYER
            and row["layer_type"] == "full_attention"
        ):
            attention_scale = floored_scale(
                keep_tokens / PROMPT_TOKENS,
                NONSCALING_ATTENTION_FLOOR,
            )
        verify_candidate += (
            projections_ms + attention_ms * attention_scale
        ) * factor

    counted_baseline = prefill_baseline + verify_baseline
    counted_candidate = prefill_candidate + verify_candidate
    credited_savings = counted_baseline - counted_candidate
    fixed_residual = QUALIFIED_BASELINE - counted_baseline
    total_overhead = sum(OVERHEAD.values())
    service = fixed_residual + counted_candidate + total_overhead
    return {
        "prefill_baseline": prefill_baseline,
        "prefill_candidate": prefill_candidate,
        "verification_baseline": verify_baseline,
        "verification_candidate": verify_candidate,
        "counted_baseline": counted_baseline,
        "counted_candidate": counted_candidate,
        "credited_savings": credited_savings,
        "fixed_residual": fixed_residual,
        "total_overhead": total_overhead,
        "service": service,
    }


def exact_removed_work(config: dict[str, Any]) -> dict[str, Any]:
    late_types = config["layer_types"][COMPACTION_AFTER_LAYER + 1 :]
    late_local_layers = late_types.count("sliding_attention")
    late_global_layers = late_types.count("full_attention")
    removed_tokens = PROMPT_TOKENS - OUTPUT_STATES
    baseline_prefill_pairs = (
        late_local_layers * causal_pairs(PROMPT_TOKENS, config["sliding_window"])
        + late_global_layers * causal_pairs(PROMPT_TOKENS, None)
    )
    candidate_prefill_pairs = (
        late_local_layers * causal_pairs(OUTPUT_STATES, config["sliding_window"])
        + late_global_layers * causal_pairs(OUTPUT_STATES, None)
    )
    local_kv_bytes = 2 * config["num_key_value_heads"] * config["head_dim"]
    global_kv_bytes = (
        2 * config["num_global_key_value_heads"] * config["global_head_dim"]
    )
    saved_kv_bytes = (
        BATCH_SIZE
        * removed_tokens
        * (
            late_local_layers * local_kv_bytes
            + late_global_layers * global_kv_bytes
        )
    )
    baseline_kv_bytes = (
        BATCH_SIZE
        * PROMPT_TOKENS
        * (
            config["layer_types"].count("sliding_attention") * local_kv_bytes
            + config["layer_types"].count("full_attention") * global_kv_bytes
        )
    )
    verification_key_positions_removed = (
        BATCH_SIZE * 12 * removed_tokens * late_global_layers
    )
    return {
        "late_local_layers": late_local_layers,
        "late_global_layers": late_global_layers,
        "prefill_gemm_rows_removed": (
            BATCH_SIZE * removed_tokens * len(late_types)
        ),
        "prefill_attention_pairs_removed_across_late_layers_per_request": (
            baseline_prefill_pairs - candidate_prefill_pairs
        ),
        "prefill_attention_pair_reduction_fraction_across_late_layers": (
            1 - candidate_prefill_pairs / baseline_prefill_pairs
        ),
        "late_layer_kv_writes_removed": (
            BATCH_SIZE * removed_tokens * len(late_types)
        ),
        "late_layer_kv_bytes_not_written_or_read_c32": saved_kv_bytes,
        "baseline_prompt_kv_bytes_c32": baseline_kv_bytes,
        "active_late_kv_working_set_reduction_fraction": saved_kv_bytes
        / baseline_kv_bytes,
        "allocator_capacity_reduction_fraction": 0.0,
        "allocator_capacity_reason": (
            "Dropped stock slots remain owned until normal request cleanup because "
            "layers 0-5 retain their full-prompt KV; no concurrency credit is taken."
        ),
        "target_verification_global_key_positions_removed_per_cycle": (
            verification_key_positions_removed
        ),
        "ordinary_decode_savings_credited": False,
    }


def schedule_sensitivity(placement: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for output_states in (1024, 1088, 1152, 1184, 1200, 1216, 1248, 1280):
        result = accounting(placement, output_states)
        rows.append(
            {
                "output_states": output_states,
                "state_fraction": output_states / PROMPT_TOKENS,
                "service_seconds_per_request": result["service"],
                "meets_target": result["service"] <= LOCKED_TARGET,
            }
        )
    return rows


def overhead_sensitivity(base_without_overhead: float) -> list[dict[str, Any]]:
    return [
        {
            "overhead_seconds_per_request": overhead,
            "service_seconds_per_request": base_without_overhead + overhead,
            "meets_target": base_without_overhead + overhead <= LOCKED_TARGET,
        }
        for overhead in (0.0, 0.006, 0.012, 0.016, 0.0164, 0.018)
    ]


def build_result() -> dict[str, Any]:
    bindings = verify_bindings()
    source = materialize()
    config = json.loads(CONFIG.read_text())["text_config"]
    placement = json.loads(PLACEMENT.read_text())
    if config["num_hidden_layers"] != 60:
        raise RuntimeError("exact_geometry_is_not_60_layers")
    if config["layer_types"][COMPACTION_AFTER_LAYER] != "full_attention":
        raise RuntimeError("compaction_boundary_is_not_after_first_global_block")

    costs = accounting(placement, OUTPUT_STATES)
    removed = exact_removed_work(config)
    maximum_overhead = (
        LOCKED_TARGET
        - (QUALIFIED_BASELINE - costs["credited_savings"])
    )
    source_complete = all(
        (
            source["syntax_valid"],
            source["merge_follows_layer_5"],
            source["every_input_contributes_by_construction"],
            source["later_layer_call_receives_compacted_state_and_batch"],
            source["late_attention_metadata_reinitialized"],
            source["compact_kv_view_implemented"],
            removed["prefill_gemm_rows_removed"] > 0,
            removed["late_layer_kv_writes_removed"] > 0,
        )
    )
    meets_target = costs["service"] <= LOCKED_TARGET
    classification = (
        "source_complete_physical_candidate"
        if source_complete and meets_target
        else "typed_none"
    )
    return {
        "schema_version": 1,
        "classification": classification,
        "decision": {
            "source_complete": source_complete,
            "meets_locked_target": meets_target,
            "every_input_contributes_to_downstream_state": True,
            "quality_qualified": False,
            "interpretation": (
                "A two-tier prompt path executes layers 0-5 on all prompt tokens, "
                "then maps every prompt token exactly once into 1,152 protected singleton "
                "or weighted summary states and passes only those states, original/final "
                "RoPE positions, compact causal order, representative late KV slots, and "
                "rebuilt attention metadata to layers 6-59. The conservative trace-bound "
                "result clears the locked target, but intentionally changes model "
                "semantics and carries no merge-quality claim."
            ),
        },
        "bindings": {
            "measured_inputs": bindings,
            "runtime_source": source,
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        },
        "geometry": {
            "batch_size": BATCH_SIZE,
            "prompt_tokens_per_request": PROMPT_TOKENS,
            "output_tokens_per_request": 358,
            "shared_prefix_tokens_per_request": 535,
            "layers": config["num_hidden_layers"],
            "layer_types": config["layer_types"],
            "hidden_size": config["hidden_size"],
            "intermediate_size": config["intermediate_size"],
            "sliding_window": config["sliding_window"],
        },
        "schedule": {
            "compaction_after_layer": COMPACTION_AFTER_LAYER,
            "first_compacted_layer": COMPACTION_AFTER_LAYER + 1,
            "output_states_per_request": OUTPUT_STATES,
            "retained_state_fraction": OUTPUT_STATES / PROMPT_TOKENS,
            "protected_shared_prefix_tokens": PROTECTED_SHARED_PREFIX_TOKENS,
            "protected_recent_tokens": PROTECTED_RECENT_TOKENS,
            "maximum_additional_special_or_tool_tokens": (
                MAX_ADDITIONAL_PROTECTED_TOKENS
            ),
            "summary_state_range": [
                MIN_SUMMARY_STATES,
                MAX_SUMMARY_STATES,
            ],
            "merge": (
                "Mandatory shared-prefix, recent, configured special, and tool-format "
                "positions remain singleton states. Every other input belongs to exactly "
                "one nonempty contiguous ordinal partition; layer-5 hidden RMS scores "
                "produce a softmax-weighted summary for that partition. Each summary "
                "uses its last contributor's position, and singleton/summary states are "
                "restored to strict causal order. Merge quality receives no credit."
            ),
            "overflow_behavior": (
                "Fail closed to the uncredited full-token route if protected positions "
                "leave fewer than 64 summary states or the full 4,214-token prefill is "
                "unavailable."
            ),
            "ragged_and_graph_behavior": (
                "The admitted c32 geometry uses a fixed 1,152-token late budget, so no "
                "late GEMM padding is retained and one late decode graph shape suffices. "
                "Variable or mixed budgets form separate cohorts or fall back."
            ),
            "prefill_execution": (
                "CANDIDATE_RUNTIME_CONFIG.json coalesces the exact c32 prompt into one "
                "134,848-token candidate prefill invocation so layer-5 scores cover each "
                "complete 4,214-token request before merging. Partial or mixed prompt "
                "chunks fail closed; no transfer from a partial-score path is claimed."
            ),
            "state_semantics": (
                "A separate compact request-to-token view uses each singleton or summary "
                "state's final contributor slot for layers 6-59 while the allocator "
                "retains every original slot for layers 0-5 and safe request cleanup. "
                "Generated/verification slots append to the compact view on each call. "
                "Singleton original and summary-final positions define RoPE, group order "
                "preserves causality, and late attention metadata is rebuilt before layer 6."
            ),
        },
        "physical_accounting": {
            "evidence_type": (
                "measured scope-matched c32 H200 prefill attention and aggregate FP8 "
                "linear costs, exact c32 target-verification layer medians, exact work "
                "ratios, 10% non-scaling floors, and an analytical overhead envelope"
            ),
            "qualified_baseline_seconds_per_request": QUALIFIED_BASELINE,
            "locked_target_seconds_per_request": LOCKED_TARGET,
            "conservative_target_passes_per_c32_request": CONSERVATIVE_TARGET_PASSES,
            "non_scaling_floors": {
                "prefill_attention": NONSCALING_ATTENTION_FLOOR,
                "prefill_fp8_linear": NONSCALING_LINEAR_FLOOR,
                "target_verification_global_attention": NONSCALING_ATTENTION_FLOOR,
            },
            "counted_baseline_seconds_per_request": {
                "prefill": costs["prefill_baseline"],
                "target_verification": costs["verification_baseline"],
                "total": costs["counted_baseline"],
            },
            "candidate_counted_seconds_per_request": {
                "prefill": costs["prefill_candidate"],
                "target_verification": costs["verification_candidate"],
                "total": costs["counted_candidate"],
            },
            "credited_savings_seconds_per_request": {
                "prefill": costs["prefill_baseline"]
                - costs["prefill_candidate"],
                "target_verification": costs["verification_baseline"]
                - costs["verification_candidate"],
                "total": costs["credited_savings"],
            },
            "fixed_and_uncredited_residual_seconds_per_request": costs[
                "fixed_residual"
            ],
            "incremental_overhead_seconds_per_request": {
                **OVERHEAD,
                "total": costs["total_overhead"],
            },
            "conservative_candidate_service_seconds_per_request": costs["service"],
            "margin_to_target_seconds_per_request": LOCKED_TARGET
            - costs["service"],
            "maximum_total_incremental_overhead_seconds_per_request": maximum_overhead,
            "uncredited_savings": (
                "No ordinary autoregressive decode, local-attention decode, KV-write, "
                "normalization, activation, launch, scheduler, batching-capacity, or "
                "reduced allocator-pressure timing benefit is credited."
            ),
        },
        "removed_execution": removed,
        "sensitivity": {
            "summary_budget": schedule_sensitivity(placement),
            "overhead": overhead_sensitivity(
                costs["service"] - costs["total_overhead"]
            ),
            "interpretation": (
                "At the frozen 15 ms overhead, the 1,152-state schedule passes narrowly; "
                "larger summary budgets are reported explicitly. At 1,152 states, all incremental overhead must remain "
                "at or below the reported maximum. Protected-token overflow receives "
                "no assumed pass rate and falls back without credit."
            ),
        },
        "quality_recovery_path": [
            "Initialize the split runtime from the locked full-token teacher and train a layer-5 scorer plus boundary adapter with teacher hidden-state and logit distillation; retain the structural protection rules.",
            "Continue training on 4K-to-32K text, retrieval, multi-turn tool traces, and formatting-heavy prompts while sweeping only budgets already inside the physical sensitivity envelope.",
            "Require exact served-model GPQA-Diamond, TauBench, long-context retrieval, tool-call validity, formatting, multimodal regression, and full-token fallback calibration.",
            "Only after quality recovery, run a matched exact-c32 H200 endpoint pair and replace the analytical floors and overhead envelope with measured profiler-off service time.",
        ],
        "limitations": [
            "No checkpoint was downloaded, no accelerator was claimed, and no provider was contacted.",
            "The result is a source-complete offline physical proxy, not a GPU endpoint measurement.",
            "The prompt bytes and hidden states are absent, so merge quality, protected-state overflow frequency, and fallback rate are unmeasured.",
            "Prefill FP8-linear cost is measured in aggregate and apportioned by exact layer geometry; smaller-row kernel efficiency is conservatively bounded with a 10% non-scaling floor rather than measured.",
            "The 15 ms scorer, weighted-summary construction, movement, graph, synchronization, metadata, and fragmentation envelope is analytical.",
            "The candidate replaces the qualified route's 2,048-token dynamic prefill chunks with one 134,848-token exact-c32 prefill cohort; fit and the 3.5 ms synchronization/fragmentation reserve are analytical until target-GPU measurement.",
            "The compact KV view deliberately does not free dropped stock slots, so allocator capacity and maximum concurrency do not improve; only later-layer KV writes and reads shrink.",
            "No semantic, quality, convergence, deployability, or production-economic claim is made.",
        ],
    }


def main() -> None:
    result = build_result()
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)
    print(
        json.dumps(
            {
                "classification": result["classification"],
                "candidate_service_seconds_per_request": result[
                    "physical_accounting"
                ]["conservative_candidate_service_seconds_per_request"],
                "target_seconds_per_request": LOCKED_TARGET,
                "output": str(OUTPUT),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
