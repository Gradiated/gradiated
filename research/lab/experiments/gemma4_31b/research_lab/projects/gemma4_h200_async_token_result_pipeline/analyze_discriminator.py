#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics


FRONTIER_SECONDS_PER_REQUEST = 0.6743258590313417
OUTPUT_TOKENS = 358
CONCURRENCY = 32
PROMOTION_FRACTION = 0.03


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def load_audit(path: pathlib.Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def in_window(
    rows: list[dict[str, object]],
    arm: str,
    terminal: dict[str, object],
) -> list[dict[str, object]]:
    begin = float(terminal["started_monotonic_s"])
    end = float(terminal["ended_monotonic_s"])
    return [
        row
        for row in rows
        if row.get("arm") == arm
        and begin <= float(row["monotonic_s"]) <= end
    ]


def boundary(rows: list[dict[str, object]]) -> dict[str, object]:
    by_generation: dict[int, dict[str, float]] = {}
    decode_generations = {
        int(row["generation"])
        for row in rows
        if row["event"] == "process_decode_entry" and row.get("generation") is not None
    }
    for row in rows:
        generation = row.get("generation")
        if generation is None or int(generation) not in decode_generations:
            continue
        bucket = by_generation.setdefault(int(generation), {})
        if row["event"] == "copy_to_cpu":
            bucket["copy_us"] = float(row["elapsed_us"])
        elif row["event"] == "copy_event_synchronize":
            bucket["sync_us"] = float(row["elapsed_us"])
        elif row["event"] == "normalize_decode_outputs":
            bucket["normalize_us"] = float(row["elapsed_us"])
        elif row["event"] == "process_decode_return":
            bucket["process_us"] = float(row["elapsed_us"])
    complete = [
        {
            "generation": generation,
            **values,
            "inclusive_us": values["copy_us"]
            + values["sync_us"]
            + values["normalize_us"],
        }
        for generation, values in by_generation.items()
        if {"copy_us", "sync_us", "normalize_us", "process_us"} <= values.keys()
    ]
    inclusive = [float(row["inclusive_us"]) for row in complete]
    return {
        "complete_boundaries": len(complete),
        "inclusive_us": {
            "median": statistics.median(inclusive) if inclusive else None,
            "p10": percentile(inclusive, 0.10),
            "p90": percentile(inclusive, 0.90),
        },
        "copy_us_median": (
            statistics.median(float(row["copy_us"]) for row in complete)
            if complete
            else None
        ),
        "sync_us_median": (
            statistics.median(float(row["sync_us"]) for row in complete)
            if complete
            else None
        ),
        "normalize_us_median": (
            statistics.median(float(row["normalize_us"]) for row in complete)
            if complete
            else None
        ),
        "process_us_median": (
            statistics.median(float(row["process_us"]) for row in complete)
            if complete
            else None
        ),
        "rows": complete,
    }


def overlap_pass(rows: list[dict[str, object]]) -> bool:
    entry_after = {
        int(row["after_generation"])
        for row in rows
        if row["event"] == "run_batch_entry"
        and row.get("after_generation") is not None
    }
    processed = {
        int(row["generation"])
        for row in rows
        if row["event"] == "process_decode_entry" and row.get("generation") is not None
    }
    nonterminal = processed - {max(processed)} if processed else set()
    return bool(nonterminal) and nonterminal <= entry_after


def host_slot_lifetime(rows: list[dict[str, object]]) -> dict[str, object]:
    processed: dict[int, float] = {}
    last_generation_by_slot: dict[int, int] = {}
    violations: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda item: float(item["monotonic_s"])):
        if row["event"] == "process_decode_entry" and row.get("generation") is not None:
            processed[int(row["generation"])] = float(row["monotonic_s"])
            continue
        if (
            row["event"] != "copy_to_cpu"
            or row.get("generation") is None
            or row.get("slot") is None
        ):
            continue
        generation = int(row["generation"])
        slot = int(row["slot"])
        prior_generation = last_generation_by_slot.get(slot)
        if prior_generation is not None:
            consumed_at = processed.get(prior_generation)
            replacement_at = float(row["monotonic_s"])
            if consumed_at is None or consumed_at >= replacement_at:
                violations.append(
                    {
                        "slot": slot,
                        "overwritten_generation": prior_generation,
                        "replacement_generation": generation,
                        "replacement_monotonic_s": replacement_at,
                        "prior_process_monotonic_s": consumed_at,
                    }
                )
        last_generation_by_slot[slot] = generation
    return {
        "pass": not violations,
        "violation_count": len(violations),
        "first_violation": violations[0] if violations else None,
        "last_violation": violations[-1] if violations else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--audit", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    control = json.loads(args.control.read_text())
    candidate = json.loads(args.candidate.read_text())
    audit = load_audit(args.audit)
    control_audit = in_window(audit, "control", control)
    candidate_audit = in_window(audit, "candidate", candidate)
    control_boundary = boundary(control_audit)
    candidate_boundary = boundary(candidate_audit)

    semantic_mismatches = []
    for index, (control_row, candidate_row) in enumerate(
        zip(control["rows"], candidate["rows"], strict=True)
    ):
        differing_fields = [
            field
            for field in (
                "request_sha256",
                "output_ids",
                "normalized_events",
                "prompt_tokens",
                "completion_tokens",
            )
            if control_row[field] != candidate_row[field]
        ]
        if not differing_fields:
            continue
        control_ids = control_row["output_ids"]
        candidate_ids = candidate_row["output_ids"]
        first_differing_token = next(
            (
                token_index
                for token_index, (control_id, candidate_id) in enumerate(
                    zip(control_ids, candidate_ids)
                )
                if control_id != candidate_id
            ),
            None,
        )
        semantic_mismatches.append(
            {
                "request_index": index,
                "differing_fields": differing_fields,
                "first_differing_token_index": first_differing_token,
            }
        )
    paired_semantics = not semantic_mismatches
    cache_accounting_pass = control["cache"] == candidate["cache"]
    candidate_copy_rows = [
        row for row in candidate_audit if row["event"] == "copy_to_cpu"
    ]
    candidate_path_pass = (
        bool(candidate_copy_rows)
        and all(row["path"] == "two_slot_pinned" for row in candidate_copy_rows)
        and all(bool(row["pinned"]) for row in candidate_copy_rows)
        and not any(
            row["event"] == "candidate_fallback" for row in candidate_audit
        )
    )
    slot_rows = [
        row for row in candidate_audit if row["event"] == "slot_reuse_check"
    ]
    device_copy_completion_slot_reuse_pass = (
        bool(slot_rows)
        and {int(row["slot"]) for row in slot_rows} == {0, 1}
        and all(bool(row["safe"]) for row in slot_rows)
    )
    host_lifetime = host_slot_lifetime(candidate_audit)
    slot_safety_pass = (
        device_copy_completion_slot_reuse_pass and bool(host_lifetime["pass"])
    )
    overlap = overlap_pass(candidate_audit)
    conservative_step_saving_us = max(
        0.0,
        float(control_boundary["inclusive_us"]["p10"])
        - float(candidate_boundary["inclusive_us"]["p90"]),
    )
    conservative_saving_seconds_per_request = (
        conservative_step_saving_us * OUTPUT_TOKENS / 1_000_000 / CONCURRENCY
    )
    conservative_fraction = (
        conservative_saving_seconds_per_request / FRONTIER_SECONDS_PER_REQUEST
    )
    semantics_pass = (
        bool(control["pass"])
        and bool(candidate["pass"])
        and paired_semantics
        and cache_accounting_pass
    )
    endpoint_gate_pass = (
        semantics_pass
        and candidate_path_pass
        and slot_safety_pass
        and overlap
        and conservative_fraction >= PROMOTION_FRACTION
    )
    result = {
        "schema_version": 1,
        "status": "terminal",
        "candidate": "two_slot_pinned_async_token_result_pipeline",
        "pass": endpoint_gate_pass,
        "classification": (
            "promote_to_one_exact_c32_pair"
            if endpoint_gate_pass
            else (
                "candidate_semantic_and_two_slot_host_lifetime_reject"
                if not paired_semantics and not host_lifetime["pass"]
                else (
                    "candidate_semantic_reject"
                    if not paired_semantics
                    else (
                        "two_slot_host_lifetime_reject"
                        if not host_lifetime["pass"]
                        else "bound_below_3pct"
                    )
                )
            )
        ),
        "control_pass": bool(control["pass"]),
        "candidate_pass": bool(candidate["pass"]),
        "bit_exact_tokens_events_and_order_pass": paired_semantics,
        "semantic_mismatch_count": len(semantic_mismatches),
        "semantic_mismatches": semantic_mismatches,
        "cache_usage_accounting_pass": cache_accounting_pass,
        "candidate_path_pass": candidate_path_pass,
        "device_copy_completion_slot_reuse_pass": (
            device_copy_completion_slot_reuse_pass
        ),
        "two_slot_host_lifetime": host_lifetime,
        "two_slot_safety_pass": slot_safety_pass,
        "next_forward_precedes_prior_host_wait_pass": overlap,
        "control_boundary": control_boundary,
        "candidate_boundary": candidate_boundary,
        "decision": {
            "conservative_step_saving_us": conservative_step_saving_us,
            "output_tokens": OUTPUT_TOKENS,
            "concurrency": CONCURRENCY,
            "conservative_saving_seconds_per_request": conservative_saving_seconds_per_request,
            "frontier_seconds_per_request": FRONTIER_SECONDS_PER_REQUEST,
            "conservative_whole_request_fraction": conservative_fraction,
            "required_fraction": PROMOTION_FRACTION,
            "conditional_exact_c32_required": endpoint_gate_pass,
        },
    }
    atomic_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
