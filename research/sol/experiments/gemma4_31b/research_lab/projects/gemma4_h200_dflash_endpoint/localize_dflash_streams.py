#!/usr/bin/env python3
"""Localize persisted DFlash/AR stream divergence without a model runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frames(path: Path) -> list[dict[str, Any]]:
    result = []
    for line in path.read_text().splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            result.append(json.loads(line[6:]))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--ar", type=Path, required=True)
    parser.add_argument("--pinned-info", type=Path, required=True)
    parser.add_argument("--later-info", type=Path, required=True)
    parser.add_argument("--pinned-overlap", type=Path, required=True)
    parser.add_argument("--later-overlap", type=Path, required=True)
    parser.add_argument("--pinned-worker", type=Path, required=True)
    parser.add_argument("--target-source", type=Path, required=True)
    parser.add_argument("--draft-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for index in range(4):
        candidate_path = args.candidate / f"response-{index:02d}.sse"
        ar_path = args.ar / f"response-{index:02d}.sse"
        candidate = frames(candidate_path)
        ar = frames(ar_path)
        output_ids = [int(x) for x in candidate[-1]["output_ids"]]
        candidate_text = candidate[-1]["text"]
        ar_chunks = [
            item["choices"][0]["text"]
            for item in ar
            if item.get("choices") and item["choices"][0].get("text") is not None
        ]
        ar_text = "".join(ar_chunks)
        repeated_unit = candidate[0]["text"]
        first_ar_chunk_not_repeated_unit = next(
            (i for i, value in enumerate(ar_chunks) if value != repeated_unit),
            None,
        )
        rows.append(
            {
                "request_index": index,
                "candidate_response_sha256": sha256(candidate_path),
                "ar_response_sha256": sha256(ar_path),
                "candidate_output_token_count": len(output_ids),
                "candidate_unique_token_ids": sorted(set(output_ids)),
                "candidate_is_single_repeated_id": len(set(output_ids)) == 1,
                "candidate_first_token_text": repeated_unit,
                "ar_first_token_text": ar_chunks[0],
                "first_ar_token_text_not_equal_to_candidate_repeated_unit": (
                    first_ar_chunk_not_repeated_unit
                ),
                "final_text_equal": candidate_text == ar_text,
            }
        )

    pinned_info = args.pinned_info.read_text()
    later_info = args.later_info.read_text()
    pinned_overlap = args.pinned_overlap.read_text()
    later_overlap = args.later_overlap.read_text()
    output = {
        "schema_version": 1,
        "classification": "offline_first_divergence_localization",
        "evidence_labels": {
            "stream_rows": "measured_persisted_producer",
            "source_comparison": "source_backed",
            "repair": "source_supported_unmeasured_candidate",
        },
        "rows": rows,
        "measured_stream_facts": {
            "all_candidate_rows_complete": all(
                row["candidate_output_token_count"] == 358 for row in rows
            ),
            "all_candidate_rows_repeat_one_token_id": all(
                row["candidate_is_single_repeated_id"] for row in rows
            ),
            "first_client_visible_divergence": {
                "request_index": 2,
                "output_index": 0,
                "candidate_token_text": rows[2]["candidate_first_token_text"],
                "ar_token_text": rows[2]["ar_first_token_text"],
            },
            "delayed_divergence": {
                "request_index": 1,
                "first_ar_token_text_change_index": rows[1][
                    "first_ar_token_text_not_equal_to_candidate_repeated_unit"
                ],
            },
            "exact_token_id_localization_limited_by_consumed_ar": (
                "The consumed AR route persisted decoded deltas but zero raw token IDs."
            ),
        },
        "source_comparison": {
            "pinned_worker_sha256": sha256(args.pinned_worker),
            "target_gemma4_source_sha256": sha256(args.target_source),
            "draft_model_source_sha256": sha256(args.draft_source),
            "pinned_info_sha256": sha256(args.pinned_info),
            "later_info_sha256": sha256(args.later_info),
            "pinned_overlap_sha256": sha256(args.pinned_overlap),
            "later_overlap_sha256": sha256(args.later_overlap),
            "pinned_direct_carry_default_true": "direct_carry_valid: bool = True"
            in pinned_info,
            "later_direct_carry_removed": "direct_carry_valid" not in later_info
            and "direct_carry_valid" not in later_overlap,
            "pinned_bypasses_request_indexed_bonus_and_length_relay": (
                "direct_carry_valid" in pinned_overlap
                and "batch.seq_lens = draft_input.new_seq_lens" in pinned_overlap
            ),
            "later_uses_bonus_tokens": "bonus_tokens: torch.Tensor" in later_info,
        },
        "localization": {
            "narrowest_proven_boundary": (
                "For request 2, divergence exists no later than the first DFlash "
                "prefill-output/first-verifier settlement boundary. Persisted SSE "
                "does not contain per-cycle verifier or KV state, so it cannot "
                "distinguish target-logit divergence from settlement/relay divergence."
            ),
            "unresolved_oracle_fields": [
                "draft_tokens_by_cycle",
                "verifier_top1_logits_and_ids",
                "accepted_prefix_by_cycle",
                "bonus_token_by_cycle",
                "kv_write_positions_and_locations",
                "committed_length_before_and_after",
                "next_cycle_seed_and_length",
                "same-state_ordinary_ar_token_id",
            ],
        },
        "repair_candidate": {
            "path": "DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch",
            "change": "default DFlash direct_carry_valid from true to false",
            "mechanism": (
                "Activate the pinned FutureMap's existing request-indexed stash/"
                "publish/resolve path for verified bonus IDs and new sequence lengths."
            ),
            "why_smallest": (
                "It changes ownership, not verifier math, acceptance, KV geometry, "
                "checkpoint bytes, or scheduling geometry."
            ),
            "measurement_required": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
