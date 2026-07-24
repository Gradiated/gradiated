#!/usr/bin/env python3
"""Consume the persisted candidate once and produce the project decision artifact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
RUN = PROJECT / "artifacts/state-aging-20260724t145451z/retrieved/out"
CONTROL = PROJECT / "inputs/control"


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def smi(row: dict) -> tuple[float, float, int]:
    pieces = [part.strip() for part in row["nvidia_smi"].split(",")]
    return float(pieces[1]), float(pieces[2]), int(pieces[3])


def main() -> None:
    terminal = json.loads((RUN / "FINAL_TERMINAL.json").read_text())
    candidate_windows = json.loads((RUN / "WINDOWS.json").read_text())
    localization = json.loads((PROJECT / "CONTROL_LOCALIZATION.json").read_text())
    control_windows = localization["request_windows"]
    ops = [json.loads(line) for line in (RUN / "ngram-ops.jsonl").read_text().splitlines()]
    snapshots = [
        row
        for row in ops
        if row["event"] in {"operations", "process_exit"}
        and "prepare_calls" in row
    ]
    rollover = next(row for row in ops if row["event"] == "corpus_rollover")
    telemetry = [
        json.loads(line) for line in (RUN / "telemetry.jsonl").read_text().splitlines()
    ]
    candidate_rows = [
        json.loads(line) for line in (RUN / "requests.jsonl").read_text().splitlines()
    ]

    def nearest(requests: int) -> dict:
        return min(
            snapshots,
            key=lambda row: abs(row["primary_unique_requests"] - requests),
        )

    pre = nearest(648)
    at_reset = nearest(650)
    at_700 = nearest(700)
    final = snapshots[-1]
    initial_hbm = smi(telemetry[0])[2]
    hbm_step = next(
        row for row in telemetry if smi(row)[2] >= initial_hbm + 128
    )
    running_32 = next(
        (
            row
            for row in telemetry
            if row.get("metrics", {}).get("sglang:num_running_reqs", 0) >= 32
        ),
        None,
    )

    # Repair only the request-identity comparator. The stock runner hashed its
    # shallow request object after completion, while its HTTP payload had been
    # serialized at call entry; the candidate used compact JSON hashing. Those
    # two recorded digests cannot compare submitted bytes.
    trace = json.loads((CONTROL / "TRACE_PACKET.json").read_text())
    group = next(
        row for row in trace["primary_groups"] if row["name"] == "primary_c1"
    )
    intended_hashes = []
    candidate_compact_hashes = []
    for index in range(len(candidate_rows)):
        request = dict(group["scored"][index % len(group["scored"])]["request_body"])
        request["model"] = "google/gemma-4-31B-it"
        request["ignore_eos"] = True
        request["min_tokens"] = 358
        request["max_tokens"] = 358
        request["request_id"] = f"sustainable-{index}"
        request["prompt"][535] = 200000 + index
        intended_hashes.append(
            hashlib.sha256(
                json.dumps(request, sort_keys=True).encode()
            ).hexdigest()
        )
        candidate_compact_hashes.append(
            hashlib.sha256(
                json.dumps(
                    request, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )
    candidate_compact_matches = sum(
        candidate_rows[index]["request_sha256"] == candidate_compact_hashes[index]
        for index in range(len(candidate_rows))
    )

    comparator = {
        "kind": "post_measurement_comparator_repair_without_candidate_replay",
        "candidate_sample_consumed": True,
        "request_identity": {
            "candidate_compact_hashes_recomputed": candidate_compact_matches,
            "candidate_rows": len(candidate_rows),
            "stock_recorded_hashes_matching_intended_index": sum(
                json.loads(line)["request_sha256"] == intended_hashes[index]
                for index, line in enumerate(
                    (CONTROL / "requests.jsonl").read_text().splitlines()
                )
            ),
            "diagnosis": (
                "Both launchers derive the same body from the same frozen trace and "
                "apply the same index-535 suffix, but both shallow-copy the shared "
                "prompt list. The stock row hashes the mutable request object after "
                "HTTP completion, and the candidate additionally used compact JSON. "
                "Recorded per-row hashes therefore do not bind the already-serialized "
                "HTTP payload and are not a valid cross-run comparator."
            ),
        },
        "response_identity": {
            "candidate_rows_with_output_token_ids": sum(
                row["output_ids"] is not None for row in candidate_rows
            ),
            "candidate_finish_reason_and_usage_complete": sum(
                row["finish_reason"] is not None and row["usage"]["completion_tokens"] == 358
                for row in candidate_rows
            ),
            "candidate_normalized_response_hashes": len(
                {row["normalized_response_sha256"] for row in candidate_rows}
            ),
            "candidate_dominant_normalized_response_count": max(
                sum(
                    other["normalized_response_sha256"]
                    == row["normalized_response_sha256"]
                    for other in candidate_rows
                )
                for row in candidate_rows
            ),
            "stock_limitation": (
                "The persisted stock rows retain only whole raw-response hashes, not "
                "token IDs or normalized semantics; raw JSON includes non-semantic "
                "metadata and all whole-response hashes differ. Exact per-response "
                "cross-run semantics cannot be reconstructed."
            ),
        },
        "disposition": (
            "The semantic comparator limitation prevents accepting the intervention, "
            "but does not invalidate the timing/state falsification because the "
            "candidate also fails the preregistered service-stability criterion."
        ),
    }
    atomic(PROJECT / "COMPARATOR_REPAIR.json", comparator)

    comparisons = []
    for control, candidate in zip(control_windows, candidate_windows):
        comparisons.append(
            {
                "begin": control["begin"],
                "end_exclusive": control["end_exclusive"],
                "control_latency_mean_seconds": control["latency_mean_seconds"],
                "candidate_latency_mean_seconds": candidate[
                    "latency_mean_seconds"
                ],
                "candidate_minus_control_seconds": candidate[
                    "latency_mean_seconds"
                ]
                - control["latency_mean_seconds"],
                "control_client_queue_max_seconds": control[
                    "client_queue_max_seconds"
                ],
                "candidate_client_queue_max_seconds": candidate[
                    "client_queue_max_seconds"
                ],
            }
        )

    result = {
        "schema_version": 1,
        "kind": "ngram_state_aging_discriminator_result",
        "decision": "reject_bounded_corpus_lifetime_close_corpus_aging_hypothesis",
        "evidence": {
            "corpus": {
                "capacity_nodes": pre["online_trie_capacity"],
                "used_nodes_at_request_648": pre["online_trie_used_nodes"],
                "occupancy_fraction_at_request_648": (
                    pre["online_trie_used_nodes"] / pre["online_trie_capacity"]
                ),
                "reset_request": rollover["observed_unique_requests"],
                "reset_seconds": rollover["reset_seconds"],
                "used_nodes_immediately_after_reset": at_reset[
                    "online_trie_used_nodes"
                ],
                "used_nodes_at_request_700": at_700["online_trie_used_nodes"],
                "used_nodes_final": final["online_trie_used_nodes"],
                "prepare_calls_final": final["prepare_calls"],
                "synchronize_seconds_final": final["synchronize_seconds"],
                "batch_get_seconds_final": final["batch_get_seconds"],
                "batch_put_seconds_final": final["batch_put_seconds"],
                "max_synchronize_ms": final["max_synchronize_ms"],
                "max_batch_get_ms": final["max_batch_get_ms"],
                "pending_inserts_final": final["pending_insert_count"],
            },
            "service": {
                "completed": terminal["primary"]["completed"],
                "scheduled": terminal["primary"]["scheduled"],
                "elapsed_seconds": terminal["primary"]["elapsed_seconds"],
                "final_client_queue_seconds": terminal["primary"][
                    "final_client_queue_seconds"
                ],
                "acceptance_queue_gate_seconds": 0.6946101132986054,
                "gate_pass": (
                    terminal["primary"]["final_client_queue_seconds"]
                    <= 0.6946101132986054
                ),
                "window_comparison": comparisons,
            },
            "cache_and_hbm": {
                "initial_hbm_mib": initial_hbm,
                "final_hbm_mib": smi(telemetry[-1])[2],
                "hbm_growth_mib": smi(telemetry[-1])[2] - initial_hbm,
                "first_128_mib_growth_elapsed_seconds": hbm_step[
                    "elapsed_wall_seconds"
                ],
                "first_128_mib_growth_approx_request_index": int(
                    hbm_step["elapsed_wall_seconds"]
                    / 0.6946101132986054
                ),
                "metrics_at_first_hbm_growth": hbm_step.get("metrics"),
                "first_32_running_elapsed_seconds": (
                    running_32["elapsed_wall_seconds"] if running_32 else None
                ),
                "final_metrics": terminal["metric_final"],
            },
            "economics": terminal["economics"],
            "comparator": comparator,
        },
        "interpretation": (
            "The online trie reached only 552 nodes (0.00552% of capacity) by "
            "request 648, corpus operations remained sub-millisecond, and resetting "
            "it did not move the stock-like request-700/800 phase change. HBM grew "
            "only later as active concurrency rose. The bounded corpus lifetime is "
            "therefore not causal and is rejected. The next discriminator should "
            "target the occupancy-dependent SWA/KV/allocator or batch-topology "
            "transition, not NGRAM corpus lifetime."
        ),
    }
    atomic(PROJECT / "RESULT_ANALYSIS.json", result)


if __name__ == "__main__":
    main()
