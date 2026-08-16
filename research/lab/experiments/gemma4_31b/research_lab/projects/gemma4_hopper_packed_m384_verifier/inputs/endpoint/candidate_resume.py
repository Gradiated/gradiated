#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time

import endpoint_pair
from token_oracle import (
    jsonl as parse_jsonl,
    response_files,
    token_rows,
    validate_oracle,
)


EXPECTED_CACHE = {
    "uncached_prompt_tokens_delta": 117728,
    "cached_prompt_tokens_delta": 17120,
}


def valid_candidate(terminal: dict, rows: list[dict]) -> bool:
    cache = terminal.get("cache", {})
    return bool(
        terminal.get("pass")
        and terminal.get("complete_requests") == 32
        and len(terminal.get("rows", [])) == 32
        and len(rows) == 32
        and all(cache.get(key) == value for key, value in EXPECTED_CACHE.items())
    )


def comparable(row: dict) -> dict:
    return {
        key: row.get(key)
        for key in (
            "emitted_token_ids",
            "completion_counter",
            "prompt_tokens",
            "finish_reason",
            "parser_input_utf8_hex",
        )
    }


def consume(
    root: pathlib.Path,
    oracle: dict,
    candidate: dict,
    input_identity: dict,
) -> dict:
    artifacts = root / "artifacts"
    candidate_rows = token_rows(
        candidate,
        response_files(artifacts / "candidate"),
        parse_jsonl((artifacts / "candidate.token-events.jsonl").read_bytes()),
    )
    control_rows = oracle["rows"]
    request_hashes_exact = [
        row["request_sha256"] for row in control_rows
    ] == [row["request_sha256"] for row in candidate_rows]
    tokens_exact = [
        row["emitted_token_ids"] for row in control_rows
    ] == [row["emitted_token_ids"] for row in candidate_rows]
    trace_exact = [comparable(row) for row in control_rows] == [
        comparable(row) for row in candidate_rows
    ]

    routes = endpoint_pair.jsonl(artifacts / "candidate.route.jsonl")
    candidate_calls = [row for row in routes if row.get("route") == "candidate"]
    rejected = [
        row for row in routes if row.get("route") == "rejected_no_fallback"
    ]
    local_calls = sum(bool(row.get("local")) for row in candidate_calls)
    global_calls = sum(bool(row.get("global")) for row in candidate_calls)
    dispatch = endpoint_pair.jsonl(artifacts / "candidate.candidate.jsonl")
    local_dispatch = sum(row.get("kind") == "local_d256" for row in dispatch)
    global_dispatch = sum(row.get("kind") == "global_d512" for row in dispatch)
    routing_exact = bool(
        not rejected
        and local_calls > 0
        and global_calls > 0
        and local_calls == local_dispatch
        and global_calls == global_dispatch
        and local_calls == 5 * global_calls
        and local_calls % 50 == 0
        and global_calls % 10 == 0
    )
    candidate_valid = valid_candidate(candidate, candidate_rows)
    gates = {
        "candidate_no_fallback_and_exact_50_10_routing": routing_exact,
        "cache_accounting_exact": candidate_valid,
        "complete_finite_nonempty_rows": candidate_valid,
        "exact_request_hashes": request_hashes_exact,
        "exact_persisted_control_target_tokens": tokens_exact,
        "exact_target_to_emitted_trace": trace_exact,
    }
    valid = all(gates.values())
    control = oracle["control_terminal"]
    candidate_patched = json.loads(json.dumps(candidate))
    for row in candidate_patched["rows"]:
        row["returned_token_ids"] = 358
    control_seconds = control["service_seconds_per_request"]
    candidate_seconds = candidate["service_seconds_per_request"]
    reduction = 1.0 - candidate_seconds / control_seconds
    classification = (
        "semantic_or_path_reject"
        if not valid
        else "endpoint_positive"
        if reduction > 0
        else "endpoint_nonpositive"
    )
    return {
        "schema_version": 1,
        "type": "packed_m384_matched_c32_endpoint_terminal",
        "classification": classification,
        "pass": valid,
        "gates": gates,
        "identity": input_identity,
        "control": control,
        "candidate": candidate_patched,
        "control_source": {
            "kind": "persisted_offline_reconstructed_oracle",
            "oracle_sha256": hashlib.sha256(
                (root / "input" / "CONTROL_TOKEN_ORACLE.json").read_bytes()
            ).hexdigest(),
            "request_replayed": False,
        },
        "control_service_seconds_per_request": control_seconds,
        "candidate_service_seconds_per_request": candidate_seconds,
        "service_reduction_fraction": reduction,
        "complete_request_throughput": {
            "control": control.get("complete_request_throughput"),
            "candidate": candidate.get("complete_request_throughput"),
        },
        "routing": {
            "candidate_local_calls": local_calls,
            "candidate_global_calls": global_calls,
            "dispatch_local_calls": local_dispatch,
            "dispatch_global_calls": global_dispatch,
            "rejected_target_calls": len(rejected),
        },
        "candidate_server": {
            "container": endpoint_pair.CANDIDATE_CONTAINER,
            "port": 30000,
            "retained": True,
            "release_condition": (
                "maintenance_unless_director_names_compatible_successor"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--oracle", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    identity = endpoint_pair.verify_inputs(root, args.manifest.resolve())
    oracle = json.loads(args.oracle.resolve().read_text())
    validate_oracle(oracle)
    endpoint_pair.atomic(
        artifacts / "INVOCATION_STATE.json",
        {
            "candidate_graph_capture_passed": False,
            "candidate_science_started": False,
            "control_request_replayed": False,
            "identity_validated": True,
            "oracle_validated": True,
        },
    )
    endpoint_pair.start_server(
        root,
        "candidate",
        endpoint_pair.CANDIDATE_CONTAINER,
        args.absolute_deadline_epoch,
    )
    state_path = artifacts / "INVOCATION_STATE.json"
    state = json.loads(state_path.read_text())
    state["candidate_graph_capture_passed"] = True
    state["graph_capture_passed_at_epoch"] = time.time()
    endpoint_pair.atomic(state_path, state)
    candidate = endpoint_pair.run_arm(
        root,
        "candidate",
        endpoint_pair.CANDIDATE_CONTAINER,
        args.absolute_deadline_epoch,
    )
    terminal = consume(root, oracle, candidate, identity)
    endpoint_pair.atomic(artifacts / "ENDPOINT_TERMINAL.json", terminal)
    endpoint_pair.atomic(
        artifacts / "RESIDENT_SERVER.json", terminal["candidate_server"]
    )
    return 0 if terminal["pass"] else 74


if __name__ == "__main__":
    raise SystemExit(main())
