#!/usr/bin/env python3
from __future__ import annotations

import collections
import hashlib
import json
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
ARTIFACT = (
    PROJECT
    / "artifacts/variable-compaction-20260724t134337Z/retrieved/artifacts"
)


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def load_events(arm: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (ARTIFACT / f"{arm}-component-events.jsonl")
        .read_text()
        .splitlines()
        if line
    ]


def stream(path: pathlib.Path) -> tuple[str, str]:
    request_id = ""
    chunks = []
    for line in path.read_text().splitlines():
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        item = json.loads(line[6:])
        request_id = request_id or item["id"]
        chunks.append((item.get("choices") or [{}])[0].get("text", ""))
    return request_id, "".join(chunks)


def request_map(arm: str, events: list[dict]) -> dict[str, tuple[str, int]]:
    result = {}
    request_id, _ = stream(
        ARTIFACT / f"{arm}-component-c1/response-00.sse"
    )
    result[request_id] = ("c1", 0)
    for path in sorted(
        (ARTIFACT / f"{arm}-component-c4").glob("response-*.sse")
    ):
        index = int(path.stem.rsplit("-", 1)[1])
        request_id, _ = stream(path)
        result[request_id] = ("c4", index)

    first_seen = {}
    for event_index, event in enumerate(events):
        for request_id in event["request_ids"]:
            first_seen.setdefault(request_id, event_index)
    mixed = sorted(
        (
            (request_id, event_index)
            for request_id, event_index in first_seen.items()
            if request_id not in result
        ),
        key=lambda item: item[1],
    )
    for index, (request_id, _) in enumerate(mixed):
        result[request_id] = ("mixed", index)
    return result


def per_request(
    events: list[dict], mapping: dict[str, tuple[str, int]]
) -> dict[tuple[str, int], list[dict]]:
    result = collections.defaultdict(list)
    for event in events:
        logit_offset = 0
        accepted_offset = 0
        for request_index, request_id in enumerate(event["request_ids"]):
            valid = event["producer_valid_lengths"][request_index]
            accepted = event["num_correct_drafts"][request_index] + 1
            result[mapping[request_id]].append(
                {
                    "producer_valid_length": valid,
                    "top2_ids": event["top2_ids"][
                        logit_offset : logit_offset + valid
                    ],
                    "top2_values": event["top2_values"][
                        logit_offset : logit_offset + valid
                    ],
                    "accepted_token_ids": event["accepted_token_ids"][
                        accepted_offset : accepted_offset + accepted
                    ],
                }
            )
            logit_offset += valid
            accepted_offset += accepted
        if logit_offset != len(event["top2_ids"]):
            raise RuntimeError("unconsumed_logit_rows")
        if accepted_offset != len(event["accepted_token_ids"]):
            raise RuntimeError("unconsumed_accepted_rows")
    return result


def counters(events: list[dict]) -> dict:
    fixed_rows = sum(
        12 * len(event["producer_valid_lengths"]) for event in events
    )
    valid_rows = sum(
        sum(event["producer_valid_lengths"]) for event in events
    )
    allocated = sum(event["allocated_kv_slots"] for event in events)
    retained = sum(event["retained_kv_slots"] for event in events)
    return {
        "events": len(events),
        "request_events": sum(
            len(event["producer_valid_lengths"]) for event in events
        ),
        "fixed_target_rows": fixed_rows,
        "valid_target_rows": valid_rows,
        "removed_target_rows": fixed_rows - valid_rows,
        "target_row_reduction_fraction": (fixed_rows - valid_rows) / fixed_rows,
        "allocated_kv_slots": allocated,
        "retained_kv_slots": retained,
        "accepted_tokens": sum(
            sum(value + 1 for value in event["num_correct_drafts"])
            for event in events
        ),
    }


def main() -> None:
    raw = json.loads((ARTIFACT / "COMPONENT_TERMINAL.json").read_text())
    control_events = load_events("control")
    candidate_events = load_events("candidate")
    control_map = request_map("control", control_events)
    candidate_map = request_map("candidate", candidate_events)
    control_requests = per_request(control_events, control_map)
    candidate_requests = per_request(candidate_events, candidate_map)

    rows = {}
    for key in sorted(control_requests):
        left = control_requests[key]
        right = candidate_requests[key]
        rows[f"{key[0]}-{key[1]}"] = {
            "control_events": len(left),
            "candidate_events": len(right),
            "exact_target_top2_and_acceptance": left == right,
            "exact_accepted_token_ids": [
                item["accepted_token_ids"] for item in left
            ]
            == [item["accepted_token_ids"] for item in right],
            "first_divergent_event": next(
                (
                    index
                    for index, (control, candidate) in enumerate(
                        zip(left, right)
                    )
                    if control != candidate
                ),
                None if len(left) == len(right) else min(len(left), len(right)),
            ),
        }

    text_rows = {}
    for phase, count in (("c1", 1), ("c4", 4)):
        for index in range(count):
            _, control_text = stream(
                ARTIFACT
                / f"control-component-{phase}/response-{index:02d}.sse"
            )
            _, candidate_text = stream(
                ARTIFACT
                / f"candidate-component-{phase}/response-{index:02d}.sse"
            )
            text_rows[f"{phase}-{index}"] = {
                "exact": control_text == candidate_text,
                "control_bytes": len(control_text.encode()),
                "candidate_bytes": len(candidate_text.encode()),
                "control_sha256": hashlib.sha256(
                    control_text.encode()
                ).hexdigest(),
                "candidate_sha256": hashlib.sha256(
                    candidate_text.encode()
                ).hexdigest(),
            }

    c4_inputs_match = (
        [
            row["request_sha256"]
            for row in json.loads(
                (
                    ARTIFACT
                    / "control-component-c4/TERMINAL.json"
                ).read_text()
            )["rows"]
        ]
        == [
            row["request_sha256"]
            for row in json.loads(
                (
                    ARTIFACT
                    / "candidate-component-c4/TERMINAL.json"
                ).read_text()
            )["rows"]
        ]
    )
    control_counters = counters(control_events)
    candidate_counters = counters(candidate_events)
    result = {
        "schema_version": 1,
        "classification": "valid_negative_component_terminal",
        "raw_component_terminal": "COMPONENT_TERMINAL.json",
        "comparator_correction": (
            "The raw aggregate paired flattened batch rows by shape and treated "
            "missing return_token_ids as empty exact lists. This offline consumer "
            "uses persisted response IDs to align c1/c4 logical requests, first "
            "arrival to align the staggered mixed requests, exact stream text, "
            "and request-local target top-2/acceptance slices."
        ),
        "coverage": raw["coverage"],
        "matched_request_inputs": {
            "c4": c4_inputs_match,
        },
        "request_local_exactness": rows,
        "response_text_exactness": text_rows,
        "all_c1_exact": rows["c1-0"]["exact_target_top2_and_acceptance"]
        and text_rows["c1-0"]["exact"],
        "all_mixed_exact": all(
            value["exact_target_top2_and_acceptance"]
            for key, value in rows.items()
            if key.startswith("mixed-")
        ),
        "c4_exact_requests": sum(
            value["exact_target_top2_and_acceptance"]
            for key, value in rows.items()
            if key.startswith("c4-")
        ),
        "c4_total_requests": 4,
        "first_divergence": {
            "row": "c4 all-one first target verification",
            "interpretation": (
                "Single-request and staggered mixed request-local consumers are "
                "exact, but simultaneous four-request compaction changes target "
                "logits/acceptance immediately for multiple matched requests. "
                "This localizes the correctness failure to multi-request compact "
                "row ownership/attention mapping, not producer validity."
            ),
        },
        "control_counters": control_counters,
        "candidate_counters": candidate_counters,
        "causal_delta": {
            "allocated_kv_slots_removed": (
                control_counters["allocated_kv_slots"]
                - candidate_counters["allocated_kv_slots"]
            ),
            "retained_kv_slots_delta": (
                candidate_counters["retained_kv_slots"]
                - control_counters["retained_kv_slots"]
            ),
            "accepted_tokens_delta": (
                candidate_counters["accepted_tokens"]
                - control_counters["accepted_tokens"]
            ),
        },
        "performance": {
            "reduced_shape_control_median_sum_ms": raw[
                "reduced_shape_control_median_sum_ms"
            ],
            "reduced_shape_candidate_median_sum_ms": raw[
                "reduced_shape_candidate_median_sum_ms"
            ],
            "reduced_shape_slowdown_fraction": (
                raw["reduced_shape_candidate_median_sum_ms"]
                / raw["reduced_shape_control_median_sum_ms"]
                - 1
            ),
            "full_shape_rows": [
                row
                for row in raw["shape_rows"]
                if all(value == 12 for value in row["shape"])
            ],
        },
        "admit_c32": False,
        "endpoint_pair_run": False,
        "decision": (
            "Reject this packet: simultaneous multi-request exactness fails and "
            "reduced compact shapes are slower. The preregistered c32 gate remains "
            "closed."
        ),
    }
    atomic(ARTIFACT / "CAUSAL_TERMINAL.json", result)


if __name__ == "__main__":
    main()
