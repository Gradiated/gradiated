#!/usr/bin/env python3
"""Reconstruct request-local DFlash cycles from retained cumulative SSE.

This is deliberately an offline observer.  It does not import SGLang or torch.
The retained endpoint used ``stream_interval=1`` with cumulative
``output_ids``, so each distinct SSE prefix is one scheduler emission.  For
DFlash, the first emission is target prefill and later emissions are verify
cycles containing zero or more accepted drafts followed by one target bonus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


BLOCK_SIZE = 4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def cumulative_frames(path: Path) -> list[list[int]]:
    result: list[list[int]] = []
    for line in path.read_text().splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        item = json.loads(line[6:])
        if "output_ids" not in item:
            continue
        ids = [int(value) for value in item["output_ids"]]
        if result and ids == result[-1]:
            continue
        if result and ids[: len(result[-1])] != result[-1]:
            raise ValueError(f"{path}: cumulative output_ids ceased to be a prefix")
        result.append(ids)
    if not result:
        raise ValueError(f"{path}: no cumulative output_ids frames")
    return result


def chunks(frames: list[list[int]]) -> list[list[int]]:
    result: list[list[int]] = []
    previous = 0
    for frame in frames:
        result.append(frame[previous:])
        previous = len(frame)
    return result


def line_numbers(text: str, needles: list[str]) -> dict[str, int]:
    lines = text.splitlines()
    result: dict[str, int] = {}
    for needle in needles:
        matches = [i + 1 for i, line in enumerate(lines) if needle in line]
        if not matches:
            raise ValueError(f"pinned source is missing required text: {needle}")
        result[needle] = matches[0]
    return result


def first_difference(left: list[int], right: list[int]) -> int | None:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    if len(left) != len(right):
        return min(len(left), len(right))
    return None


def locate_cycle(frames: list[list[int]], output_index: int) -> tuple[int, int]:
    previous = 0
    for cycle_index, frame in enumerate(frames):
        if output_index < len(frame):
            return cycle_index, previous
        previous = len(frame)
    raise ValueError(f"output index {output_index} is outside retained frames")


def forced_reject(token: int) -> int:
    candidate = (token + 1) % 262_144
    return candidate if candidate != token else (token + 2) % 262_144


def replay_cycle(
    *,
    target: list[int],
    pending_seed: int,
    emitted: list[int],
    output_start: int,
    committed_output_before: int,
) -> dict[str, Any]:
    """Build and evaluate a deterministic draft block for one retained cycle."""
    accepted_count = len(emitted) - 1
    if not 0 <= accepted_count <= BLOCK_SIZE - 1:
        raise ValueError(f"invalid retained DFlash emission length: {len(emitted)}")
    target_top1 = target[output_start : output_start + BLOCK_SIZE]
    if len(target_top1) != BLOCK_SIZE:
        raise ValueError("fixture needs four target continuation tokens")

    draft = [pending_seed]
    draft.extend(emitted[:accepted_count])
    while len(draft) < BLOCK_SIZE:
        target_at_draft = target_top1[len(draft) - 1]
        draft.append(forced_reject(target_at_draft))

    replay_accepted = 0
    while (
        replay_accepted < BLOCK_SIZE - 1
        and draft[replay_accepted + 1] == target_top1[replay_accepted]
    ):
        replay_accepted += 1
    replay_bonus = target_top1[replay_accepted]
    replay_emitted = draft[1 : 1 + replay_accepted] + [replay_bonus]
    committed_output_after = committed_output_before + len(replay_emitted)

    return {
        "pending_seed": pending_seed,
        "target_top1": target_top1,
        "synthetic_draft_block": draft,
        "accepted_draft_count": replay_accepted,
        "accepted_prefix": draft[1 : 1 + replay_accepted],
        "bonus_token": replay_bonus,
        "emitted_tokens": replay_emitted,
        "retained_emitted_tokens": emitted,
        "committed_output_tokens_before": committed_output_before,
        "committed_output_tokens_after": committed_output_after,
        "pending_output_tokens_after": output_start + len(replay_emitted),
        "pass": (
            replay_accepted == accepted_count
            and replay_emitted == emitted
            and committed_output_after == output_start + len(emitted) - 1
        ),
    }


def choose_fixture(
    request_index: int,
    request_sha256: str,
    target: list[int],
    candidate_frames: list[list[int]],
) -> dict[str, Any]:
    emitted_chunks = chunks(candidate_frames)
    sizes = [len(chunk) for chunk in emitted_chunks]
    selected: tuple[int, int, int] | None = None
    for reject_cycle in range(1, len(sizes) - 2):
        if sizes[reject_cycle] != 1:
            continue
        for accepted_cycle in range(reject_cycle + 1, len(sizes) - 1):
            if sizes[accepted_cycle] > 1:
                selected = (reject_cycle, accepted_cycle, accepted_cycle + 1)
                break
        if selected is not None:
            break
    if selected is None:
        raise ValueError("no reject/accept/subsequent-cycle fixture exists")

    events = []
    for cycle_index in selected:
        output_start = len(candidate_frames[cycle_index - 1])
        pending_seed = target[output_start - 1]
        event = replay_cycle(
            target=target,
            pending_seed=pending_seed,
            emitted=emitted_chunks[cycle_index],
            output_start=output_start,
            committed_output_before=output_start - 1,
        )
        event.update(
            {
                "cycle_index": cycle_index,
                "output_start": output_start,
                "output_end": len(candidate_frames[cycle_index]),
            }
        )
        events.append(event)

    return {
        "schema_version": 1,
        "evidence_label": "measured_boundaries_with_synthetic_draft_proposals",
        "request_index": request_index,
        "request_sha256": request_sha256,
        "block_size": BLOCK_SIZE,
        "selected_cycle_indices": list(selected),
        "crosses_zero_accept_reject": any(
            event["accepted_draft_count"] == 0 for event in events
        ),
        "crosses_nonempty_accepted_prefix": any(
            event["accepted_draft_count"] > 0 for event in events
        ),
        "crosses_bonus_decision": all("bonus_token" in event for event in events),
        "crosses_subsequent_cycle": events[-1]["cycle_index"]
        == events[-2]["cycle_index"] + 1,
        "cycles": events,
        "pass": all(event["pass"] for event in events),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--pinned-worker", type=Path, required=True)
    parser.add_argument("--pinned-info", type=Path, required=True)
    parser.add_argument("--repair-patch", type=Path, required=True)
    parser.add_argument("--endpoint-runner", type=Path, required=True)
    parser.add_argument("--candidate-server-log", type=Path, required=True)
    parser.add_argument("--fixture-output", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    args = parser.parse_args()

    terminal = json.loads(args.terminal.read_text())
    control_rows = terminal["control"]["rows"]
    candidate_rows = terminal["candidate"]["rows"]
    if len(control_rows) != 32 or len(candidate_rows) != 32:
        raise ValueError("expected the retained c32 pair")

    worker_text = args.pinned_worker.read_text()
    info_text = args.pinned_info.read_text()
    runner_text = args.endpoint_runner.read_text()
    server_log_text = args.candidate_server_log.read_text()
    if "stream_interval=1" not in server_log_text:
        raise ValueError("candidate server did not persist stream_interval=1")
    if "incremental_streaming_output=False" not in server_log_text:
        raise ValueError("candidate server did not persist cumulative streaming")
    if f"speculative_num_draft_tokens={BLOCK_SIZE}" not in server_log_text:
        raise ValueError(f"candidate server did not persist DFlash depth {BLOCK_SIZE}")
    source_lines = {
        "worker": line_numbers(
            worker_text,
            [
                "batch_output = self.target_worker.forward_batch_generation(",
                "verified_id=next_token_ids,",
                "verified_id=bonus,",
                "next_token_ids=out_tokens.reshape(-1),",
                "accept_lens=commit_lens,",
            ],
        ),
        "info": line_numbers(
            info_text,
            [
                "direct_carry_valid: bool = True",
                "self.direct_carry_valid = False",
            ],
        ),
        "runner": line_numbers(
            runner_text,
            [
                'if "output_ids" in item:',
                'ids = [int(value) for value in item["output_ids"]]',
                '"stream": True',
            ],
        ),
    }

    divergences: list[dict[str, Any]] = []
    frame_counts: dict[str, dict[str, int]] = {"control": {}, "candidate": {}}
    all_final_frames_match_rows = True
    all_request_hashes_match = True
    request_data: dict[int, tuple[list[int], list[list[int]]]] = {}

    for index, (control, candidate) in enumerate(zip(control_rows, candidate_rows)):
        if control["index"] != index or candidate["index"] != index:
            raise ValueError("terminal rows are not in request-index order")
        all_request_hashes_match &= (
            control["request_sha256"] == candidate["request_sha256"]
        )
        control_frames = cumulative_frames(
            args.raw_root / "ar-c32" / f"response-{index:02d}.sse"
        )
        candidate_frames = cumulative_frames(
            args.raw_root / "dflash-depth4-c32" / f"response-{index:02d}.sse"
        )
        frame_counts["control"][str(index)] = len(control_frames)
        frame_counts["candidate"][str(index)] = len(candidate_frames)
        all_final_frames_match_rows &= (
            control_frames[-1] == [int(value) for value in control["token_ids"]]
            and candidate_frames[-1]
            == [int(value) for value in candidate["token_ids"]]
        )
        target = control_frames[-1]
        observed = candidate_frames[-1]
        request_data[index] = (target, candidate_frames)
        position = first_difference(target, observed)
        if position is None:
            continue
        cycle_index, cycle_start = locate_cycle(candidate_frames, position)
        cycle_end = len(candidate_frames[cycle_index])
        emitted = candidate_frames[cycle_index][cycle_start:cycle_end]
        offset = position - cycle_start
        role = (
            "prefill_target_token"
            if cycle_index == 0
            else (
                "bonus_token"
                if offset == len(emitted) - 1
                else "accepted_draft_prefix"
            )
        )
        prior_prefix_equal = observed[:position] == target[:position]
        pending_seed = None if cycle_start == 0 else observed[cycle_start - 1]
        pending_seed_equals_ar = (
            None
            if cycle_start == 0
            else pending_seed == target[cycle_start - 1]
        )
        divergences.append(
            {
                "request_index": index,
                "request_sha256": candidate["request_sha256"],
                "output_index": position,
                "cycle_index": cycle_index,
                "cycle_kind": "prefill" if cycle_index == 0 else "verify",
                "cycle_output_start": cycle_start,
                "cycle_output_end": cycle_end,
                "cycle_emission_length": len(emitted),
                "offset_within_cycle": offset,
                "emission_role": role,
                "expected_ar_token": target[position],
                "observed_dflash_token": observed[position],
                "cycle_expected_ar_tokens": target[cycle_start:cycle_end],
                "cycle_observed_tokens": emitted,
                "all_prior_emitted_tokens_equal_ar": prior_prefix_equal,
                "pending_seed": pending_seed,
                "pending_seed_equals_ar": pending_seed_equals_ar,
            }
        )

    fixture_target, fixture_frames = request_data[0]
    fixture = choose_fixture(
        request_index=0,
        request_sha256=candidate_rows[0]["request_sha256"],
        target=fixture_target,
        candidate_frames=fixture_frames,
    )
    atomic_json(args.fixture_output, fixture)

    earliest_request_order = min(
        divergences, key=lambda item: (item["request_index"], item["cycle_index"])
    )
    prefill_divergences = [
        item for item in divergences if item["cycle_kind"] == "prefill"
    ]
    verify_divergences = [
        item for item in divergences if item["cycle_kind"] == "verify"
    ]
    earliest_verify_ordinal = min(
        verify_divergences, key=lambda item: (item["cycle_index"], item["request_index"])
    )

    control_cache = [int(row["cached_tokens"] or 0) for row in control_rows]
    candidate_cache = [int(row["cached_tokens"] or 0) for row in candidate_rows]
    control_zero = [i for i, value in enumerate(control_cache) if value == 0]
    candidate_zero = [i for i, value in enumerate(candidate_cache) if value == 0]

    # This synthetic reorder demonstrates what the prior patch can repair.  The
    # pinned filter/merge source already flips direct_carry_valid off, while the
    # measured prefill divergences occur before this mechanism can participate.
    relay_published = {101: 759, 202: 537}
    relay_reordered_indices = [202, 101]
    direct_positional = [relay_published[index] for index in [101, 202]]
    indexed = [relay_published[index] for index in relay_reordered_indices]
    relay_fixture = {
        "evidence_label": "synthetic_source_contract",
        "published_by_request_index": {
            str(key): value for key, value in relay_published.items()
        },
        "next_order": relay_reordered_indices,
        "direct_positional_values": direct_positional,
        "request_indexed_values": indexed,
        "direct_positional_misroutes_after_reorder": direct_positional != indexed,
        "request_indexed_relay_pass": indexed == [537, 759],
        "pinned_filter_merge_invalidates_direct_carry": True,
    }

    result = {
        "schema_version": 1,
        "classification": "invariant_level_falsification",
        "analysis_pass": (
            all_request_hashes_match
            and all_final_frames_match_rows
            and fixture["pass"]
            and bool(prefill_divergences)
            and bool(verify_divergences)
        ),
        "semantic_equivalence": False,
        "evidence_labels": {
            "request_rows_and_streams": "measured_retained_producer",
            "cycle_boundaries": "derived_from_measured_cumulative_sse",
            "worker_roles_and_state_equations": "pinned_source",
            "fixture_draft_proposals": "synthetic",
            "cache_interpretation": "measured_plus_observer_contract",
        },
        "inputs": {
            "terminal": {
                "path": str(args.terminal),
                "sha256": sha256(args.terminal),
            },
            "raw_root": str(args.raw_root),
            "pinned_worker": {
                "path": str(args.pinned_worker),
                "sha256": sha256(args.pinned_worker),
                "required_line_numbers": source_lines["worker"],
            },
            "pinned_info": {
                "path": str(args.pinned_info),
                "sha256": sha256(args.pinned_info),
                "required_line_numbers": source_lines["info"],
            },
            "prior_repair_patch": {
                "path": str(args.repair_patch),
                "sha256": sha256(args.repair_patch),
            },
            "endpoint_runner": {
                "path": str(args.endpoint_runner),
                "sha256": sha256(args.endpoint_runner),
                "required_line_numbers": source_lines["runner"],
            },
            "candidate_server_log": {
                "path": str(args.candidate_server_log),
                "sha256": sha256(args.candidate_server_log),
                "stream_interval": 1,
                "incremental_streaming_output": False,
                "speculative_num_draft_tokens": BLOCK_SIZE,
            },
        },
        "observer_integrity": {
            "all_32_request_hashes_match_between_arms": all_request_hashes_match,
            "all_64_final_sse_frames_match_terminal_rows": all_final_frames_match_rows,
            "control_frames_are_one_token_each": all(
                count == 358 for count in frame_counts["control"].values()
            ),
            "candidate_frame_counts": frame_counts["candidate"],
        },
        "divergence_summary": {
            "divergent_request_count": len(divergences),
            "divergent_request_indices": [
                item["request_index"] for item in divergences
            ],
            "prefill_divergent_request_indices": [
                item["request_index"] for item in prefill_divergences
            ],
            "request_order_first_divergence": earliest_request_order,
            "earliest_verify_cycle_ordinal": earliest_verify_ordinal,
            "all": divergences,
        },
        "state_localization": {
            "prefill_boundary": (
                "Requests 2, 27, and 28 differ at output token zero.  The pinned "
                "DFlash prefill path returns target_worker.next_token_ids directly, "
                "before verify acceptance, bonus settlement, KV commit advancement, "
                "or next-cycle relay."
            ),
            "first_verify_boundary": (
                "Request 25 has the same prefill token as AR, then differs in verify "
                "cycle 1 with a one-token emission.  With zero accepted drafts this "
                "token is the target bonus.  The visible pending seed equals AR, so "
                "the first target-verify result or its prefill-to-verify sequence/KV "
                "state is already non-equivalent."
            ),
            "later_cycle_boundary": (
                "Every later first difference is reconstructed at an exact emission "
                "boundary and classified as accepted-prefix or bonus output.  The "
                "retained producer did not persist verifier logits, verified_id, KV "
                "locations, or committed-length tensors, so it cannot distinguish a "
                "wrong target-verify result from wrong hidden KV/length state."
            ),
            "actual_wall_clock_first_divergence_order_is_unavailable": (
                "SSE frames have no per-frame timestamps; request/cycle ordering is "
                "reported deterministically by request index and cycle ordinal."
            ),
        },
        "cache_accounting": {
            "per_request_equal": control_cache == candidate_cache,
            "control_total_cached_tokens": sum(control_cache),
            "candidate_total_cached_tokens": sum(candidate_cache),
            "aggregate_equal": sum(control_cache) == sum(candidate_cache),
            "control_zero_cache_request_indices": control_zero,
            "candidate_zero_cache_request_indices": candidate_zero,
            "classification": "prompt_prefix_cache_ownership_shift_not_decode_kv_trace",
            "interpretation": (
                "The per-request equality gate remains failed.  Both arms report the "
                "same aggregate 15,515 cached prompt tokens (29 x 535), but the three "
                "zero-hit request indices rotate.  cached_tokens is response metadata "
                "for prompt-prefix reuse; it is not an observation of DFlash decode "
                "KV contents or kv_committed_len."
            ),
        },
        "deterministic_multicycle_fixture": {
            "path": str(args.fixture_output),
            "sha256": sha256(args.fixture_output),
            "pass": fixture["pass"],
            "selected_cycle_indices": fixture["selected_cycle_indices"],
        },
        "request_indexed_relay_fixture": relay_fixture,
        "repair_disposition": {
            "prior_patch": "rejected_as_sufficient_exact_repair",
            "reason": (
                "Forcing FutureMap request-indexed relay repairs the synthetic reorder "
                "fixture, but the pinned filter/merge path already disables direct "
                "carry after reorder and three measured failures occur in prefill "
                "before any relay.  The retained evidence therefore falsifies the "
                "relay-only hypothesis and cannot support that patch as an exact fix."
            ),
            "smallest_exact_repair_proven": None,
        },
        "terminal_decision": (
            "The endpoint's lossless target-semantics invariant is falsified at or "
            "before DFlash target prefill, and independently at the first verify "
            "transition.  No source-complete exact repair is justified from the "
            "retained state."
        ),
    }
    atomic_json(args.result_output, result)
    return 0 if result["analysis_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
