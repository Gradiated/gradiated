#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    control = json.loads(args.control.read_text())
    candidate = json.loads(args.candidate.read_text())
    accounting = (
        control["complete_requests"] == candidate["complete_requests"] == 32
        and control["cache"] == candidate["cache"]
        and all(
            control_row["prompt_tokens"] == candidate_row["prompt_tokens"] == 4214
            and control_row["completion_tokens"]
            == candidate_row["completion_tokens"]
            == 358
            and control_row["returned_token_ids"]
            == candidate_row["returned_token_ids"]
            == 358
            for control_row, candidate_row in zip(
                control["rows"], candidate["rows"], strict=True
            )
        )
    )
    control_seconds = float(control["service_seconds_per_request"])
    candidate_seconds = float(candidate["service_seconds_per_request"])
    improvement = (control_seconds - candidate_seconds) / control_seconds
    passed = (
        bool(control["pass"])
        and bool(candidate["pass"])
        and accounting
        and candidate_seconds < control_seconds
    )
    atomic_json(
        args.output,
        {
            "schema_version": 1,
            "status": "terminal",
            "classification": (
                "endpoint_positive" if passed else "endpoint_regression_or_accounting_reject"
            ),
            "pass": passed,
            "control_seconds_per_request": control_seconds,
            "candidate_seconds_per_request": candidate_seconds,
            "relative_improvement": improvement,
            "exact_accounting_pass": accounting,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
