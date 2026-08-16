#!/usr/bin/env python3
"""Consume one candidate-only capture against the immutable AR endpoint terminal."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

from summarize_request_state_capture import atomic, load, load_events, sha256

ARM = "dflash-depth4-c32"
PHASES = ("target_prefill", "first_target_step")


def rows_by_index(terminal: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(row["index"]): row for row in terminal["rows"]}


def compare_request_and_response(
    ar_row: dict[str, Any], candidate_row: dict[str, Any]
) -> list[dict[str, Any]]:
    differences = []
    for field in (
        "request_sha256",
        "token_ids",
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "finish_reason",
    ):
        if ar_row.get(field) != candidate_row.get(field):
            differences.append(
                {"field": field, "ar": ar_row.get(field), "candidate": candidate_row.get(field)}
            )
    return differences


def compare_event(
    event: dict[str, Any], ar_row: dict[str, Any]
) -> list[dict[str, Any]]:
    expected = [int(value) for value in ar_row["token_ids"]]
    differences: list[dict[str, Any]] = []

    def check(field: str, observed: Any, wanted: Any) -> None:
        if observed != wanted:
            differences.append(
                {"field": field, "ar_expected": wanted, "candidate_observed": observed}
            )

    if event["phase"] == "target_prefill":
        check("target_prefill_output", int(event["target_prefill_output"]), expected[0])
        check("target_top1", int(event["target_top1"]), expected[0])
        accounting = event["prompt_cache_accounting"]
        check(
            "prompt_cache_accounting_total",
            int(accounting["prefix_tokens"]) + int(accounting["fresh_tokens"]),
            int(accounting["total_tokens"]),
        )
        check("sequence_length_after", int(event["sequence_length_after"]), int(ar_row["prompt_tokens"]))
        return differences

    accepted = [int(value) for value in event["accepted_prefix"]]
    emitted = [int(value) for value in event["emitted_stream_tokens"]]
    commit_length = int(event["commit_length"])
    check("verified_id", int(event["verified_id"]), expected[0])
    check("target_top1_first", int(event["target_top1"][0]), expected[1])
    check("accepted_prefix", accepted, expected[1 : 1 + len(accepted)])
    check("emitted_stream_tokens", emitted, expected[1 : 1 + commit_length])
    check("bonus_token", int(event["bonus_token"]), expected[1 + len(accepted)])
    check("commit_length", len(emitted), commit_length)
    check(
        "sequence_length_delta",
        int(event["sequence_length_after"]) - int(event["sequence_length_before"]),
        commit_length,
    )
    return differences


def classify(first: dict[str, Any] | None, endpoint_match: bool) -> str:
    if first is None:
        return "candidate_observer_valid_endpoint_match" if endpoint_match else "candidate_endpoint_divergence_after_first_target_step"
    phase = first["phase"]
    field = first["difference"]["field"]
    if phase == "target_prefill":
        return "localized_target_prefill_output_or_accounting"
    if field == "verified_id":
        return "localized_prefill_to_verify_seed"
    if field in {"target_top1_first", "accepted_prefix", "bonus_token"}:
        return "localized_first_target_verifier"
    return "localized_first_verify_commit_or_stream"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ar-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-states", type=pathlib.Path, required=True)
    parser.add_argument("--result", type=pathlib.Path, required=True)
    parser.add_argument("--terminal", type=pathlib.Path, required=True)
    args = parser.parse_args()

    ar_terminal = load(args.ar_terminal)
    candidate_terminal = load(args.candidate_terminal)
    events = load_events(args.candidate_states, candidate_terminal)
    ar_rows = rows_by_index(ar_terminal)
    candidate_rows = rows_by_index(candidate_terminal)
    expected_keys = {(phase, index) for phase in PHASES for index in range(32)}
    missing = sorted(expected_keys - events.keys())
    extra = sorted(events.keys() - expected_keys)
    endpoint_complete = bool(
        candidate_terminal.get("pass")
        and candidate_terminal.get("complete_requests") == 32
        and candidate_terminal.get("raw_token_ids_present")
    )
    endpoint_differences = {
        str(index): compare_request_and_response(ar_rows[index], candidate_rows[index])
        for index in range(32)
    }
    endpoint_match = not any(endpoint_differences.values())
    comparisons = []
    for key in sorted(events):
        phase, index = key
        comparisons.append(
            {
                "phase": phase,
                "request_index": index,
                "request_id": events[key]["request_id"],
                "differences": compare_event(events[key], ar_rows[index]),
            }
        )
    first = next(
        (
            {
                "phase": item["phase"],
                "request_index": item["request_index"],
                "request_id": item["request_id"],
                "difference": item["differences"][0],
            }
            for item in comparisons
            if item["differences"]
        ),
        None,
    )
    valid_capture = endpoint_complete and not missing and not extra
    result = {
        "schema_version": 1,
        "classification": classify(first, endpoint_match) if valid_capture else "invalid_candidate_observer_attempt",
        "valid_scientific_capture": valid_capture,
        "candidate_endpoint_complete": endpoint_complete,
        "observer_coverage": {
            "event_count": len(events),
            "missing": [{"phase": phase, "request_index": index} for phase, index in missing],
            "extra": [{"phase": phase, "request_index": index} for phase, index in extra],
        },
        "endpoint_exact_match": endpoint_match,
        "endpoint_differences": endpoint_differences,
        "first_differing_captured_state": first,
        "comparisons": comparisons,
        "events": [events[key] for key in sorted(events)],
        "ar_producer_replayed": False,
        "performance_claim_authorized": False,
    }
    atomic(args.result, result)
    terminal = {
        "schema_version": 1,
        "classification": result["classification"],
        "valid_scientific_capture": valid_capture,
        "candidate_endpoint_complete": endpoint_complete,
        "observer_coverage_pass": not missing and not extra,
        "endpoint_exact_match": endpoint_match,
        "first_differing_captured_state": first,
        "result": str(args.result),
        "result_sha256": sha256(args.result),
        "inputs": {
            "ar_terminal": str(args.ar_terminal),
            "ar_terminal_sha256": sha256(args.ar_terminal),
            "candidate_terminal_sha256": sha256(args.candidate_terminal),
            "candidate_states_sha256": sha256(args.candidate_states),
        },
        "ar_producer_replayed": False,
        "performance_claim_authorized": False,
    }
    atomic(args.terminal, terminal)
    return 0 if valid_capture else 74


if __name__ == "__main__":
    raise SystemExit(main())
