from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


CEILING_SECONDS_PER_REQUEST = 0.6381105231


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()

    artifact = args.project / "artifacts/mtp-candidate-repair-20260723t0658z/retrieved"
    terminal = json.loads((artifact / "mtp/TERMINAL.json").read_text())
    events = [
        json.loads(line)
        for line in (artifact / "mtp-audit/accepted-depth.jsonl")
        .read_text()
        .splitlines()
    ]
    assistant = [row for row in events if row.get("event") == "assistant_forward"]
    verify = [row for row in events if row.get("event") == "target_verify"]

    verify_calls = sum(int(row["batch_size"]) for row in verify)
    accepted_drafts = sum(int(row["accepted_drafts_total"]) for row in verify)
    completion_tokens = sum(int(row["completion_tokens"]) for row in terminal["rows"])
    complete_requests = int(terminal["complete_requests"])
    first_tokens = complete_requests
    target_verify_positions = 2 * verify_calls
    stock_decode_positions = completion_tokens - first_tokens

    by_batch_size: dict[int, dict[str, float | int]] = defaultdict(
        lambda: {
            "iterations": 0,
            "request_verifies": 0,
            "accepted_drafts": 0,
            "assistant_ms": 0.0,
            "target_verify_ms": 0.0,
        }
    )
    for row in assistant:
        by_batch_size[int(row["batch_size"])]["assistant_ms"] += float(
            row["elapsed_ms"]
        )
    for row in verify:
        size = int(row["batch_size"])
        group = by_batch_size[size]
        group["iterations"] += 1
        group["request_verifies"] += size
        group["accepted_drafts"] += int(row["accepted_drafts_total"])
        group["target_verify_ms"] += float(row["elapsed_ms"])

    for group in by_batch_size.values():
        request_verifies = int(group["request_verifies"])
        group["accepted_drafts_per_request_verify"] = (
            float(group["accepted_drafts"]) / request_verifies
        )

    assistant_seconds = sum(float(row["elapsed_ms"]) for row in assistant) / 1000
    target_verify_seconds = sum(float(row["elapsed_ms"]) for row in verify) / 1000
    ceiling_batch_seconds = CEILING_SECONDS_PER_REQUEST * complete_requests

    output = {
        "schema_version": 1,
        "complete_requests": complete_requests,
        "completion_tokens": completion_tokens,
        "batch_iterations": len(verify),
        "request_verifies": verify_calls,
        "accepted_drafts": accepted_drafts,
        "token_conservation": {
            "first_tokens": first_tokens,
            "verify_bonus_tokens": verify_calls,
            "accepted_drafts": accepted_drafts,
            "sum": first_tokens + verify_calls + accepted_drafts,
            "expected": completion_tokens,
            "pass": first_tokens + verify_calls + accepted_drafts
            == completion_tokens,
        },
        "target_work_geometry": {
            "mtp_target_verify_positions": target_verify_positions,
            "stock_decode_positions": stock_decode_positions,
            "mtp_over_stock_ratio": target_verify_positions / stock_decode_positions,
        },
        "measured_spans": {
            "assistant_seconds": assistant_seconds,
            "target_verify_seconds": target_verify_seconds,
            "assistant_plus_target_verify_seconds": assistant_seconds
            + target_verify_seconds,
            "candidate_batch_seconds": float(terminal["batch_seconds"]),
        },
        "ceiling": {
            "seconds_per_request": CEILING_SECONDS_PER_REQUEST,
            "batch_seconds": ceiling_batch_seconds,
            "target_verify_only_seconds_per_request": target_verify_seconds
            / complete_requests,
            "target_verify_only_excess_fraction": target_verify_seconds
            / ceiling_batch_seconds
            - 1,
            "assistant_plus_verify_seconds_per_request": (
                assistant_seconds + target_verify_seconds
            )
            / complete_requests,
            "source_bound_overlap_candidate_pass": target_verify_seconds
            <= ceiling_batch_seconds,
        },
        "by_batch_size": {
            str(size): values
            for size, values in sorted(by_batch_size.items(), reverse=True)
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
