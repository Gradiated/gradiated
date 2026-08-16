#!/usr/bin/env python3
"""Correlated fixed-geometry workload for the GLM observer bracket."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable


BASE_URL = "http://127.0.0.1:30000"
MODEL = "glm-4.7-flash-awq"


class ObserverWorkloadError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def request_id(run_id: str, arm_id: str, index: int) -> str:
    if not run_id or not arm_id or index < 0:
        raise ObserverWorkloadError("invalid correlation identity")
    return f"{run_id}:{arm_id}:{index:03d}"


def build_request(prompt: str, correlation_id: str, base_url: str = BASE_URL) -> urllib.request.Request:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "temperature": 0,
        "max_tokens": 32,
        "ignore_eos": True,
        "seed": 470147,
        "stream": True,
        "stream_options": {"include_usage": True},
        "return_token_ids": True,
    }
    return urllib.request.Request(
        base_url + "/v1/completions",
        data=canonical(payload),
        headers={"Content-Type": "application/json", "X-Request-Id": correlation_id},
        method="POST",
    )


def stream_completion(
    prompt: str,
    correlation_id: str,
    *,
    base_url: str = BASE_URL,
    timeout: int = 300,
) -> dict:
    arm_parts = correlation_id.split(":")
    if len(arm_parts) < 3:
        raise ObserverWorkloadError("request ID lacks run and arm correlation")
    arrival_ns = time.monotonic_ns()
    first_token_ns = None
    end_ns = None
    token_timestamps_ns: list[int] = []
    usage = None
    finish_reason = None
    digest = hashlib.sha256()
    with urllib.request.urlopen(build_request(prompt, correlation_id, base_url), timeout=timeout) as response:
        for raw in response:
            digest.update(raw)
            line = raw.strip()
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                end_ns = time.monotonic_ns()
                break
            value = json.loads(data)
            if isinstance(value.get("usage"), dict):
                usage = value["usage"]
            choices = value.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            now_ns = time.monotonic_ns()
            token_ids = choice.get("token_ids") or []
            text = choice.get("text") or ""
            emitted = len(token_ids) if token_ids else int(bool(text))
            if emitted:
                first_token_ns = first_token_ns or now_ns
                token_timestamps_ns.extend([now_ns] * emitted)
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]
    if first_token_ns is None or end_ns is None or not isinstance(usage, dict):
        raise ObserverWorkloadError("stream lacks timing or usage evidence")
    return {
        "run_id": arm_parts[0],
        "arm_id": arm_parts[1],
        "request_id": correlation_id,
        "status": "success",
        "input_tokens": int(usage["prompt_tokens"]),
        "output_tokens": int(usage["completion_tokens"]),
        "finish_reason": finish_reason,
        "arrival_ns": arrival_ns,
        "first_token_ns": first_token_ns,
        "end_ns": end_ns,
        "token_timestamps_ns": token_timestamps_ns,
        "ttft_ms": (first_token_ns - arrival_ns) / 1_000_000,
        "tpot_ms": (end_ns - first_token_ns) / max(1, int(usage["completion_tokens"]) - 1) / 1_000_000,
        "end_to_end_ms": (end_ns - arrival_ns) / 1_000_000,
        "stream_sha256": digest.hexdigest(),
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ObserverWorkloadError("percentile requires measurements")
    return ordered[max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))]


def validate_rows(rows: list[dict], *, requests: int) -> None:
    exact = (
        len(rows) == requests
        and len({row.get("request_id") for row in rows}) == requests
        and all(
            row.get("status") == "success"
            and row.get("input_tokens") == 8192
            and row.get("output_tokens") == 32
            and row.get("finish_reason") == "length"
            and len(row.get("token_timestamps_ns", [])) == 32
            for row in rows
        )
    )
    if not exact:
        raise ObserverWorkloadError("fixed observer geometry or token evidence failed")


def run_arm(
    prompt: str,
    run_id: str,
    arm_id: str,
    *,
    completion: Callable[[str, str], dict] = stream_completion,
    concurrency: int = 8,
    requests: int = 8,
) -> dict:
    if concurrency != 8 or requests != 8:
        raise ObserverWorkloadError("observer arm must use eight synchronized requests")
    barrier = threading.Barrier(concurrency)

    def synchronized(index: int) -> dict:
        barrier.wait(timeout=30)
        return completion(prompt, request_id(run_id, arm_id, index))

    started_ns = time.monotonic_ns()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = [future.result() for future in concurrent.futures.as_completed(
            [pool.submit(synchronized, index) for index in range(requests)]
        )]
    ended_ns = time.monotonic_ns()
    rows.sort(key=lambda row: row["request_id"])
    validate_rows(rows, requests=requests)
    total_output_tokens = sum(row["output_tokens"] for row in rows)
    wall_seconds = (ended_ns - started_ns) / 1_000_000_000
    return {
        "schema_version": 1,
        "run_id": run_id,
        "arm_id": arm_id,
        "geometry_pass": True,
        "concurrency": concurrency,
        "requests": requests,
        "wall_seconds": wall_seconds,
        "total_output_tokens": total_output_tokens,
        "output_tokens_per_second": total_output_tokens / wall_seconds,
        "ttft_ms": {"p50": percentile([row["ttft_ms"] for row in rows], 0.5), "p95": percentile([row["ttft_ms"] for row in rows], 0.95)},
        "tpot_ms": {"p50": percentile([row["tpot_ms"] for row in rows], 0.5), "p95": percentile([row["tpot_ms"] for row in rows], 0.95)},
        "end_to_end_ms": {"p50": percentile([row["end_to_end_ms"] for row in rows], 0.5), "p95": percentile([row["end_to_end_ms"] for row in rows], 0.95)},
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--arm-id", choices=("A1", "B1", "A2", "B2", "A3"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_arm(args.prompt_file.read_text(), args.run_id, args.arm_id)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
