#!/usr/bin/env python3
"""Build the fail-closed endpoint first-divergence terminal from a capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def token_sequence(response: dict[str, Any]) -> list[int]:
    chunks = [
        row
        for row in response["explicit_token_sequences"]
        if row["path"] == "choices.0.token_ids"
    ]
    chunks.sort(key=lambda row: row["event_index"])
    return [token for row in chunks for token in row["values"]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    capture_bytes = args.capture.read_bytes()
    capture = json.loads(capture_bytes)
    pair = capture["pair_terminal"]
    stock_rows = {row["index"]: row for row in pair["stock"]["rows"]}
    candidate_rows = {row["index"]: row for row in pair["candidate"]["rows"]}
    expected_indices = list(range(32))
    if sorted(stock_rows) != expected_indices or sorted(candidate_rows) != expected_indices:
        raise ValueError("pair terminal does not contain the complete 32-row ledger")

    stock_ids = token_sequence(capture["stock_response_10"])
    candidate_ids = token_sequence(capture["candidate_response_10"])
    if len(stock_ids) != 358 or len(candidate_ids) != 358:
        raise ValueError("request 10 does not contain 358 reconstructed token IDs per arm")
    differences = [
        index
        for index, (stock, candidate) in enumerate(zip(stock_ids, candidate_ids))
        if stock != candidate
    ]
    if differences != [20]:
        raise ValueError(f"unexpected token divergence: {differences}")
    if sha256(canonical(stock_ids)) != stock_rows[10]["token_ids_sha256"]:
        raise ValueError("stock request-10 raw response does not reproduce terminal hash")
    if sha256(canonical(candidate_ids)) != candidate_rows[10]["token_ids_sha256"]:
        raise ValueError("candidate request-10 raw response does not reproduce terminal hash")

    row_ledger = []
    for index in expected_indices:
        stock = stock_rows[index]
        candidate = candidate_rows[index]
        row_ledger.append(
            {
                "index": index,
                "request_sha256": stock["request_sha256"],
                "request_sha256_equal": (
                    stock["request_sha256"] == candidate["request_sha256"]
                ),
                "stock_token_ids_sha256": stock["token_ids_sha256"],
                "candidate_token_ids_sha256": candidate["token_ids_sha256"],
                "token_ids_sha256_equal": (
                    stock["token_ids_sha256"] == candidate["token_ids_sha256"]
                ),
            }
        )

    request = capture["request_10"]["stock_payload"]
    source_files = capture["source_files"]
    terminal = {
        "schema_version": 1,
        "classification": "endpoint_promotion_rejected_first_divergence_localized",
        "evidence_scope": {
            "mode": "retrieved_evidence_only",
            "gpu_claimed": False,
            "endpoint_pair_replayed": False,
            "pair_consumed_once": True,
            "provider_cleanup_verified": True,
            "paid_claim_authority_remaining": False,
            "one_pass_capture": {
                "path": str(args.capture),
                "sha256": sha256(capture_bytes),
                "source_reads_per_path": capture["source_read_contract"][
                    "reads_per_path_in_this_process"
                ],
            },
        },
        "source_files": source_files,
        "bound_candidate_source": {
            "path": "m32_static_persistent_geometric_rebind_extension.cu",
            "sha256": "1d1f5aba004d9e33e14a0c548eca2ea8c0e5f326fc60b1dac2334e482b30e425",
            "evidence_label": "inherited_hash_binding_not_reopened_in_this_action",
        },
        "measured": {
            "pair_terminal_sha256_verified": (
                source_files["pair_terminal"]["sha256"]
                == "afe8b5475879dd5af822a557da86dfd224bc339aa014f7579f3a77137c60ba42"
            ),
            "complete_requests": {
                "stock": pair["stock"]["complete_requests"],
                "candidate": pair["candidate"]["complete_requests"],
            },
            "service_seconds_per_request": {
                "stock": pair["stock"]["service_seconds_per_request"],
                "candidate": pair["candidate"]["service_seconds_per_request"],
                "candidate_reduction_fraction": (
                    1
                    - pair["candidate"]["service_seconds_per_request"]
                    / pair["stock"]["service_seconds_per_request"]
                ),
                "candidate_slowdown_fraction": (
                    pair["candidate"]["service_seconds_per_request"]
                    / pair["stock"]["service_seconds_per_request"]
                    - 1
                ),
            },
            "request_identity": {
                "all_32_arm_request_hashes_equal": all(
                    row["request_sha256_equal"] for row in row_ledger
                ),
                "matching_row_count": sum(
                    row["request_sha256_equal"] for row in row_ledger
                ),
                "mismatching_indices": [
                    row["index"]
                    for row in row_ledger
                    if not row["request_sha256_equal"]
                ],
                "request_10_raw_bytes_equal": capture["request_10"][
                    "raw_bytes_equal"
                ],
                "request_10_sha256": source_files["stock_request_10"]["sha256"],
                "request_10_candidate_sha256": source_files["candidate_request_10"][
                    "sha256"
                ],
                "request_10_sampling_contract": {
                    "model": request["model"],
                    "max_tokens": request["max_tokens"],
                    "min_tokens": request["min_tokens"],
                    "ignore_eos": request["ignore_eos"],
                    "temperature": request["temperature"],
                    "seed": request["seed"],
                    "stream": request["stream"],
                    "return_token_ids": request["return_token_ids"],
                    "add_special_tokens": request["add_special_tokens"],
                },
            },
            "token_hash_ledger": {
                "matching_row_count": sum(
                    row["token_ids_sha256_equal"] for row in row_ledger
                ),
                "matching_indices": [
                    row["index"] for row in row_ledger if row["token_ids_sha256_equal"]
                ],
                "mismatching_indices": [
                    row["index"]
                    for row in row_ledger
                    if not row["token_ids_sha256_equal"]
                ],
                "rows": row_ledger,
            },
            "request_10_raw_response_reconstruction": {
                "stock_sse_event_count": capture["stock_response_10"]["event_count"],
                "candidate_sse_event_count": capture["candidate_response_10"][
                    "event_count"
                ],
                "stock_token_count": len(stock_ids),
                "candidate_token_count": len(candidate_ids),
                "stock_reconstructed_token_ids_sha256": sha256(canonical(stock_ids)),
                "candidate_reconstructed_token_ids_sha256": sha256(
                    canonical(candidate_ids)
                ),
                "reconstructed_hashes_match_pair_terminal": True,
                "divergent_token_count": len(differences),
                "divergent_zero_based_indices": differences,
                "first_divergence": {
                    "zero_based_completion_index": 20,
                    "one_based_completion_position": 21,
                    "absolute_sequence_position_after_prompt_zero_based": 4214 + 20,
                    "equal_prefix_token_count": 20,
                    "stock_token_id": stock_ids[20],
                    "candidate_token_id": candidate_ids[20],
                    "equal_suffix_token_count": 358 - 21,
                    "suffix_identical": stock_ids[21:] == candidate_ids[21:],
                    "stock_context_token_ids_15_through_25": stock_ids[15:26],
                    "candidate_context_token_ids_15_through_25": candidate_ids[15:26],
                },
            },
        },
        "derived": {
            "terminal_hash_or_parser_artifact": {
                "verdict": "ruled_out_for_the_observed_difference",
                "basis": "Independent offline concatenation of raw SSE choices[0].token_ids reproduces each arm's terminal SHA-256 exactly.",
            },
            "ordinary_stochastic_sampling": {
                "verdict": "not_enabled_by_the_immutable_request",
                "basis": "The arm-identical request uses temperature=0 and the same fixed per-index seed.",
            },
            "scope_of_semantic_difference": {
                "verdict": "one_token_substitution_only",
                "basis": "The first 20 and final 337 token IDs are arm-identical; only completion position 21 differs.",
            },
        },
        "inferred": {
            "scheduler_semantic_corruption": {
                "causal_status": "not_proven_but_not_exonerated",
                "reason": "The candidate intervention is the arm difference and a deterministic request diverged, but the retrieved evidence has no logits, kernel-level trace, or same-arm A/A repetition.",
            },
            "endpoint_numerical_nondeterminism": {
                "causal_status": "cannot_be_excluded",
                "reason": "Temperature-zero removes configured sampling randomness, not possible numerical race or near-tie sensitivity; no A/A evidence was admitted.",
            },
            "comparative_weight": "The 31/32 exact token-hash matches and the isolated one-token substitution argue against broad endpoint nondeterminism, but they are insufficient to prove the scheduler caused the event.",
        },
        "promotion_verdict": {
            "promote": False,
            "classification": "fail_closed_semantic_mismatch_and_latency_regression",
            "reasons": [
                "The semantics-preserving acceptance contract failed at request index 10.",
                "The candidate was slower by 0.05529037516858182%.",
                "Retrieved evidence does not provide a scope-matched offline explanation that proves the scheduler was non-causal.",
            ],
            "pair_replay_allowed": False,
            "additional_gpu_work_authorized": False,
            "next_action": "Archive the candidate as an endpoint negative; any future reopening requires new authority and independent A/A plus first-divergence logits or scheduler-path telemetry.",
        },
    }

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite terminal: {args.output}")
    temporary = args.output.with_name(f".{args.output.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, args.output)
    digest = sha256(args.output.read_bytes())
    print(json.dumps({"output": str(args.output), "sha256": digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
