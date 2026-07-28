#!/usr/bin/env python3
"""Offline exact-token/KV-commit discriminator for one Gemma 4 draft cycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
DFLASH = PROJECTS / "gemma4_h200_dflash_endpoint"
OFFSET_HEAD = PROJECTS / "gemma4_causal_parallel_offset_head"

REQUEST_INDEX = 25
REQUEST_ID = "077dff09d0bc4ec1ad3af6ec056651b2"
REQUEST_SHA256 = "ee2edfa7a9ff571b0268966f506c4cb868868ab880ac87c2684b055d48a0e150"
QUALIFIED_BASELINE_SECONDS = 0.625149101968745
TARGET_SECONDS = 0.500119281574996

INPUTS = {
    "worker_source": (
        DFLASH / "inputs/bound/dflash_worker_v2.py",
        "8fbddb39f4b33b4ac55b1919bc58fa846acb60892886199251d3592a5223050f",
    ),
    "candidate_states": (
        DFLASH
        / "artifacts/candidate-only-owner-20260726t001857Z"
        / "retrieved/states/dflash-depth4-c32.jsonl",
        "b00e778bc03e218bb98d97817831438b304ae64ca21d4e945be22209ce68f694",
    ),
    "ordinary_terminal": (
        DFLASH
        / "artifacts/request-state-capture-owner-20260725T232227Z"
        / "retrieved-final/results/ar-c32/TERMINAL.json",
        "45b8120b452452b3ffcdc5282138e984140aa96b5802eef3d3ce66603a141af4",
    ),
    "parallel_frontier": (
        OFFSET_HEAD / "inputs/evidence/PARALLEL_DRAFT_FRONTIER.json",
        "59e35a96d00f370ad7eb6eb9721195a939265091f47094cff9947b62577c4f8b",
    ),
    "cost_model": (
        OFFSET_HEAD / "COST_MODEL.json",
        "4ee31dd7c0f6d407e1e61b148b7d41e54f8bda674e7b953d905d8a816a00ab72",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def first_difference(left: list[int], right: list[int]) -> int | None:
    for index, (left_token, right_token) in enumerate(zip(left, right)):
        if left_token != right_token:
            return index
    if len(left) != len(right):
        return min(len(left), len(right))
    return None


def source_line(source: str, needle: str) -> int:
    matches = [
        index
        for index, line in enumerate(source.splitlines(), start=1)
        if needle in line
    ]
    if not matches:
        raise ValueError(f"pinned worker is missing {needle!r}")
    return matches[0]


def evaluate_transition(
    *,
    pending_seed: int,
    proposal_tokens: list[int],
    verifier_top1: list[int],
    ordinary_tokens: list[int],
    committed_length_before: int,
    kv_write_locations: list[int],
) -> dict[str, Any]:
    if not proposal_tokens:
        raise ValueError("at least one proposal is required")
    if len(verifier_top1) < len(proposal_tokens) + 1:
        raise ValueError("verifier must contain one row per proposal plus a bonus row")

    accepted = 0
    while (
        accepted < len(proposal_tokens)
        and proposal_tokens[accepted] == verifier_top1[accepted]
    ):
        accepted += 1
    bonus = verifier_top1[accepted]
    emitted = proposal_tokens[:accepted] + [bonus]
    commit_length = accepted + 1
    if len(kv_write_locations) < commit_length:
        raise ValueError("KV locations do not cover seed plus accepted proposals")
    committed_locations = kv_write_locations[:commit_length]
    committed_length_after = committed_length_before + commit_length

    verifier_difference = first_difference(
        verifier_top1[: len(ordinary_tokens)], ordinary_tokens
    )
    emitted_difference = first_difference(
        emitted, ordinary_tokens[: len(emitted)]
    )
    token_exact = emitted_difference is None
    ordinary_commit_length = len(emitted)
    kv_geometry_exact = (
        commit_length == ordinary_commit_length
        and committed_length_after
        == committed_length_before + ordinary_commit_length
    )
    exact = token_exact and kv_geometry_exact

    fail_closed = None
    if not exact:
        ordinary_bonus = ordinary_tokens[0]
        fail_closed = {
            "action": "discard_speculative_only_writes_and_use_ordinary_target",
            "accepted_draft_count": 0,
            "emitted_tokens": [ordinary_bonus],
            "commit_length": 1,
            "committed_kv_write_locations": kv_write_locations[:1],
            "committed_length_after": committed_length_before + 1,
            "next_pending_seed": ordinary_bonus,
            "exact_against_ordinary_one_step": bool(kv_write_locations),
        }

    return {
        "pending_seed": pending_seed,
        "proposal_tokens": proposal_tokens,
        "verifier_top1": verifier_top1,
        "ordinary_tokens": ordinary_tokens[: len(verifier_top1)],
        "accepted_draft_count": accepted,
        "accepted_prefix": proposal_tokens[:accepted],
        "bonus_token": bonus,
        "emitted_tokens": emitted,
        "commit_length": commit_length,
        "committed_kv_write_locations": committed_locations,
        "committed_length_before": committed_length_before,
        "committed_length_after": committed_length_after,
        "next_pending_seed": bonus,
        "target_token_exact": token_exact,
        "kv_commit_geometry_exact": kv_geometry_exact,
        "exact_transition": exact,
        "first_verifier_difference_index": verifier_difference,
        "first_emitted_difference_index": emitted_difference,
        "fail_closed_correction": fail_closed,
    }


def economic_hurdle(cost_model: dict[str, Any], frontier: dict[str, Any]) -> dict[str, Any]:
    service = cost_model["service_model"]
    complete_head = cost_model["complete_head_accounting"]
    verifier = cost_model["verifier"]
    threshold = service["threshold"]
    baseline = float(service["qualified_baseline_seconds_per_request"])
    target = float(service["target_seconds_per_request"])
    if baseline != QUALIFIED_BASELINE_SECONDS or target != TARGET_SECONDS:
        raise ValueError("campaign baseline or target changed")

    accepted_target = float(threshold["mean_accepted_target_tokens"])
    accepted_draft = float(threshold["mean_accepted_draft_tokens"])
    head_ms = float(complete_head["head_ms_per_verification_call"])
    verifier_ms = float(verifier["measured_d16_per_request_verification_ms"])
    required_fom = accepted_target / ((head_ms + verifier_ms) / 1000.0)

    current = next(
        row for row in frontier["measured_depth_frontier"] if row["depth"] == 4
    )
    current_fom = float(current["accepted_target_tokens_per_cuda_event_second"])
    current_accept = float(
        current["mean_accepted_target_tokens_per_verification"]
    )

    gpu_fraction = float(service["trace_gpu_interval_union_fraction"])
    trace_calls = int(service["trace_target_forward_calls"])
    trace_window_ms = float(service["trace_window_ms"])
    current_baseline_accept = float(
        service["same_distribution_current_accepted_target_tokens"]
    )
    verifier_ratio = float(verifier["d16_over_d12_cost_ratio"])
    fixed_fraction = 1.0 - gpu_fraction

    def head_budget_ms(mean_accepted_target_tokens: float) -> float:
        remaining_fraction = (
            target / baseline
            - fixed_fraction
            - gpu_fraction
            * verifier_ratio
            * current_baseline_accept
            / mean_accepted_target_tokens
        )
        return max(
            0.0,
            remaining_fraction
            * mean_accepted_target_tokens
            / current_baseline_accept
            * trace_window_ms
            / trace_calls,
        )

    zero_draft_required = (
        current_baseline_accept
        * gpu_fraction
        / (target / baseline - fixed_fraction)
    )
    configured_depths = (4, 8, 12, 16)
    depth_rows = []
    for depth in configured_depths:
        maximum_accepted_target = depth + 1
        depth_rows.append(
            {
                "depth": depth,
                "maximum_accepted_target_tokens": maximum_accepted_target,
                "can_clear_with_zero_draft_cost_and_d12_verifier": (
                    maximum_accepted_target >= zero_draft_required
                ),
            }
        )

    return {
        "qualified_baseline_seconds_per_request": baseline,
        "target_seconds_per_request": target,
        "required_whole_request_reduction_fraction": 1.0 - target / baseline,
        "optimistic_zero_draft_cost": {
            "required_mean_accepted_target_tokens": zero_draft_required,
            "required_mean_accepted_draft_tokens": zero_draft_required - 1.0,
            "minimum_integer_draft_depth": math.ceil(zero_draft_required - 1.0),
            "configured_depths": depth_rows,
        },
        "charged_depth16_head_and_verifier": {
            "head_ms_per_verification_call": head_ms,
            "verifier_ms_per_request_verification": verifier_ms,
            "required_mean_accepted_target_tokens": accepted_target,
            "required_mean_accepted_draft_tokens": accepted_draft,
            "required_draft_prefix_fraction_of_depth16": float(
                threshold["draft_prefix_fraction_of_maximum"]
            ),
            "required_accepted_target_tokens_per_cuda_event_second": required_fom,
            "perfect_depth16_head_budget_ms": head_budget_ms(17.0),
            "threshold_head_budget_ms": head_budget_ms(accepted_target),
        },
        "measured_current_dflash": {
            "depth": int(current["depth"]),
            "mean_accepted_target_tokens": current_accept,
            "accepted_target_tokens_per_cuda_event_second": current_fom,
            "fraction_of_required_depth16_fom": current_fom / required_fom,
            "paired_endpoint_improvement_fraction": float(
                frontier["decision_basis"][
                    "depth4_paired_service_improvement_fraction"
                ]
            ),
            "passes_accepted_depth_hurdle": current_accept >= accepted_target,
            "passes_verification_cost_hurdle": current_fom >= required_fom,
        },
        "interpretation": (
            "Depths 4, 8, and 12 cannot reach the 20% target even with a free "
            "drafter and the optimistic D12 verifier. A charged D16 route needs "
            "15.054 accepted drafts (16.054 target tokens) per verification."
        ),
    }


def build_result() -> dict[str, Any]:
    integrity: dict[str, Any] = {}
    for name, (path, expected) in INPUTS.items():
        observed = sha256(path)
        if observed != expected:
            raise ValueError(
                f"{name} hash mismatch: expected {expected}, observed {observed}"
            )
        integrity[name] = {
            "path": os.path.relpath(path, PROJECT),
            "sha256": observed,
        }

    worker = INPUTS["worker_source"][0].read_text(encoding="utf-8")
    source_chain = {
        "verify_cache_assignment": source_line(
            worker, "model_worker_batch.out_cache_loc = verify_out_cache_loc"
        ),
        "target_forward": source_line(
            worker, "target_out = self.target_worker.forward_batch_generation("
        ),
        "target_argmax": source_line(
            worker, "target_predict = torch.argmax("
        ),
        "commit_length": source_line(
            worker, "commit_lens = accept_len.to(torch.int32) + 1"
        ),
        "sequence_advance": source_line(
            worker, "new_seq_lens = prefix_lens + commit_lens.to(prefix_lens.dtype)"
        ),
        "bonus_relay": source_line(worker, "verified_id=bonus,"),
        "kv_commit_consumer": source_line(worker, "accept_lens=commit_lens,"),
    }

    events = [
        event
        for event in load_jsonl(INPUTS["candidate_states"][0])
        if event.get("request_id") == REQUEST_ID
    ]
    first_step = next(event for event in events if event["phase"] == "first_target_step")
    ordinary_terminal = load_json(INPUTS["ordinary_terminal"][0])
    ordinary_row = next(
        row for row in ordinary_terminal["rows"] if row["index"] == REQUEST_INDEX
    )
    if ordinary_row["request_sha256"] != REQUEST_SHA256:
        raise ValueError("ordinary request identity changed")
    if first_step["verified_id"] != ordinary_row["token_ids"][0]:
        raise ValueError("captured pending seed no longer matches ordinary prefill")
    if first_step["sequence_length_after"] - first_step["sequence_length_before"] != 1:
        raise ValueError("captured zero-accept transition length changed")

    transition = evaluate_transition(
        pending_seed=int(first_step["verified_id"]),
        proposal_tokens=[int(value) for value in first_step["draft_tokens"][1:]],
        verifier_top1=[int(value) for value in first_step["target_top1"]],
        ordinary_tokens=[int(value) for value in ordinary_row["token_ids"][1:]],
        committed_length_before=int(first_step["sequence_length_before"]),
        kv_write_locations=[int(value) for value in first_step["kv_locations"]],
    )
    if transition["exact_transition"]:
        raise ValueError("expected the retained request-25 divergence")
    if transition["first_verifier_difference_index"] != 0:
        raise ValueError("first divergence moved beyond the first verifier token")
    if transition["fail_closed_correction"]["exact_against_ordinary_one_step"] is not True:
        raise ValueError("fail-closed correction did not reconstruct ordinary one-step")

    cost_model = load_json(INPUTS["cost_model"][0])
    frontier = load_json(INPUTS["parallel_frontier"][0])
    hurdle = economic_hurdle(cost_model, frontier)

    return {
        "schema_version": 1,
        "classification": (
            "localized_first_target_token_divergence_with_exact_fail_closed_correction"
        ),
        "decision": "reject_captured_dflash_transition_and_current_depth4_route",
        "new_scientific_sample_consumed": False,
        "gpu_used": False,
        "provider_spend_usd": 0.0,
        "input_integrity": integrity,
        "source_grounding": {
            "semantics": (
                "The verifier writes the pending seed and draft rows, derives greedy "
                "target IDs, commits seed plus accepted drafts, advances sequence "
                "length by that commit count, and relays the target bonus."
            ),
            "worker_line_numbers": source_chain,
        },
        "request_25": {
            "request_index": REQUEST_INDEX,
            "request_id": REQUEST_ID,
            "request_sha256": REQUEST_SHA256,
            "captured_kv_content_sha256": first_step["kv_content_sha256"],
            "ordinary_kv_content_sha256": None,
            "kv_content_equivalence_claimed": False,
            "transition": transition,
            "first_localized_divergence": {
                "phase": "target_verifier_token_before_acceptance",
                "output_index": 1,
                "expected_ordinary_token": ordinary_row["token_ids"][1],
                "observed_verifier_token": first_step["target_top1"][0],
                "kv_commit_geometry_at_boundary": "matching_seed_only_commit",
                "kv_content_status": (
                    "candidate hash persisted; ordinary same-state hash absent"
                ),
            },
            "smallest_executable_corrective_change": {
                "change": (
                    "Before accepting or committing speculative-only rows, compare "
                    "the first verifier target against the same-state ordinary target. "
                    "On mismatch, discard speculative-only writes, commit only the "
                    "pending seed, emit the ordinary token, and carry it as next seed."
                ),
                "preserves_target_semantics": True,
                "performance_interpretation": (
                    "This fail-closed guard needs ordinary target authority and is a "
                    "correctness discriminator, not a speedup. A performant repair "
                    "must make the request-owned verifier state itself reproduce 3496."
                ),
            },
        },
        "economic_hurdle": hurdle,
        "terminal_interpretation": (
            "The executable discriminator localizes the retained failure before "
            "acceptance and KV-length advancement: verifier target 759 differs from "
            "ordinary target 3496. Seed-only KV commit geometry matches, but KV "
            "content equivalence is unobserved. The exact fail-closed correction "
            "works, while the measured depth-4 route misses both accepted-depth and "
            "verification-efficiency hurdles."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_result()
    atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
