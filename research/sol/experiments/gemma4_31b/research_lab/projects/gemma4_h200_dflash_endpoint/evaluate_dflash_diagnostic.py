#!/usr/bin/env python3
"""Gate the DFlash diagnostic against the consumed AR text and raw telemetry."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import re


VERIFY_RE = re.compile(
    r"DFLASH verify completed\. num_correct_drafts_per_req=(\[[^\n]+\])"
)


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def old_openai_text(path: pathlib.Path) -> str:
    text = ""
    for raw in path.read_bytes().splitlines():
        if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
            continue
        item = json.loads(raw[6:])
        choice = (item.get("choices") or [{}])[0]
        text += choice.get("text") or ""
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--consumed-ar", type=pathlib.Path, required=True)
    parser.add_argument("--server-log", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    terminal = json.loads((args.candidate / "TERMINAL.json").read_text())
    rows = [
        json.loads(path.read_text())
        for path in sorted(args.candidate.glob("request-*.json"))
    ]
    candidate_texts = [
        path.read_text() for path in sorted(args.candidate.glob("response-*.txt"))
    ]
    control_texts = [
        old_openai_text(path)
        for path in sorted(args.consumed_ar.glob("response-*.sse"))
    ]
    log_text = args.server_log.read_text(errors="replace")
    events = []
    for match in VERIFY_RE.finditer(log_text):
        values = ast.literal_eval(match.group(1))
        if not isinstance(values, list) or any(not isinstance(v, int) for v in values):
            raise ValueError("invalid DFlash verification telemetry")
        events.append(values)
    accepted = [value for event in events for value in event]
    result = {
        "schema_version": 1,
        "classification": "diagnostic_pass",
        "complete_requests": terminal.get("complete_requests"),
        "candidate_raw_token_ids_present": len(rows) == 4
        and all(row.get("returned_token_ids") == 358 for row in rows),
        "prior_ar_decoded_text_equal": len(candidate_texts)
        == len(control_texts)
        == 4
        and candidate_texts == control_texts,
        "candidate_text_sha256": [
            hashlib.sha256(value.encode()).hexdigest() for value in candidate_texts
        ],
        "consumed_ar_text_sha256": [
            hashlib.sha256(value.encode()).hexdigest() for value in control_texts
        ],
        "draft_runner_initialized": "Initialized DFLASH draft runner" in log_text,
        "verify_event_count": len(events),
        "request_verification_count": len(accepted),
        "accepted_draft_tokens": sum(accepted),
        "mean_accepted_drafts_per_verification": (
            sum(accepted) / len(accepted) if accepted else None
        ),
        "zero_accept_fraction": (
            sum(value == 0 for value in accepted) / len(accepted)
            if accepted
            else None
        ),
        "terminal_pass": terminal.get("pass") is True,
    }
    passed = (
        result["terminal_pass"]
        and result["complete_requests"] == 4
        and result["candidate_raw_token_ids_present"]
        and result["prior_ar_decoded_text_equal"]
        and result["draft_runner_initialized"]
        and result["verify_event_count"] > 0
        and result["accepted_draft_tokens"] > 0
    )
    result["pass"] = passed
    if not passed:
        result["classification"] = "diagnostic_quality_or_integration_reject"
    atomic(args.output, result)
    return 0 if passed else 72


if __name__ == "__main__":
    raise SystemExit(main())
