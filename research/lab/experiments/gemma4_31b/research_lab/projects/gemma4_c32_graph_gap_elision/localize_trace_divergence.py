#!/usr/bin/env python3
"""Reconcile the consumed c32 pair from immutable raw files only."""

from __future__ import annotations

import collections
import hashlib
import json
import os
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
ARTIFACT = PROJECT / "artifacts/c32-graph-gap-20260726t042557z"
RAW = ARTIFACT / "raw/pair"
OUTPUT = PROJECT / "TRACE_DIVERGENCE_LOCALIZATION.json"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def response(arm: str, index: int) -> dict:
    path = RAW / f"{arm}-c32/response-{index:02d}.sse"
    rows = []
    for line in path.read_text().splitlines():
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        rows.append(json.loads(line[6:]))
    rids = {row["id"] for row in rows}
    if len(rids) != 1:
        raise RuntimeError(f"{arm}:{index}:response_rid_cardinality:{len(rids)}")
    choices = [(row.get("choices") or [{}])[0] for row in rows]
    return {
        "path": path,
        "rid": next(iter(rids)),
        "text": "".join(choice.get("text") or "" for choice in choices),
        "finish_reason": next(
            (
                choice["finish_reason"]
                for choice in reversed(choices)
                if choice.get("finish_reason") is not None
            ),
            None,
        ),
        "usage": next(
            (row["usage"] for row in reversed(rows) if row.get("usage") is not None),
            None,
        ),
    }


def trace(arm: str) -> dict[str, dict]:
    path = RAW / f"{arm}-token-events.jsonl"
    grouped: dict[str, dict] = collections.defaultdict(
        lambda: {"scheduler": [], "final": []}
    )
    for line in path.read_text().splitlines():
        row = json.loads(line)
        key = "scheduler" if row["stage"] == "scheduler_to_detokenizer" else "final"
        grouped[row["rid"]][key].append(row)
    return grouped


def reconstruct(events: dict) -> dict:
    scheduler = events["scheduler"]
    final = events["final"]
    ids: list[int] = []
    counter_invariant = True
    for row in scheduler:
        ids.extend(row["scheduler_output_ids_delta"])
        counter_invariant &= row["completion_counter"] == len(ids)
    return {
        "token_ids": ids,
        "counter_invariant": counter_invariant,
        "scheduler_events": scheduler,
        "final_events": final,
        "final_counter": scheduler[-1]["completion_counter"] if scheduler else None,
        "final_delta_matches": bool(
            scheduler
            and final
            and scheduler[-1]["scheduler_output_ids_delta"]
            == final[-1]["emitted_token_ids"]
        ),
    }


def iteration_for_position(events: list[dict], position: int) -> dict:
    start = 0
    for iteration, row in enumerate(events):
        width = len(row["scheduler_output_ids_delta"])
        if start <= position < start + width:
            return {
                "scheduler_event_ordinal": iteration,
                "event_start_token_position": start,
                "event_width": width,
                "accepted_drafts_proxy": max(0, width - 1),
                "completion_counter": row["completion_counter"],
                "at_monotonic": row["at_monotonic"],
            }
        start += width
    raise RuntimeError(f"token_position_not_found:{position}")


def main() -> int:
    traces = {arm: trace(arm) for arm in ("control", "candidate")}
    arms: dict[str, list[dict]] = {}
    for arm in ("control", "candidate"):
        arm_rows = []
        for index in range(32):
            api = response(arm, index)
            if api["rid"] not in traces[arm]:
                raise RuntimeError(f"{arm}:{index}:response_trace_join_missing")
            rebuilt = reconstruct(traces[arm][api["rid"]])
            request = read_json(RAW / f"{arm}-c32/request-{index:02d}.json")
            arm_rows.append(
                {
                    "index": index,
                    "rid": api["rid"],
                    "request_sha256": request["request_sha256"],
                    "text": api["text"],
                    "finish_reason": api["finish_reason"],
                    "usage": api["usage"],
                    **rebuilt,
                }
            )
        arms[arm] = arm_rows

    mismatches = []
    for control, candidate in zip(arms["control"], arms["candidate"]):
        if control["request_sha256"] != candidate["request_sha256"]:
            raise RuntimeError(f"request_hash_mismatch:{control['index']}")
        left, right = control["token_ids"], candidate["token_ids"]
        position = next(
            (i for i, pair in enumerate(zip(left, right)) if pair[0] != pair[1]),
            min(len(left), len(right)) if left != right else None,
        )
        if position is not None or control["text"] != candidate["text"]:
            mismatches.append(
                {
                    "request_index": control["index"],
                    "request_sha256": control["request_sha256"],
                    "control_rid": control["rid"],
                    "candidate_rid": candidate["rid"],
                    "first_token_position": position,
                    "control_token_id": (
                        control["token_ids"][position]
                        if position is not None and position < len(left)
                        else None
                    ),
                    "candidate_token_id": (
                        candidate["token_ids"][position]
                        if position is not None and position < len(right)
                        else None
                    ),
                    "control_iteration": iteration_for_position(
                        control["scheduler_events"], position
                    ),
                    "candidate_iteration": iteration_for_position(
                        candidate["scheduler_events"], position
                    ),
                    "streamed_text_exact": control["text"] == candidate["text"],
                    "control_text_prefix": control["text"][:96],
                    "candidate_text_prefix": candidate["text"][:96],
                }
            )

    first = min(mismatches, key=lambda row: (row["first_token_position"], row["request_index"]))
    per_arm = {}
    for arm, rows in arms.items():
        per_arm[arm] = {
            "response_rids_unique": len({row["rid"] for row in rows}) == 32,
            "response_to_trace_join_complete": len(rows) == 32,
            "counter_invariant_all_rows": all(
                row["counter_invariant"] for row in rows
            ),
            "final_counter_358_all_rows": all(
                row["final_counter"] == 358 for row in rows
            ),
            "final_delta_matches_all_rows": all(
                row["final_delta_matches"] for row in rows
            ),
            "token_rows": len(rows),
            "token_ids_per_row": sorted({len(row["token_ids"]) for row in rows}),
        }

    inputs = {}
    for relative in (
        "C32_GRAPH_GAP_ELISION_TERMINAL.json",
        "endpoint_pair.py",
        "token_trace_hook.py",
        "ngram_worker.py",
        "inputs/source/ngram_worker.stock.py",
        "inputs/source/ngram_info.py",
        "inputs/source/batch_result_processor.py",
        "artifacts/c32-graph-gap-20260726t042557z/raw/pair/PAIR_TERMINAL.json",
        "artifacts/c32-graph-gap-20260726t042557z/raw/pair/control-token-events.jsonl",
        "artifacts/c32-graph-gap-20260726t042557z/raw/pair/candidate-token-events.jsonl",
        "artifacts/c32-graph-gap-20260726t042557z/raw/pair/control-c32/response-00.sse",
        "artifacts/c32-graph-gap-20260726t042557z/raw/pair/candidate-c32/response-00.sse",
    ):
        path = PROJECT / relative
        inputs[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}

    result = {
        "schema_version": 1,
        "classification": "director_zero_gpu_trace_divergence_localization",
        "result": "semantic_divergence_reject",
        "science_consumed": True,
        "gpu_claimed": False,
        "endpoint_requests_submitted": 0,
        "provider_spend_usd": 0.0,
        "measured_timing_preserved": {
            "control_service_seconds_per_request": 0.6183353098438147,
            "candidate_service_seconds_per_request": 0.6135780843437715,
            "service_time_delta_fraction": -0.007693601552925755,
            "performance_claimed": False,
        },
        "observer_reconciliation": {
            "per_arm": per_arm,
            "sse_token_ids_exact_field": {
                "reported": True,
                "decision_bearing": False,
                "reason": "return_token_ids produced zero IDs for all rows; empty-list equality was vacuous.",
            },
            "consumer_join": (
                "response-XX.sse id joins one-to-one to trace rid; scheduler deltas "
                "are ordered by file order and every completion counter equals their "
                "cumulative length. The existing cumulative consumer is internally valid."
            ),
            "streamed_text_mismatch_request_indices": [
                row["request_index"] for row in mismatches if not row["streamed_text_exact"]
            ],
            "streamed_text_mismatch_count": sum(
                not row["streamed_text_exact"] for row in mismatches
            ),
        },
        "first_divergence": {
            **first,
            "selection": "minimum emitted token position, then request index",
            "phase": "initial prefill bonus-token emission before the first NGRAM TARGET_VERIFY call",
            "target_verify_padding": "not_applicable",
            "target_verify_row": "not_applicable",
            "row_ownership": (
                "request file index 0 -> SSE id/rid -> scheduler trace rid; the "
                "request SHA-256 is exact across arms"
            ),
        },
        "causal_localization": {
            "candidate_boundary": (
                "NgramVerifyInput.verify updates batch.seq_lens_cpu only after "
                "TARGET_VERIFY; NGRAMWorker.forward_batch_generation then derives "
                "num_correct_drafts_per_req_cpu."
            ),
            "semantic_reachability": (
                "The candidate count is computed after accepted tokens are fixed. "
                "For Gemma it feeds per-request speculative statistics; the only "
                "generic stateful downstream branch found is Mamba interval tracking, "
                "which is not this model."
            ),
            "first_divergence_precedes_intervention": True,
            "conclusion": (
                "The pair contains a real API-visible semantic mismatch, not an "
                "observer join defect, but its position-zero pre-intervention onset "
                "prevents attributing it to cpu_seq_len_delta_accept_count. The exact "
                "quality gate still fails, so the timing movement cannot be promoted."
            ),
        },
        "mismatch_request_count": len(mismatches),
        "all_mismatches": mismatches,
        "inputs": inputs,
        "constructor": {
            "path": "localize_trace_divergence.py",
            "sha256": sha256(PROJECT / "localize_trace_divergence.py"),
        },
        "future_capture_if_reopened": (
            "Smallest missing discriminator: a separately authorized stock/stock "
            "A/A c32 pair with fixed server random_seed plus nonempty API token IDs "
            "and a per-TARGET_VERIFY record of active batch size, padded graph batch "
            "size, request row, accepted-prefix length, and the post-verify count "
            "mirror. No such replay is authorized here."
        ),
    }
    atomic(OUTPUT, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
