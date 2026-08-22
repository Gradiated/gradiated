#!/usr/bin/env python3
"""Capture the admitted endpoint-pair evidence in one source read per file.

This intentionally does not replay the endpoint or inspect any request other
than index 10.  The resulting capture is an offline derivative that can be
audited without reopening the immutable source files.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_sha256(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    )


def read_inputs_once(paths: dict[str, Path]) -> dict[str, bytes]:
    seen: set[Path] = set()
    result: dict[str, bytes] = {}
    for label, path in paths.items():
        resolved = path.resolve()
        if resolved in seen:
            raise ValueError(f"duplicate source path: {resolved}")
        seen.add(resolved)
        with resolved.open("rb") as source:
            result[label] = source.read()
    return result


def walk(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    leaves: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            leaves.extend(walk(child, path + (str(key),)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            leaves.extend(walk(child, path + (str(index),)))
    else:
        leaves.append((path, value))
    return leaves


def integer_sequences(value: Any, path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Find explicit token-ID vectors without guessing from arbitrary integers."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (str(key),)
            key_lower = str(key).lower()
            if "token" in key_lower and "id" in key_lower:
                if isinstance(child, list) and all(
                    isinstance(item, int) and not isinstance(item, bool) for item in child
                ):
                    found.append({"path": ".".join(child_path), "values": child})
                elif isinstance(child, int) and not isinstance(child, bool):
                    found.append({"path": ".".join(child_path), "values": [child]})
            found.extend(integer_sequences(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(integer_sequences(child, path + (str(index),)))
    return found


def logprob_token_sequences(value: Any, path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Extract SGLang-style [logprob, token_id, token_text] token rows."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (str(key),)
            key_lower = str(key).lower()
            if "token_logprob" in key_lower and isinstance(child, list):
                token_ids: list[int] = []
                valid = bool(child)
                for row in child:
                    if (
                        not isinstance(row, list)
                        or len(row) < 2
                        or not isinstance(row[1], int)
                        or isinstance(row[1], bool)
                    ):
                        valid = False
                        break
                    token_ids.append(row[1])
                if valid:
                    found.append({"path": ".".join(child_path), "values": token_ids})
            found.extend(logprob_token_sequences(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(logprob_token_sequences(child, path + (str(index),)))
    return found


def parse_sse(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8")
    events: list[Any] = []
    done_events = 0
    non_data_lines: list[str] = []
    for line in text.splitlines():
        if not line:
            continue
        if not line.startswith("data:"):
            non_data_lines.append(line[:200])
            continue
        payload = line[5:].lstrip()
        if payload == "[DONE]":
            done_events += 1
            continue
        events.append(json.loads(payload))

    explicit: list[dict[str, Any]] = []
    logprob: list[dict[str, Any]] = []
    key_paths: set[str] = set()
    event_summaries: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        leaves = walk(event)
        key_paths.update(".".join(path) for path, _ in leaves)
        event_explicit = integer_sequences(event)
        event_logprob = logprob_token_sequences(event)
        for row in event_explicit:
            explicit.append({"event_index": index, **row})
        for row in event_logprob:
            logprob.append({"event_index": index, **row})
        event_summaries.append(
            {
                "event_index": index,
                "canonical_json_sha256": json_sha256(event),
                "explicit_token_vector_lengths": [
                    {"path": row["path"], "length": len(row["values"])}
                    for row in event_explicit
                ],
                "logprob_token_vector_lengths": [
                    {"path": row["path"], "length": len(row["values"])}
                    for row in event_logprob
                ],
            }
        )

    return {
        "event_count": len(events),
        "done_event_count": done_events,
        "non_data_lines": non_data_lines,
        "leaf_key_paths": sorted(key_paths),
        "event_summaries": event_summaries,
        "explicit_token_sequences": explicit,
        "logprob_token_sequences": logprob,
    }


def runner_summary(data: bytes) -> dict[str, Any]:
    source = data.decode("utf-8")
    tree = ast.parse(source)
    functions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    relevant_lines = []
    needles = ("token", "sha256", "request", "response", "seed", "temperature", "top_p")
    for number, line in enumerate(source.splitlines(), start=1):
        if any(needle in line.lower() for needle in needles):
            relevant_lines.append({"line": number, "text": line})
    return {
        "ast_parse": "passed",
        "functions": functions,
        "relevant_source_lines": relevant_lines,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-terminal", type=Path, required=True)
    parser.add_argument("--stock-request", type=Path, required=True)
    parser.add_argument("--candidate-request", type=Path, required=True)
    parser.add_argument("--stock-response", type=Path, required=True)
    parser.add_argument("--candidate-response", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--expected-pair-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paths = {
        "pair_terminal": args.pair_terminal,
        "stock_request_10": args.stock_request,
        "candidate_request_10": args.candidate_request,
        "stock_response_10": args.stock_response,
        "candidate_response_10": args.candidate_response,
        "runner": args.runner,
    }
    raw = read_inputs_once(paths)
    observed_pair_sha256 = sha256(raw["pair_terminal"])
    if observed_pair_sha256 != args.expected_pair_sha256:
        raise ValueError(
            "pair terminal digest mismatch: "
            f"expected {args.expected_pair_sha256}, observed {observed_pair_sha256}"
        )
    pair_terminal = json.loads(raw["pair_terminal"])
    stock_request = json.loads(raw["stock_request_10"])
    candidate_request = json.loads(raw["candidate_request_10"])

    capture = {
        "schema_version": 1,
        "classification": "offline_admitted_evidence_capture",
        "source_read_contract": {
            "reads_per_path_in_this_process": 1,
            "gpu_claimed": False,
            "endpoint_replayed": False,
            "admitted_paths": {label: str(path.resolve()) for label, path in paths.items()},
        },
        "source_files": {
            label: {
                "path": str(paths[label].resolve()),
                "bytes": len(data),
                "sha256": sha256(data),
            }
            for label, data in raw.items()
        },
        "pair_terminal": pair_terminal,
        "request_10": {
            "stock_canonical_json_sha256": json_sha256(stock_request),
            "candidate_canonical_json_sha256": json_sha256(candidate_request),
            "raw_bytes_equal": raw["stock_request_10"] == raw["candidate_request_10"],
            "canonical_json_equal": stock_request == candidate_request,
            "stock_payload": stock_request,
            "candidate_payload": candidate_request,
        },
        "stock_response_10": parse_sse(raw["stock_response_10"]),
        "candidate_response_10": parse_sse(raw["candidate_response_10"]),
        "runner": runner_summary(raw["runner"]),
    }

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite one-pass capture: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, args.output)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output.read_bytes())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
