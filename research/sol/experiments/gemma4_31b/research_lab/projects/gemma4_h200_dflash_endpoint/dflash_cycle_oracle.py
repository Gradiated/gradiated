#!/usr/bin/env python3
"""Pure-Python one-cycle semantic oracle for greedy DFlash verification.

The pending seed was emitted by the preceding target step but is not yet in
the committed KV prefix.  A verify block consumes that seed followed by draft
proposals.  If A proposals match target top-1 IDs, the cycle:

* emits A accepted proposals followed by one target bonus token;
* commits the seed plus A accepted proposals to KV; and
* carries the bonus as the next cycle's pending seed.

The oracle deliberately has no torch/SGLang dependency so a captured cycle can
be checked offline before any endpoint comparison.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


PHASE_ORDER = (
    "capture_shape",
    "verifier",
    "acceptance",
    "bonus",
    "kv_commit",
    "committed_length",
    "next_state_relay",
)


def _issue(issues: list[dict[str, Any]], phase: str, invariant: str, **detail: Any) -> None:
    issues.append({"phase": phase, "invariant": invariant, **detail})


def evaluate_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    draft = [int(x) for x in cycle["draft_tokens"]]
    target = [int(x) for x in cycle["verifier_top1_ids"]]
    top1_logits = [float(x) for x in cycle["verifier_top1_logits"]]
    positions = [int(x) for x in cycle["kv_write_positions"]]
    write_locs = [int(x) for x in cycle["kv_write_locations"]]
    before = int(cycle["committed_length_before"])
    block_size = int(cycle["block_size"])
    issues: list[dict[str, Any]] = []

    for name, values in (
        ("draft_tokens", draft),
        ("verifier_top1_ids", target),
        ("verifier_top1_logits", top1_logits),
        ("kv_write_positions", positions),
        ("kv_write_locations", write_locs),
    ):
        if len(values) != block_size:
            _issue(
                issues,
                "capture_shape",
                f"{name}_has_block_size_entries",
                expected=block_size,
                observed=len(values),
            )
    if any(not math.isfinite(x) for x in top1_logits):
        _issue(issues, "verifier", "verifier_top1_logits_are_finite")

    ar_cycle = [int(x) for x in cycle.get("ar_cycle_tokens", [])]
    if ar_cycle and target and target[0] != ar_cycle[0]:
        _issue(
            issues,
            "verifier",
            "first_verifier_id_equals_deterministic_ar_next_id",
            expected=ar_cycle[0],
            observed=target[0],
        )

    max_drafts = max(0, min(len(draft) - 1, len(target) - 1))
    expected_accepted = 0
    while (
        expected_accepted < max_drafts
        and draft[expected_accepted + 1] == target[expected_accepted]
    ):
        expected_accepted += 1
    expected_prefix = draft[1 : 1 + expected_accepted]
    expected_bonus = target[expected_accepted] if target else None
    expected_emitted = expected_prefix + ([] if expected_bonus is None else [expected_bonus])
    expected_commit_length = expected_accepted + 1

    accepted_prefix = [int(x) for x in cycle["accepted_prefix"]]
    if accepted_prefix != expected_prefix:
        _issue(
            issues,
            "acceptance",
            "accepted_prefix_is_maximal_target_matching_draft_prefix",
            expected=expected_prefix,
            observed=accepted_prefix,
        )
    if int(cycle["accepted_draft_count"]) != expected_accepted:
        _issue(
            issues,
            "acceptance",
            "accepted_draft_count_matches_prefix",
            expected=expected_accepted,
            observed=int(cycle["accepted_draft_count"]),
        )

    bonus = int(cycle["bonus_token"])
    if expected_bonus is not None and bonus != expected_bonus:
        _issue(
            issues,
            "bonus",
            "bonus_is_target_id_at_first_rejected_depth",
            expected=expected_bonus,
            observed=bonus,
        )
    emitted = [int(x) for x in cycle["emitted_tokens"]]
    if emitted != expected_emitted:
        _issue(
            issues,
            "bonus",
            "emitted_tokens_are_accepted_prefix_plus_bonus",
            expected=expected_emitted,
            observed=emitted,
        )
    if ar_cycle and emitted != ar_cycle[: len(emitted)]:
        _issue(
            issues,
            "verifier",
            "cycle_emission_equals_deterministic_ar",
            expected=ar_cycle[: len(emitted)],
            observed=emitted,
        )

    expected_positions = list(range(before, before + block_size))
    if positions != expected_positions:
        _issue(
            issues,
            "kv_commit",
            "verify_write_positions_are_contiguous_from_committed_prefix",
            expected=expected_positions,
            observed=positions,
        )
    if len(set(write_locs)) != len(write_locs):
        _issue(issues, "kv_commit", "verify_write_locations_are_unique")
    committed_locs = [int(x) for x in cycle["committed_kv_write_locations"]]
    if committed_locs != write_locs[:expected_commit_length]:
        _issue(
            issues,
            "kv_commit",
            "committed_kv_locations_are_seed_plus_accepted_draft_locations",
            expected=write_locs[:expected_commit_length],
            observed=committed_locs,
        )

    observed_commit_length = int(cycle["commit_length"])
    if observed_commit_length != expected_commit_length:
        _issue(
            issues,
            "committed_length",
            "commit_length_is_accepted_drafts_plus_one_seed",
            expected=expected_commit_length,
            observed=observed_commit_length,
        )
    expected_after = before + expected_commit_length
    if int(cycle["committed_length_after"]) != expected_after:
        _issue(
            issues,
            "committed_length",
            "committed_length_advances_by_commit_length",
            expected=expected_after,
            observed=int(cycle["committed_length_after"]),
        )

    next_ar = int(cycle["next_ar_token"])
    if expected_bonus is not None and next_ar != expected_bonus:
        _issue(
            issues,
            "next_state_relay",
            "ordinary_ar_at_committed_boundary_equals_bonus",
            expected=expected_bonus,
            observed=next_ar,
        )
    if int(cycle["next_cycle_seed"]) != bonus:
        _issue(
            issues,
            "next_state_relay",
            "next_cycle_seed_equals_published_bonus",
            expected=bonus,
            observed=int(cycle["next_cycle_seed"]),
        )
    if int(cycle["next_cycle_committed_length"]) != int(
        cycle["committed_length_after"]
    ):
        _issue(
            issues,
            "next_state_relay",
            "next_cycle_length_equals_published_committed_length",
            expected=int(cycle["committed_length_after"]),
            observed=int(cycle["next_cycle_committed_length"]),
        )

    earliest = None
    for phase in PHASE_ORDER:
        if any(item["phase"] == phase for item in issues):
            earliest = phase
            break
    return {
        "schema_version": 1,
        "request_id": cycle.get("request_id"),
        "cycle_index": cycle.get("cycle_index"),
        "pass": not issues,
        "earliest_divergence_phase": earliest,
        "derived": {
            "expected_accepted_draft_count": expected_accepted,
            "expected_accepted_prefix": expected_prefix,
            "expected_bonus_token": expected_bonus,
            "expected_emitted_tokens": expected_emitted,
            "expected_commit_length": expected_commit_length,
            "expected_committed_length_after": expected_after,
        },
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_cycle(json.loads(args.input.read_text()))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
