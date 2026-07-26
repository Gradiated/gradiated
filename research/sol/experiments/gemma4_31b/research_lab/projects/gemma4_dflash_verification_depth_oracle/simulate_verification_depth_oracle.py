#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path


CAMPAIGN_TARGET_SECONDS_PER_REQUEST = 0.500119281574996
QUALIFIED_DENOMINATOR_SECONDS_PER_REQUEST = 0.625149101968745


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.part")
    temporary.write_bytes(data)
    temporary.replace(path)


def load_bound_rows(input_path: Path, manifest_path: Path) -> tuple[list[dict], dict, str]:
    input_bytes = input_path.read_bytes()
    input_sha256 = sha256(input_bytes)
    manifest = json.loads(manifest_path.read_bytes())
    if input_sha256 != manifest["content"]["sha256"]:
        raise ValueError("input hash does not match the materialization manifest")
    rows = [json.loads(line) for line in input_bytes.splitlines() if line]
    return rows, manifest, input_sha256


def build_terminal(
    rows: list[dict],
    manifest: dict,
    input_sha256: str,
    cost_terminal_path: Path,
    endpoint_terminal_path: Path,
) -> dict:
    if len(rows) != 32:
        raise ValueError("oracle requires all 32 exact c32 request records")
    if len({row["request_id"] for row in rows}) != len(rows):
        raise ValueError("request ids are not distinct")
    if any(row["verification_depth"] != 4 for row in rows):
        raise ValueError("input includes a non-depth-four record")

    aggregate_histogram = [0, 0, 0, 0]
    for row in rows:
        histogram = row["accept_histogram"]
        if len(histogram) != 4 or sum(histogram) != row["verify_cycles"]:
            raise ValueError("invalid request histogram")
        if sum(index * count for index, count in enumerate(histogram)) != row["accepted_drafts"]:
            raise ValueError("invalid accepted-draft total")
        for index, count in enumerate(histogram):
            aggregate_histogram[index] += count

    verify_cycles = sum(aggregate_histogram)
    accepted_drafts = sum(
        accepted_count * cycle_count
        for accepted_count, cycle_count in enumerate(aggregate_histogram)
    )
    proposed_drafts = verify_cycles * 3
    fixed_verified_rows = verify_cycles * 4
    oracle_verified_rows = verify_cycles + accepted_drafts
    avoided_verified_rows = fixed_verified_rows - oracle_verified_rows
    logical_row_reduction_fraction = avoided_verified_rows / fixed_verified_rows
    accepted_plus_bonus_tokens = accepted_drafts + verify_cycles
    returned_completion_tokens = sum(row["completion_tokens"] for row in rows)
    completion_cap_surplus_tokens = accepted_plus_bonus_tokens - returned_completion_tokens

    cost_bytes = cost_terminal_path.read_bytes()
    cost_terminal = json.loads(cost_bytes)
    if not cost_terminal["pass"]:
        raise ValueError("depth-cost terminal is not valid")
    depth_cost = next(item for item in cost_terminal["depths"] if item["depth"] == 4)
    summary = depth_cost["robust_summary"]
    verifier_ms = summary["verifier"]["sum_ms"]
    draft_ms = summary["draft"]["sum_ms"]
    combined_ms = summary["draft_plus_verifier"]["sum_ms"]
    avoided_verifier_ms = verifier_ms * logical_row_reduction_fraction
    perfect_oracle_component_ms = combined_ms - avoided_verifier_ms
    component_reduction_fraction = avoided_verifier_ms / combined_ms

    endpoint_bytes = endpoint_terminal_path.read_bytes()
    endpoint_terminal = json.loads(endpoint_bytes)
    candidate = endpoint_terminal["candidate"]
    if candidate["arm"] != "dflash-depth4-c32" or candidate["complete_requests"] != 32:
        raise ValueError("endpoint terminal is not the complete exact depth-4 c32 arm")
    batch_seconds = candidate["batch_seconds"]
    service_seconds_per_request = candidate["service_seconds_per_request"]
    conservative_row_proportional_batch_floor = batch_seconds - avoided_verifier_ms / 1000
    conservative_row_proportional_service_floor = (
        conservative_row_proportional_batch_floor / candidate["complete_requests"]
    )
    whole_service_scaling_floor = service_seconds_per_request * (
        perfect_oracle_component_ms / combined_ms
    )
    sample_counts = depth_cost["sample_counts"]

    return {
        "schema_version": 1,
        "classification": "dflash_verification_depth_oracle_typed_none",
        "result": "none",
        "pass": True,
        "promotion": False,
        "decision": "close_request_adaptive_verification_depth_for_this_exact_c32_distribution",
        "evidence_label": "derived perfect-information oracle over measured real acceptance telemetry",
        "scope": {
            "accelerator": "nvidia-h200-sxm",
            "arm": "dflash-depth4-c32",
            "concurrency": 32,
            "draft_model": "z-lab/gemma-4-31B-it-DFlash@eabd648301ce28583cc14757912e5e0f84e152e1",
            "gpu_claimed": False,
            "network_or_endpoint_contacted": False,
            "paid_provider_mutation": False,
            "request_25_replayed": False,
            "target_model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        },
        "input_binding": {
            "analysis_input_hash_verified_before_parse": True,
            "bytes": manifest["content"]["bytes"],
            "manifest_classification": manifest["classification"],
            "request_count": len(rows),
            "sha256": input_sha256,
            "source_endpoint_terminal_sha256": manifest["source_endpoint_terminal"]["sha256"],
            "source_response_count": len(manifest["source_responses"]),
            "source_response_sha256s": [
                source["sha256"] for source in manifest["source_responses"]
            ],
            "excluded_source": manifest["excluded_source"],
        },
        "observed_distribution": {
            "accept_histogram_for_accepted_drafts_0_through_3": aggregate_histogram,
            "accepted_drafts": accepted_drafts,
            "proposed_drafts": proposed_drafts,
            "verify_cycles": verify_cycles,
            "returned_completion_tokens": returned_completion_tokens,
            "accepted_plus_one_target_bonus_tokens": accepted_plus_bonus_tokens,
            "completion_cap_surplus_tokens": completion_cap_surplus_tokens,
            "all_requests_complete_at_358_returned_tokens": all(
                row["completion_tokens"] == 358 for row in rows
            ),
        },
        "fixed_depth_four": {
            "verified_target_rows": fixed_verified_rows,
            "request_cycle_draft_invocations": verify_cycles,
            "proposed_draft_rows": proposed_drafts,
            "accepted_draft_tokens": accepted_drafts,
            "paired_batched_draft_and_target_launches_including_cold": sample_counts[
                "paired_decode_rows"
            ],
            "admitted_paired_launches_after_warmup": sample_counts["controller_rows"],
        },
        "perfect_predecision_oracle": {
            "policy": (
                "For an event with k accepted drafts, choose verification depth k+1. "
                "This preserves the accepted prefix and one target bonus while avoiding "
                "only rows strictly after the first rejected draft."
            ),
            "depth_histogram_1_through_4": aggregate_histogram,
            "unpadded_verified_target_rows": oracle_verified_rows,
            "avoided_unpadded_verified_target_rows": avoided_verified_rows,
            "logical_verified_row_reduction_fraction": logical_row_reduction_fraction,
            "request_cycle_draft_invocations": verify_cycles,
            "proposed_draft_rows_held_fixed": proposed_drafts,
            "accepted_draft_tokens": accepted_drafts,
            "request_completion_preserved": True,
            "paired_batched_draft_and_target_launches_including_cold": sample_counts[
                "paired_decode_rows"
            ],
            "admitted_paired_launches_after_warmup": sample_counts["controller_rows"],
            "launch_reduction": 0,
            "guaranteed_padding_aware_verified_row_reduction": 0,
        },
        "cost_translation": {
            "classification": "analytical_bound_from_exact_depth4_c32_h200_cuda_events",
            "cost_terminal_sha256": sha256(cost_bytes),
            "endpoint_terminal_sha256": sha256(endpoint_bytes),
            "measured_admitted_draft_ms": draft_ms,
            "measured_admitted_verifier_ms": verifier_ms,
            "measured_admitted_combined_ms": combined_ms,
            "row_proportional_avoided_verifier_ms_ceiling": avoided_verifier_ms,
            "perfect_oracle_component_ms_floor": perfect_oracle_component_ms,
            "perfect_oracle_component_reduction_fraction_ceiling": component_reduction_fraction,
            "fixed_endpoint_batch_seconds": batch_seconds,
            "fixed_endpoint_service_seconds_per_request": service_seconds_per_request,
            "conservative_row_proportional_batch_seconds_floor": (
                conservative_row_proportional_batch_floor
            ),
            "conservative_row_proportional_service_seconds_per_request_floor": (
                conservative_row_proportional_service_floor
            ),
            "even_more_generous_whole_service_scaling_floor": whole_service_scaling_floor,
            "padding_and_launch_guaranteed_service_seconds_per_request_floor": (
                service_seconds_per_request
            ),
            "interpretation": (
                "The conservative physical ceiling subtracts the row-proportional "
                "verifier CUDA-event saving from the exact c32 endpoint batch wall. "
                "It is not an observed endpoint delta. The whole-service scaling "
                "cross-check is deliberately more generous and also noncompetitive."
            ),
        },
        "competitiveness": {
            "campaign_target_seconds_per_request": CAMPAIGN_TARGET_SECONDS_PER_REQUEST,
            "qualified_denominator_seconds_per_request": (
                QUALIFIED_DENOMINATOR_SECONDS_PER_REQUEST
            ),
            "conservative_physical_ceiling_beats_campaign_target": (
                conservative_row_proportional_service_floor
                <= CAMPAIGN_TARGET_SECONDS_PER_REQUEST
            ),
            "conservative_physical_ceiling_beats_qualified_denominator": (
                conservative_row_proportional_service_floor
                <= QUALIFIED_DENOMINATOR_SECONDS_PER_REQUEST
            ),
            "even_whole_service_scaling_beats_qualified_denominator": (
                whole_service_scaling_floor
                <= QUALIFIED_DENOMINATOR_SECONDS_PER_REQUEST
            ),
        },
        "realizability": {
            "smallest_missing_predecision_observable": (
                "A calibrated per-request upper bound on accepted draft-prefix length "
                "available before TARGET_VERIFY row scheduling."
            ),
            "additional_scheduler_state_needed": [
                "request slot and sequence position",
                "active batch membership",
                "CUDA-graph bucket and padding layout",
            ],
            "present_in_bound_telemetry": False,
            "source_level_candidate": {
                "location": "DFlashWorkerV2.forward_batch_generation before target_worker.forward",
                "intervention": (
                    "Predict a depth vector from draft-side confidence, then bucket or "
                    "compact requests by chosen depth before constructing TARGET_VERIFY rows."
                ),
                "status": "not_admitted",
                "reason": (
                    "The perfect-information ceiling is already noncompetitive, and "
                    "the retained telemetry contains no predecision predictor features."
                ),
            },
        },
        "none_reasons": [
            (
                "The perfect oracle saves 24% of logical verifier rows but no target "
                "forward launches or draft invocations."
            ),
            (
                "Per-launch batch membership and padding are absent, so the guaranteed "
                "physical row saving is zero."
            ),
            (
                "Even the optimistic row-proportional H200 service floor misses both "
                "the qualified denominator and campaign target."
            ),
            (
                "Only post-verification acceptance outcomes are retained; no realizable "
                "predecision controller state can be fitted or evaluated."
            ),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cost-terminal", type=Path, required=True)
    parser.add_argument("--endpoint-terminal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, manifest, input_sha256 = load_bound_rows(args.input, args.manifest)
    terminal = build_terminal(
        rows,
        manifest,
        input_sha256,
        args.cost_terminal,
        args.endpoint_terminal,
    )
    atomic_write(
        args.output,
        json.dumps(terminal, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    )
    print(
        json.dumps(
            {
                "classification": terminal["classification"],
                "input_sha256": input_sha256,
                "logical_verified_row_reduction_fraction": terminal[
                    "perfect_predecision_oracle"
                ]["logical_verified_row_reduction_fraction"],
                "service_floor": terminal["cost_translation"][
                    "conservative_row_proportional_service_seconds_per_request_floor"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
