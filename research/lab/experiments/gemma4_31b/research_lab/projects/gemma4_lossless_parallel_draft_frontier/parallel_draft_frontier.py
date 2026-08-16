#!/usr/bin/env python3
"""Reproduce the real DFlash first divergence and measure its retained frontier."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def terminal_rows(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    rows = value.get("rows")
    if not isinstance(rows, list) or len(rows) != 32:
        raise ValueError(f"{path}: expected 32 terminal rows")
    return rows


def first_token_difference(
    left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    right_by_request = {row["request_sha256"]: row for row in right_rows}
    for left in sorted(left_rows, key=lambda row: int(row["index"])):
        right = right_by_request.get(left["request_sha256"])
        if right is None:
            return {
                "request_index": int(left["index"]),
                "request_sha256": left["request_sha256"],
                "field": "request_missing",
            }
        left_tokens = [int(token) for token in left["token_ids"]]
        right_tokens = [int(token) for token in right["token_ids"]]
        for output_index, (left_token, right_token) in enumerate(
            zip(left_tokens, right_tokens)
        ):
            if left_token != right_token:
                return {
                    "request_index": int(left["index"]),
                    "request_sha256": left["request_sha256"],
                    "output_index": output_index,
                    "left_token": left_token,
                    "right_token": right_token,
                    "left_prefix": left_tokens[: min(output_index + 3, len(left_tokens))],
                    "right_prefix": right_tokens[
                        : min(output_index + 3, len(right_tokens))
                    ],
                }
        if len(left_tokens) != len(right_tokens):
            return {
                "request_index": int(left["index"]),
                "request_sha256": left["request_sha256"],
                "output_index": min(len(left_tokens), len(right_tokens)),
                "left_length": len(left_tokens),
                "right_length": len(right_tokens),
            }
    return None


def exact_row_matches(
    left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]]
) -> int:
    right_by_request = {row["request_sha256"]: row for row in right_rows}
    return sum(
        1
        for left in left_rows
        if left["request_sha256"] in right_by_request
        and left["token_ids"] == right_by_request[left["request_sha256"]]["token_ids"]
    )


def cumulative_frames(path: Path) -> list[list[int]]:
    frames: list[list[int]] = []
    for line in path.read_text().splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        item = json.loads(line[6:])
        if "output_ids" not in item:
            continue
        ids = [int(value) for value in item["output_ids"]]
        if not ids:
            continue
        if frames and ids == frames[-1]:
            continue
        if frames and ids[: len(frames[-1])] != frames[-1]:
            raise ValueError(f"{path}: output_ids stopped being cumulative")
        frames.append(ids)
    if not frames:
        raise ValueError(f"{path}: no output_ids frames")
    return frames


def acceptance_for_depth(response_root: Path, depth: int) -> dict[str, Any]:
    target_tokens = 0
    accepted_drafts = 0
    verifications = 0
    final_tokens = 0
    for index in range(32):
        frames = cumulative_frames(response_root / f"response-{index:02d}.sse")
        if len(frames[0]) != 1:
            raise ValueError(
                f"depth {depth} request {index}: first DFlash frame is not prefill"
            )
        previous = len(frames[0])
        final_tokens += len(frames[-1])
        for frame in frames[1:]:
            committed = len(frame) - previous
            if not 1 <= committed <= depth:
                raise ValueError(
                    f"depth {depth} request {index}: invalid commit {committed}"
                )
            target_tokens += committed
            accepted_drafts += committed - 1
            verifications += 1
            previous = len(frame)
    if final_tokens != 32 * 358:
        raise ValueError(f"depth {depth}: expected 11,456 final tokens")
    return {
        "depth": depth,
        "requests": 32,
        "final_output_tokens": final_tokens,
        "target_tokens_committed_after_prefill": target_tokens,
        "target_verifications": verifications,
        "accepted_draft_tokens": accepted_drafts,
        "mean_accepted_target_tokens_per_verification": target_tokens / verifications,
        "mean_accepted_draft_tokens_per_verification": accepted_drafts / verifications,
        "draft_slot_survival_fraction": accepted_drafts
        / (verifications * (depth - 1)),
    }


def measured_frontier(
    depth_cost_terminal: Path, depth_roots: dict[int, Path]
) -> list[dict[str, Any]]:
    cost = load_json(depth_cost_terminal)
    choices = {
        int(choice["depth"]): choice for choice in cost["controller"]["choices"]
    }
    rows = []
    for depth in sorted(depth_roots):
        row = acceptance_for_depth(depth_roots[depth], depth)
        choice = choices[depth]
        total_ms = float(choice["validated_draft_plus_verifier_cuda_event_ms"])
        row.update(
            {
                "draft_plus_verifier_cuda_event_ms": total_ms,
                "accepted_target_tokens_per_cuda_event_second": row[
                    "target_tokens_committed_after_prefill"
                ]
                / (total_ms / 1000.0),
                "source_cost_controller_tokens_per_second": float(
                    choice["normalized_tokens_per_cuda_event_second"]
                ),
            }
        )
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: row["accepted_target_tokens_per_cuda_event_second"],
        reverse=True,
    )


def event_for(
    capture: dict[str, Any], request_index: int, phase: str
) -> dict[str, Any]:
    matches = [
        event
        for event in capture["events"]
        if int(event["request_index"]) == request_index and event["phase"] == phase
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one {phase} event for request {request_index}, got {len(matches)}"
        )
    return matches[0]


def relay_reproducer(
    request_25: dict[str, Any], request_28: dict[str, Any]
) -> dict[str, Any]:
    published = [
        {
            "request_id": request_25["request_id"],
            "verified_id": int(request_25["bonus_token"]),
            "new_seq_len": int(request_25["sequence_length_after"]),
            "kv_locations": [int(value) for value in request_25["kv_locations"]],
        },
        {
            "request_id": request_28["request_id"],
            "verified_id": int(request_28["bonus_token"]),
            "new_seq_len": int(request_28["sequence_length_after"]),
            "kv_locations": [int(value) for value in request_28["kv_locations"]],
        },
    ]
    identity = [0, 1]
    reordered = [1, 0]

    def direct(indices: list[int]) -> list[dict[str, Any]]:
        return [
            {
                "request_id": published[index]["request_id"],
                "received_state": published[position],
            }
            for position, index in enumerate(indices)
        ]

    def future_map(indices: list[int]) -> list[dict[str, Any]]:
        return [
            {
                "request_id": published[index]["request_id"],
                "received_state": published[index],
            }
            for index in indices
        ]

    def correctly_owned(rows: list[dict[str, Any]]) -> bool:
        return all(
            row["request_id"] == row["received_state"]["request_id"] for row in rows
        )

    aa_direct = direct(identity)
    aa_future = future_map(identity)
    ab_direct = direct(reordered)
    ab_future = future_map(reordered)
    return {
        "input_evidence": "real_persisted_first_target_step_state",
        "schedule_geometry": "deterministic_source_exercising_reorder",
        "aa_identity_control": {
            "direct_carry": aa_direct,
            "future_map": aa_future,
            "direct_carry_pass": correctly_owned(aa_direct),
            "future_map_pass": correctly_owned(aa_future),
            "arms_equal": canonical(aa_direct) == canonical(aa_future),
        },
        "reorder_discriminator": {
            "next_order": [
                published[index]["request_id"] for index in reordered
            ],
            "direct_carry": ab_direct,
            "future_map": ab_future,
            "direct_carry_pass": correctly_owned(ab_direct),
            "future_map_pass": correctly_owned(ab_future),
            "first_divergent_field": "verified_id",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repair-patch", type=Path, required=True)
    args = parser.parse_args()

    legacy = args.legacy_project.resolve()
    run_a = legacy / "artifacts/candidate-only-owner-20260726t000722Z"
    run_b = legacy / "artifacts/candidate-only-owner-20260726t001354Z"
    run_c = legacy / "artifacts/candidate-only-owner-20260726t001857Z"
    ar_terminal = (
        legacy
        / "artifacts/request-state-capture-owner-20260725T232227Z"
        / "retrieved-final/results/ar-c32/TERMINAL.json"
    )
    a_terminal = run_a / "retrieved/results/dflash-depth4-c32/TERMINAL.json"
    b_terminal = run_b / "retrieved/results/dflash-depth4-c32/TERMINAL.json"
    c_terminal = run_c / "retrieved/results/dflash-depth4-c32/TERMINAL.json"
    capture_path = run_c / "DFLASH_CANDIDATE_ONLY_REQUEST_STATE_CAPTURE_RESULT.json"
    buggy_info = run_c / "retrieved/inputs/bound/dflash_info_v2.py"
    repaired_info = (
        legacy
        / "artifacts/request25-boundary-probe-preparation-20260726"
        / "packet/4ae9a81bfe3cfcc45a5302662be380e70c2753ef336547445b85aa7ed28f7f4b"
        / "executed_source/dflash_info_v2.py"
    )
    depth_root = legacy / "artifacts/cycle-depth-owner-20260725t1810z/retrieved"
    depth_roots = {
        depth: depth_root / f"depth-{depth}/request" for depth in (4, 8, 12, 16)
    }
    depth_cost = legacy / "DFLASH_C32_DEPTH_COST_TERMINAL.json"
    endpoint = load_json(legacy / "DFLASH_DEPTH4_ENDPOINT_TERMINAL.json")

    a_rows = terminal_rows(a_terminal)
    b_rows = terminal_rows(b_terminal)
    c_rows = terminal_rows(c_terminal)
    ar_rows = terminal_rows(ar_terminal)
    capture = load_json(capture_path)
    request_25 = event_for(capture, 25, "first_target_step")
    request_25_prefill = event_for(capture, 25, "target_prefill")
    request_28 = event_for(capture, 28, "first_target_step")
    ar_25 = ar_rows[25]
    candidate_25 = c_rows[25]
    if (
        ar_25["request_sha256"] != candidate_25["request_sha256"]
        or candidate_25["request_id"] != request_25["request_id"]
    ):
        raise ValueError("request 25 identity mismatch")

    observer_left = copy.deepcopy(request_25)
    observer_right = copy.deepcopy(request_25)
    observer_aa_pass = canonical(observer_left) == canonical(observer_right)
    runtime_first_difference = first_token_difference(a_rows, b_rows)
    runtime_exact_matches = exact_row_matches(a_rows, b_rows)
    frontier = measured_frontier(depth_cost, depth_roots)
    best = frontier[0]

    control_s = float(endpoint["control"]["service_seconds_per_request"])
    candidate_s = float(endpoint["candidate"]["service_seconds_per_request"])
    target_s = float(endpoint["campaign_target_s_per_request"])
    paired_improvement = 1.0 - candidate_s / control_s

    buggy_text = buggy_info.read_text()
    repaired_text = repaired_info.read_text()
    repair_bound = (
        "direct_carry_valid: bool = True" in buggy_text
        and "direct_carry_valid: bool = False" in repaired_text
        and sha256(args.repair_patch) == sha256(legacy / "DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch")
    )
    relay = relay_reproducer(request_25, request_28)

    result = {
        "schema_version": 1,
        "decision": "typed_none",
        "scope": "current_gemma4_dflash_drafter_and_pinned_sglang_runtime",
        "classification": "measured_acceptance_and_service_frontier_below_20_percent_route",
        "question": (
            "Can the repaired current DFlash path plausibly reduce 0.625149101968745 "
            "s/request to 0.500119281574996 s/request losslessly?"
        ),
        "input_integrity": {
            str(path.relative_to(legacy)): sha256(path)
            for path in (
                a_terminal,
                b_terminal,
                c_terminal,
                ar_terminal,
                capture_path,
                buggy_info,
                repaired_info,
                depth_cost,
                legacy / "DFLASH_DEPTH4_ENDPOINT_TERMINAL.json",
            )
        },
        "real_first_divergence": {
            "request_index": 25,
            "request_id": request_25["request_id"],
            "request_sha256": candidate_25["request_sha256"],
            "target_autoregressive_tokens": [
                int(value) for value in ar_25["token_ids"][:3]
            ],
            "target_prefill_argmax": int(request_25_prefill["target_top1"]),
            "verified_id": int(request_25["verified_id"]),
            "draft_tokens": [int(value) for value in request_25["draft_tokens"]],
            "target_verifier_logits": {
                "persisted": False,
                "reason": "raw verifier logits were not retained",
            },
            "target_verifier_argmax": [
                int(value) for value in request_25["target_top1"]
            ],
            "accepted_prefix": [
                int(value) for value in request_25["accepted_prefix"]
            ],
            "accepted_draft_count": int(request_25["accepted_draft_count"]),
            "bonus_token": int(request_25["bonus_token"]),
            "kv_write_locations": [
                int(value) for value in request_25["kv_locations"]
            ],
            "kv_content_sha256": request_25["kv_content_sha256"],
            "committed_sequence_length_before": int(
                request_25["sequence_length_before"]
            ),
            "committed_sequence_length_after": int(
                request_25["sequence_length_after"]
            ),
            "first_subsequent_autoregressive_token": int(ar_25["token_ids"][2]),
            "first_difference": {
                "output_index": 1,
                "autoregressive": int(ar_25["token_ids"][1]),
                "dflash": int(request_25["bonus_token"]),
            },
        },
        "aa_controls": {
            "observer_same_bytes_twice": {
                "pass": observer_aa_pass,
                "canonical_sha256": hashlib.sha256(canonical(observer_left)).hexdigest(),
            },
            "runtime_same_source_same_workload": {
                "source_sha256_equal": sha256(
                    run_a / "retrieved/inputs/bound/dflash_info_v2.py"
                )
                == sha256(run_b / "retrieved/inputs/bound/dflash_info_v2.py"),
                "exact_request_token_matches": runtime_exact_matches,
                "total_requests": 32,
                "first_difference": runtime_first_difference,
                "pass": runtime_first_difference is None,
            },
        },
        "causal_reproducer": relay,
        "repair": {
            "mechanism": (
                "Disable DFlash positional direct carry so FutureMap gathers verified_id "
                "and new_seq_lens by request identity on every overlap iteration."
            ),
            "patch": args.repair_patch.name,
            "patch_sha256": sha256(args.repair_patch),
            "buggy_source_sha256": sha256(buggy_info),
            "repaired_source_sha256": sha256(repaired_info),
            "source_transition_bound": repair_bound,
            "aa_pass": relay["aa_identity_control"]["arms_equal"],
            "bug_reproduced": not relay["reorder_discriminator"]["direct_carry_pass"],
            "repair_pass": relay["reorder_discriminator"]["future_map_pass"],
            "upstream_corroboration": {
                "sglang_pr": 29232,
                "url": "https://github.com/sgl-project/sglang/pull/29232",
                "merged_commit": "593f5ba68f4c27d5ea5644cd46c938644b5ef61a",
                "merged_at_utc": "2026-06-28T07:02:32Z",
                "change": "removed DFlash direct-carry early returns from overlap_utils",
            },
        },
        "measured_depth_frontier": frontier,
        "measured_endpoint": {
            "paired_ar_s_per_request": control_s,
            "dflash_depth4_s_per_request": candidate_s,
            "paired_improvement_fraction": paired_improvement,
            "campaign_target_s_per_request": target_s,
            "candidate_excess_over_target_fraction": candidate_s / target_s - 1.0,
            "semantic_equivalence": bool(endpoint["target_emitted_token_equivalence"]),
        },
        "decision_basis": {
            "best_depth_by_required_objective": int(best["depth"]),
            "best_accepted_target_tokens_per_cuda_event_second": best[
                "accepted_target_tokens_per_cuda_event_second"
            ],
            "depth4_paired_service_improvement_fraction": paired_improvement,
            "required_service_improvement_fraction": 0.20,
            "reason": (
                "The current drafter's best measured acceptance/cost depth is retained, "
                "but its completed paired endpoint improved service by only "
                f"{paired_improvement:.3%}; this is far below 20%, and the measured "
                "candidate was also semantically divergent. Repairing request ownership "
                "does not create the missing accepted work."
            ),
        },
        "next_intervention": {
            "name": "gemma4_causal_parallel_offset_head",
            "mechanism": (
                "Freeze Gemma 4 and train one small shared causal block head over target "
                "layer taps plus learned offsets 1..16. One head forward emits all offset "
                "logits through the tied vocabulary projection; the unchanged target "
                "verifier remains the lossless authority."
            ),
            "training_data": (
                "Teacher-forced and target-generated continuations from the exact campaign "
                "request distribution; label offsets 1..16 with target tokens and weight "
                "loss by prefix survival and measured depth cost."
            ),
            "smallest_falsifier": {
                "hardware": "one director-authorized H200 or equivalent",
                "trainable_parameters": "head only; target frozen",
                "examples": 4096,
                "depths": [4, 8, 12, 16],
                "gate": (
                    "On a disjoint 512-example holdout, exact target verification must "
                    "raise accepted-target-tokens/(draft+verify CUDA seconds) enough for "
                    "a conservative c32 service projection <=0.500119281574996 s/request."
                ),
                "gpu_command_bound": False,
                "reason": (
                    "No trained head checkpoint or positive spend authority exists in "
                    "this project; this typed-none result closes only the current drafter."
                ),
            },
        },
        "claims": {
            "working_runtime_repair_source": True,
            "repair_executed_on_gpu": False,
            "new_gpu_sample_consumed": False,
            "provider_spend_usd": 0.0,
            "production_eligible": False,
        },
    }
    gates = [
        observer_aa_pass,
        runtime_first_difference is not None,
        runtime_exact_matches < 32,
        repair_bound,
        relay["aa_identity_control"]["arms_equal"],
        not relay["reorder_discriminator"]["direct_carry_pass"],
        relay["reorder_discriminator"]["future_map_pass"],
        len(frontier) == 4,
        paired_improvement < 0.20,
    ]
    result["reproducer_pass"] = all(gates)
    atomic_json(args.output, result)
    return 0 if result["reproducer_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
