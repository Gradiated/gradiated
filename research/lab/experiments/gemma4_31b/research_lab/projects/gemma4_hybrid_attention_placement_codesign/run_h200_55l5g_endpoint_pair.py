#!/usr/bin/env python3
"""Run the one admitted permanent-55L/5G matched endpoint pair on a claimed H200.

This program runs on the guest.  The outer owner supplies two already-started,
independent OpenAI-compatible endpoints and refuses to send the immutable c32
workload until the candidate endpoint has produced its runtime path proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


MODEL = "google/gemma-4-31B-it"
CONCURRENCY, PROMPT_TOKENS, OUTPUT_TOKENS = 32, 4214, 358
CONVERTED = [11, 23, 35, 47, 59]


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def request(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    body = json.dumps(payload, separators=(",", ":")).encode()
    call = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions", body,
        {"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(call, timeout=timeout) as response:
        return json.loads(response.read()), time.monotonic() - started


def validate_candidate_proof(path: Path, candidate_source_sha256: str) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not (
        value.get("candidate_endpoint_path_executed") is True
        and value.get("converted_layers") == CONVERTED
        and value.get("candidate_source_sha256") == candidate_source_sha256
    ):
        raise RuntimeError("candidate_path_proof_invalid")
    return value


def run_arm(name: str, url: str, workload: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, payload in enumerate(workload):
        item = dict(payload)
        item["model"] = MODEL
        started = time.monotonic()
        try:
            response, wall = request(url, item, timeout)
            choice = (response.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            usage = response.get("usage") or {}
            text = message.get("content", "")
            token_ids = choice.get("token_ids") or []
            rows.append({
                "index": index, "request_sha256": hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest(),
                "response_sha256": hashlib.sha256(json.dumps(response, sort_keys=True).encode()).hexdigest(),
                "wall_seconds": wall, "ttft_seconds": response.get("meta_info", {}).get("ttft"),
                "decode_seconds": response.get("meta_info", {}).get("decode_time"), "usage": usage,
                "finish_reason": choice.get("finish_reason"), "text": text, "token_ids": token_ids,
                "finite_nonempty_text": isinstance(text, str) and bool(text), "error": None,
            })
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as error:
            rows.append({"index": index, "error": repr(error), "wall_seconds": time.monotonic() - started})
            break
    complete = [row for row in rows if row.get("error") is None]
    walls = [float(row["wall_seconds"]) for row in complete]
    return {
        "arm": name, "rows": rows, "complete_requests": len(complete), "failures": len(rows) - len(complete),
        "service_seconds_per_request": sum(walls) / len(walls) if walls else None,
        "wall_p50_seconds": percentile(walls, .5) if walls else None,
        "wall_p95_seconds": percentile(walls, .95) if walls else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--control-url", required=True)
    parser.add_argument("--candidate-url", required=True)
    parser.add_argument("--candidate-proof", type=Path, required=True)
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    args = parser.parse_args()
    workload = json.loads(args.workload.read_text())
    if not isinstance(workload, list) or len(workload) != CONCURRENCY:
        raise RuntimeError("exact_c32_workload_required")
    proof = validate_candidate_proof(args.candidate_proof, digest(args.candidate_source))
    atomic(args.output / "INVOCATION.json", {"science_started": True, "candidate_cuda_invocation_started": False, "workload_sha256": digest(args.workload), "candidate_proof": proof})
    control = run_arm("stock", args.control_url, workload, args.timeout_seconds)
    candidate = run_arm("permanent_55local_5global", args.candidate_url, workload, args.timeout_seconds)
    valid = all(arm["complete_requests"] == CONCURRENCY and arm["failures"] == 0 for arm in (control, candidate))
    terminal = {
        "schema_version": 1, "classification": "scientific_terminal" if valid else "invalid_endpoint_pair",
        "science_consumed": valid, "candidate_cuda_invocation_started": valid,
        "candidate_layers": [5, 17, 29, 41, 53], "converted_layers": CONVERTED,
        "workload": {"concurrency": CONCURRENCY, "prompt_tokens": PROMPT_TOKENS, "output_tokens": OUTPUT_TOKENS, "sha256": digest(args.workload)},
        "candidate_path_proof": proof, "control": control, "candidate": candidate,
        "service_time_delta_seconds_per_request": None if not valid else candidate["service_seconds_per_request"] - control["service_seconds_per_request"],
    }
    atomic(args.output / "HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json", terminal)
    return 0 if valid else 72


if __name__ == "__main__":
    raise SystemExit(main())
