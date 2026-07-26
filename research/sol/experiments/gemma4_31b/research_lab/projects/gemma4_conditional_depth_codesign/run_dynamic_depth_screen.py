#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from conditional_depth_policy import (
    FULL_ACTIVE_LAYERS,
    PHYSICAL_PROXY_ROUTE,
    PREFILL_ACTIVE_LAYERS,
    PREFILL_GROUPS,
    VERIFICATION_ACTIVE_LAYERS,
    VERIFICATION_GROUPS,
)
from materialize_candidate import materialize


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PLACEMENT_PROJECT = ROOT.parent / "gemma4_hybrid_attention_placement_codesign"
CONFIG = PLACEMENT_PROJECT / "inputs/bound/config.json"
PLACEMENT = PLACEMENT_PROJECT / "PLACEMENT_SIMULATION_RESULT.json"
OUTPUT = ROOT / "DYNAMIC_DEPTH_PHYSICAL_SCREEN.json"

EXPECTED_BINDINGS = {
    CONFIG: "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    PLACEMENT: "2af53085953393785204eafb2c2dd0e9d335805f8a8e5963ae46fb57ed99e40b",
}

QUALIFIED_BASELINE_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
BATCH_SIZE = 32
CONSERVATIVE_TARGET_PASSES_PER_C32_REQUEST = 33.3125
OVERHEAD_SECONDS_PER_REQUEST = {
    "phase_router_and_route_validation": 0.0015,
    "route_specific_graph_selection_and_amortized_capture": 0.0010,
    "route_homogeneous_batch_compaction": 0.0040,
    "additional_route_boundary_synchronization": 0.0015,
    "graph_fragmentation_and_underfill_reserve": 0.0040,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bindings() -> list[dict[str, Any]]:
    bindings = []
    for path, expected in EXPECTED_BINDINGS.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"binding_mismatch:{path}:{actual}:{expected}")
        bindings.append(
            {
                "path": str(path.relative_to(LAB.parents[4])),
                "sha256": actual,
                "match": True,
            }
        )
    return bindings


def contiguous_groups(indices: frozenset[int]) -> list[list[int]]:
    ordered = sorted(indices)
    groups: list[list[int]] = []
    for layer_index in ordered:
        if not groups or layer_index != groups[-1][-1] + 1:
            groups.append([layer_index])
        else:
            groups[-1].append(layer_index)
    return [[group[0], group[-1] + 1] for group in groups]


def phase_costs(
    placement: dict[str, Any],
    active_layers: frozenset[int],
    phase: str,
) -> tuple[float, float]:
    if phase == "prefill":
        rows = placement["layer_cost_reconstruction"]["prefill"]["layers"]
        costs = {
            row["layer_index"]: (
                row["attention_kernel_seconds_per_c32_batch"]
                + row[
                    "flop_calibrated_attention_plus_mlp_linear_seconds_per_c32_batch"
                ]
            )
            / BATCH_SIZE
            for row in rows
        }
    else:
        rows = placement["layer_cost_reconstruction"]["target_verification"][
            "layers"
        ]
        costs = {
            row["layer_index"]: (
                row["attention_plus_all_projections_candidate_ms"]
                / 1000
                * CONSERVATIVE_TARGET_PASSES_PER_C32_REQUEST
                / BATCH_SIZE
            )
            for row in rows
        }
    baseline = sum(costs.values())
    active = sum(cost for layer_index, cost in costs.items() if layer_index in active_layers)
    return baseline, active


def routing_sensitivity(
    raw_savings: float, total_overhead: float
) -> list[dict[str, float | bool]]:
    rows = []
    for full_depth_fallback_fraction in (0.0, 0.05, 0.10, 0.20, 0.25):
        service = (
            QUALIFIED_BASELINE_SECONDS_PER_REQUEST
            - raw_savings * (1 - full_depth_fallback_fraction)
            + total_overhead
        )
        rows.append(
            {
                "full_depth_fallback_fraction": full_depth_fallback_fraction,
                "service_seconds_per_request": service,
                "meets_target": service <= TARGET_SECONDS_PER_REQUEST,
            }
        )
    return rows


def overhead_sensitivity(raw_savings: float) -> list[dict[str, float | bool]]:
    rows = []
    for overhead in (0.0, 0.004, 0.012, 0.024, 0.048, 0.050):
        service = QUALIFIED_BASELINE_SECONDS_PER_REQUEST - raw_savings + overhead
        rows.append(
            {
                "incremental_overhead_seconds_per_request": overhead,
                "service_seconds_per_request": service,
                "meets_target": service <= TARGET_SECONDS_PER_REQUEST,
            }
        )
    return rows


def build_result() -> dict[str, Any]:
    bindings = verify_bindings()
    source = materialize()
    config = json.loads(CONFIG.read_text())["text_config"]
    placement = json.loads(PLACEMENT.read_text())

    if config["num_hidden_layers"] != 60 or len(config["layer_types"]) != 60:
        raise RuntimeError("exact_geometry_is_not_60_layers")
    if not VERIFICATION_ACTIVE_LAYERS.issubset(PREFILL_ACTIVE_LAYERS):
        raise RuntimeError("verification_kv_ownership_violation")
    if contiguous_groups(PREFILL_ACTIVE_LAYERS) != [list(group) for group in PREFILL_GROUPS]:
        raise RuntimeError("prefill_groups_are_not_the_frozen_contiguous_groups")
    if contiguous_groups(VERIFICATION_ACTIVE_LAYERS) != [
        list(group) for group in VERIFICATION_GROUPS
    ]:
        raise RuntimeError("verification_groups_are_not_the_frozen_contiguous_groups")

    prefill_baseline, prefill_active = phase_costs(
        placement, PREFILL_ACTIVE_LAYERS, "prefill"
    )
    verify_baseline, verify_active = phase_costs(
        placement, VERIFICATION_ACTIVE_LAYERS, "verification"
    )
    prefill_savings = prefill_baseline - prefill_active
    verify_savings = verify_baseline - verify_active
    raw_savings = prefill_savings + verify_savings
    counted_baseline = prefill_baseline + verify_baseline
    non_skippable_residual = (
        QUALIFIED_BASELINE_SECONDS_PER_REQUEST - counted_baseline
    )
    total_overhead = sum(OVERHEAD_SECONDS_PER_REQUEST.values())
    candidate_service = (
        non_skippable_residual + prefill_active + verify_active + total_overhead
    )
    maximum_overhead = (
        TARGET_SECONDS_PER_REQUEST
        - (QUALIFIED_BASELINE_SECONDS_PER_REQUEST - raw_savings)
    )
    maximum_fallback = (
        raw_savings
        - (QUALIFIED_BASELINE_SECONDS_PER_REQUEST - TARGET_SECONDS_PER_REQUEST)
        - total_overhead
    ) / raw_savings

    source_complete = all(
        (
            source["syntax_valid"],
            source["skip_dominates_layer_load_and_call"],
            len(PREFILL_ACTIVE_LAYERS) == 30,
            len(VERIFICATION_ACTIVE_LAYERS) == 20,
            len(FULL_ACTIVE_LAYERS) == 60,
        )
    )
    meets_target = candidate_service <= TARGET_SECONDS_PER_REQUEST
    classification = (
        "source_complete_physical_candidate"
        if source_complete and meets_target
        else "typed_none"
    )

    return {
        "schema_version": 1,
        "classification": classification,
        "decision": {
            "meets_locked_target": meets_target,
            "source_complete": source_complete,
            "quality_qualified": False,
            "interpretation": (
                "The exact pinned layer loop can bypass the nominated block groups "
                "before Gemma4DecoderLayer.forward, eliminating the counted attention, "
                "QKV/O, gate/up/down, normalization, dynamic-FP8, and KV-write path. "
                "The conservative trace-backed service bound clears the target after "
                "a 12 ms/request incremental overhead envelope. This is an intentionally "
                "semantics-changing physical proxy with no accuracy credit."
            ),
        },
        "bindings": {
            "measured_inputs": bindings,
            "runtime_source": source,
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        },
        "geometry": {
            "layers": config["num_hidden_layers"],
            "layer_types": config["layer_types"],
            "hidden_size": config["hidden_size"],
            "intermediate_size": config["intermediate_size"],
            "attention_heads": config["num_attention_heads"],
            "local_kv_heads": config["num_key_value_heads"],
            "global_kv_heads": config["num_global_key_value_heads"],
            "local_head_dim": config["head_dim"],
            "global_head_dim": config["global_head_dim"],
            "sliding_window": config["sliding_window"],
        },
        "schedule": {
            "route_id": PHYSICAL_PROXY_ROUTE,
            "routing_rule": (
                "A candidate-only runtime defaults to the proxy route and captures its "
                "route-homogeneous c32 graphs. EXTEND/MIXED use prefill_groups; "
                "TARGET_VERIFY/DECODE use verification_groups. A separately captured "
                "full-depth runtime is the explicit fallback; mixed routes fail closed."
            ),
            "prefill_groups_half_open": contiguous_groups(PREFILL_ACTIVE_LAYERS),
            "verification_groups_half_open": contiguous_groups(
                VERIFICATION_ACTIVE_LAYERS
            ),
            "prefill_active_layers": sorted(PREFILL_ACTIVE_LAYERS),
            "verification_active_layers": sorted(VERIFICATION_ACTIVE_LAYERS),
            "prefill_active_layer_fraction": len(PREFILL_ACTIVE_LAYERS) / 60,
            "verification_active_layer_fraction": len(VERIFICATION_ACTIVE_LAYERS)
            / 60,
            "kv_ownership_invariant": (
                "verification_active_layers is a subset of prefill_active_layers; "
                "skipped layers are never later read and active layers retain their "
                "native layer-indexed KV ownership"
            ),
            "heterogeneous_batch_behavior": (
                "fail closed before model execution; a later request router must compact "
                "requests into separately captured route-homogeneous runtime cohorts"
            ),
        },
        "physical_accounting": {
            "evidence_type": (
                "measured scope-matched c32 H200 attention plus measured FP8-linear "
                "projection costs; analytical exact layer selection and overhead envelope"
            ),
            "qualified_baseline_seconds_per_request": QUALIFIED_BASELINE_SECONDS_PER_REQUEST,
            "locked_target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
            "conservative_target_passes_per_c32_request": CONSERVATIVE_TARGET_PASSES_PER_C32_REQUEST,
            "counted_baseline_seconds_per_request": {
                "prefill": prefill_baseline,
                "verification": verify_baseline,
                "total": counted_baseline,
            },
            "non_skippable_residual_seconds_per_request": non_skippable_residual,
            "candidate_counted_seconds_per_request": {
                "prefill": prefill_active,
                "verification": verify_active,
                "total": prefill_active + verify_active,
            },
            "credited_savings_seconds_per_request": {
                "prefill": prefill_savings,
                "verification": verify_savings,
                "total": raw_savings,
            },
            "uncredited_removed_work": (
                "All skipped layer norms, residual kernels, dynamic-FP8 quantizers, "
                "Python dispatch, and KV writes remain inside the fixed residual; no "
                "timing credit is taken for them."
            ),
            "incremental_overhead_seconds_per_request": {
                **OVERHEAD_SECONDS_PER_REQUEST,
                "total": total_overhead,
            },
            "conservative_candidate_service_seconds_per_request": candidate_service,
            "margin_to_target_seconds_per_request": (
                TARGET_SECONDS_PER_REQUEST - candidate_service
            ),
            "maximum_incremental_overhead_at_zero_fallback_seconds_per_request": maximum_overhead,
            "maximum_full_depth_fallback_fraction_at_frozen_overhead": maximum_fallback,
        },
        "removed_execution": {
            "source_boundary": (
                "Gemma4TextModel.forward skips before per-layer-input slicing, "
                "self.layers[layer_idx] load, and Gemma4DecoderLayer.forward"
            ),
            "prefill_layer_calls_removed_per_c32_model_forward": 30,
            "verification_layer_calls_removed_per_cycle": 40,
            "verification_fp8_projection_launches_removed_per_cycle": 160,
            "verification_attention_calls_removed_per_cycle": 40,
            "proof": (
                "The exact pinned target trace has four ordered FP8 projections per "
                "layer (QKV, O, gate/up, down). Dominating the layer call removes those "
                "four launches plus attention and all layer-local consumers; a mask "
                "that executes the layer cannot satisfy this source check."
            ),
        },
        "sensitivity": {
            "full_depth_fallback": routing_sensitivity(raw_savings, total_overhead),
            "incremental_overhead": overhead_sensitivity(raw_savings),
            "interpretation": (
                "At the frozen 12 ms envelope, at most the reported fallback fraction "
                "may revert to full depth. At zero fallback, routing, graph, compaction, "
                "synchronization, and fragmentation may total at most the reported "
                "maximum overhead before the target is lost."
            ),
        },
        "quality_recovery_path": [
            "Initialize the 60-layer student from the locked teacher; retain every weight and hard-wire the proxy schedule while training only recovery adapters and boundary norms first.",
            "Distill teacher logits and hidden states at the ends of [0,10), [25,35), and [50,60) on 4K-to-32K text, long-context retrieval, and tool-use trajectories, then continue pretraining with the hard prefill and verification schedules.",
            "Only after the fixed schedule recovers, train a request router with full-depth fallback and route-homogeneous batching; do not spend the physical margin as presumed accuracy.",
            "Require scope-matched GPQA-Diamond, TauBench, long-context retrieval, tool-call formatting, multimodal regression, and an exact c32 endpoint measurement before production eligibility.",
        ],
        "limitations": [
            "No checkpoint was downloaded, no accelerator was claimed, and no provider was contacted.",
            "The result is a source-complete physical bound, not a GPU measurement.",
            "Per-layer prefill projection cost is measured in aggregate and apportioned by exact projection FLOPs; target-verification layer costs are measured medians.",
            "The 33.3125 request-equivalent verification pass count is the conservative lower of two bound counter reconstructions, maximizing the fixed residual and minimizing credited savings.",
            "The 12 ms incremental overhead envelope is analytical and must be replaced by scope-matched measurement if checkpoint recovery is later authorized.",
            "The source-complete proxy is phase-adaptive. Per-request routing across proxy and full-depth graph cohorts remains part of the explicitly deferred quality-recovery runtime and receives no measured credit here.",
            "No semantic, quality, convergence, or deployability claim is made.",
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
                "target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
                "output": str(OUTPUT),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
