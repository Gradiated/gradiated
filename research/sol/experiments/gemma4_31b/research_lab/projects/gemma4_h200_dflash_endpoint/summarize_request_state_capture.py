#!/usr/bin/env python3
"""Validate and localize one matched AR/DFlash exact-c32 state capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

from request_state_observer import canonical_bytes, validate_event

AR = "ar-c32"
DFLASH = "dflash-depth4-c32"
PHASES = ("target_prefill", "first_target_step")


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text())


def load_events(
    path: pathlib.Path,
    terminal: dict[str, Any],
) -> dict[tuple[str, int], dict[str, Any]]:
    rid_to_index = {
        str(row["request_id"]): int(row["index"]) for row in terminal["rows"]
    }
    if len(rid_to_index) != len(terminal["rows"]):
        raise ValueError(f"{path}: endpoint terminal contains duplicate request ids")
    events: dict[tuple[str, int], dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        event = json.loads(line)
        validate_event(event)
        expected = event.pop("event_sha256", None)
        observed = hashlib.sha256(canonical_bytes(event)).hexdigest()
        event["event_sha256"] = expected
        if expected != observed:
            raise ValueError(f"{path}:{line_number}: event digest mismatch")
        request_id = str(event["request_id"])
        if request_id not in rid_to_index:
            raise ValueError(
                f"{path}:{line_number}: request id absent from endpoint terminal"
            )
        request_index = rid_to_index[request_id]
        event["request_index"] = request_index
        key = (str(event["phase"]), request_index)
        if key in events:
            raise ValueError(f"{path}:{line_number}: duplicate event {key}")
        events[key] = event
    return events


def endpoint_rows(terminal: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(row["index"]): row for row in terminal["rows"]}


def compare_endpoint_identity(
    current: dict[str, Any], prior: dict[str, Any]
) -> dict[str, Any]:
    current_rows = endpoint_rows(current)
    prior_rows = endpoint_rows(prior)
    indices = sorted(set(current_rows) | set(prior_rows))
    mismatches = []
    for index in indices:
        left, right = current_rows.get(index), prior_rows.get(index)
        if left is None or right is None:
            mismatches.append({"request_index": index, "field": "row_presence"})
            continue
        for field in (
            "request_sha256",
            "token_ids",
            "prompt_tokens",
            "completion_tokens",
            "cached_tokens",
            "finish_reason",
        ):
            if left.get(field) != right.get(field):
                mismatches.append({"request_index": index, "field": field})
    return {
        "pass": not mismatches,
        "mismatches": mismatches,
        "requests_compared": len(indices),
    }


def event_differences(
    ar: dict[str, Any], dflash: dict[str, Any]
) -> list[dict[str, Any]]:
    phase = str(ar["phase"])
    differences = []

    def compare(name: str, left: Any, right: Any) -> None:
        if left != right:
            differences.append({"field": name, "ar": left, "dflash": right})

    compare("sequence_length_before", ar["sequence_length_before"], dflash["sequence_length_before"])
    if phase == "target_prefill":
        compare("target_top1", ar["target_top1"], dflash["target_top1"])
        compare(
            "target_prefill_output",
            ar["target_prefill_output"],
            dflash["target_prefill_output"],
        )
        compare("sequence_length_after", ar["sequence_length_after"], dflash["sequence_length_after"])
        compare("kv_content_sha256", ar["kv_content_sha256"], dflash["kv_content_sha256"])
        compare(
            "prompt_cache_accounting",
            ar["prompt_cache_accounting"],
            dflash["prompt_cache_accounting"],
        )
    else:
        compare("verified_id", ar["verified_id"], dflash["verified_id"])
        dflash_top1 = dflash["target_top1"][0]
        compare("target_top1", ar["target_top1"], dflash_top1)
        compare("bonus_token", ar["bonus_token"], dflash["bonus_token"])
        compare(
            "emitted_first_token",
            ar["emitted_stream_tokens"][0],
            dflash["emitted_stream_tokens"][0],
        )
        if int(dflash.get("commit_length", 1)) == 1:
            compare("sequence_length_after", ar["sequence_length_after"], dflash["sequence_length_after"])
            compare("kv_content_sha256", ar["kv_content_sha256"], dflash["kv_content_sha256"])
    return differences


def classification(first: dict[str, Any] | None) -> str:
    if first is None:
        return "observer_coverage_falsification"
    phase, field = first["phase"], first["difference"]["field"]
    if phase == "target_prefill":
        if field in {"target_top1", "target_prefill_output"}:
            return "localized_target_prefill_output"
        return "localized_target_prefill_state"
    if field == "verified_id":
        return "localized_prefill_to_verify_seed"
    if field in {"target_top1", "bonus_token"}:
        return "localized_first_target_verifier"
    return "localized_first_verify_commit_or_stream"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--prior", type=pathlib.Path, required=True)
    parser.add_argument("--result", type=pathlib.Path, required=True)
    parser.add_argument("--terminal", type=pathlib.Path, required=True)
    args = parser.parse_args()

    terminals = {
        arm: load(args.root / "results" / arm / "TERMINAL.json")
        for arm in (AR, DFLASH)
    }
    events = {
        arm: load_events(args.root / "states" / f"{arm}.jsonl", terminals[arm])
        for arm in (AR, DFLASH)
    }
    expected_keys = {(phase, index) for phase in PHASES for index in range(32)}
    coverage = {
        arm: {
            "event_count": len(values),
            "missing": [
                {"phase": phase, "request_index": index}
                for phase, index in sorted(expected_keys - values.keys())
            ],
            "extra": [
                {"phase": phase, "request_index": index}
                for phase, index in sorted(values.keys() - expected_keys)
            ],
        }
        for arm, values in events.items()
    }
    endpoint_complete = all(
        terminal.get("pass")
        and terminal.get("complete_requests") == 32
        and terminal.get("raw_token_ids_present")
        for terminal in terminals.values()
    )
    prior = load(args.prior)
    prior_arms = {"ar-c32": prior["control"], "dflash-depth4-c32": prior["candidate"]}
    pass_through = {
        arm: compare_endpoint_identity(terminals[arm], prior_arms[arm])
        for arm in (AR, DFLASH)
    }

    comparisons = []
    for phase in PHASES:
        for index in range(32):
            key = (phase, index)
            if key not in events[AR] or key not in events[DFLASH]:
                continue
            differences = event_differences(events[AR][key], events[DFLASH][key])
            comparisons.append(
                {
                    "phase": phase,
                    "request_index": index,
                    "differences": differences,
                }
            )
    first = None
    for item in comparisons:
        if item["differences"]:
            first = {
                "phase": item["phase"],
                "request_index": item["request_index"],
                "difference": item["differences"][0],
            }
            break
    coverage_pass = all(
        not value["missing"] and not value["extra"] for value in coverage.values()
    )
    observer_pass_through = all(value["pass"] for value in pass_through.values())
    valid = endpoint_complete and coverage_pass and observer_pass_through
    result = {
        "schema_version": 1,
        "classification": classification(first) if valid else "invalid_observer_attempt",
        "valid_scientific_capture": valid,
        "endpoint_complete": endpoint_complete,
        "observer_coverage": coverage,
        "observer_pass_through": pass_through,
        "first_differing_captured_state": first,
        "comparisons": comparisons,
        "events": {
            arm: [events[arm][key] for key in sorted(events[arm])]
            for arm in (AR, DFLASH)
        },
        "request_25_first_step": next(
            (
                item
                for item in comparisons
                if item["phase"] == "first_target_step"
                and item["request_index"] == 25
            ),
            None,
        ),
        "performance_claim_authorized": False,
        "source_repair_implemented": False,
    }
    atomic(args.result, result)
    terminal = {
        "schema_version": 1,
        "classification": result["classification"],
        "valid_scientific_capture": valid,
        "endpoint_complete": endpoint_complete,
        "observer_coverage_pass": coverage_pass,
        "observer_pass_through": observer_pass_through,
        "first_differing_captured_state": first,
        "request_25_first_step": result["request_25_first_step"],
        "result": str(args.result),
        "result_sha256": sha256(args.result),
        "raw_artifacts": {
            "ar_terminal_sha256": sha256(args.root / "results" / AR / "TERMINAL.json"),
            "dflash_terminal_sha256": sha256(
                args.root / "results" / DFLASH / "TERMINAL.json"
            ),
            "ar_states_sha256": sha256(args.root / "states" / f"{AR}.jsonl"),
            "dflash_states_sha256": sha256(
                args.root / "states" / f"{DFLASH}.jsonl"
            ),
        },
        "performance_claim_authorized": False,
    }
    atomic(args.terminal, terminal)
    return 0 if valid else 74


if __name__ == "__main__":
    raise SystemExit(main())
