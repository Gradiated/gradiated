#!/usr/bin/env python3
"""Execution-equivalent c32 consumer for one OpenAI-compatible vLLM arm.

The owner deliberately runs this once per server generation: the first output
is the all-TRITON control and the second is the 50-TRITON/10-FLEX candidate.
No endpoint result is accepted without all 32 response rows and exact token
accounting.  This module is inert on the coordinator; ``--preflight`` only
checks the immutable workload bytes.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WORKLOAD = ROOT.parent / "gemma4_rtxpro6000_vllm_current_fp8_endpoint" / "inputs" / "c32_requests.jsonl"
WORKLOAD_SHA256 = "357f22f350a8c0f11df5e1a93f1cd19e4b2eb2d329c75ed993f8dda2cf72338c"
WORKLOAD_BYTES = 893666
CONCURRENCY = 32
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")
        tmp = Path(f.name)
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def load_workload(path: Path = WORKLOAD) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size != WORKLOAD_BYTES or digest(path) != WORKLOAD_SHA256:
        raise RuntimeError("authoritative_c32_workload_identity_invalid")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(rows) != CONCURRENCY or any(not isinstance(r.get("payload"), dict) for r in rows):
        raise RuntimeError("authoritative_c32_workload_row_count_invalid")
    for row in rows:
        payload = row["payload"]
        if payload.get("max_tokens") != OUTPUT_TOKENS or payload.get("min_tokens") != OUTPUT_TOKENS:
            raise RuntimeError("authoritative_c32_output_geometry_invalid")
        if len(payload.get("prompt", [])) != PROMPT_TOKENS:
            raise RuntimeError("authoritative_c32_prompt_geometry_invalid")
    return rows


def post(url: str, row: dict[str, Any], timeout: float) -> dict[str, Any]:
    payload = row["payload"]
    raw = json.dumps(payload, separators=(",", ":")).encode()
    started = time.monotonic()
    result: dict[str, Any] = {"request_id": row.get("request_id"), "request_sha256": hashlib.sha256(raw).hexdigest()}
    request = urllib.request.Request(url, data=raw, headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            decoded = json.loads(body)
            usage = decoded.get("usage", {})
            completion = usage.get("completion_tokens")
            prompt = usage.get("prompt_tokens")
            result.update({"status": response.status, "response_sha256": hashlib.sha256(body).hexdigest(),
                           "prompt_tokens": prompt, "completion_tokens": completion,
                           "elapsed_seconds": time.monotonic() - started,
                           "ok": response.status == 200 and prompt == PROMPT_TOKENS and completion == OUTPUT_TOKENS})
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result.update({"status": getattr(exc, "code", None), "error_type": type(exc).__name__,
                       "error": str(exc)[:500], "elapsed_seconds": time.monotonic() - started, "ok": False})
    return result


def run_arm(url: str, output: Path, arm: str, timeout: float) -> dict[str, Any]:
    rows = load_workload()
    output.mkdir(parents=True, exist_ok=False)
    started = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(post, url, row, timeout) for row in rows]
        results = [future.result() for future in futures]
    results.sort(key=lambda r: str(r.get("request_id", "")))
    terminal = {
        "schema_version": 1, "classification": "endpoint_arm_complete" if all(r.get("ok") for r in results) else "endpoint_arm_incomplete",
        "arm": arm, "science_started": True, "science_consumed": bool(results),
        "workload_sha256": WORKLOAD_SHA256, "request_rows": len(results), "successful_rows": sum(bool(r.get("ok")) for r in results),
        "prompt_tokens": PROMPT_TOKENS, "output_tokens": OUTPUT_TOKENS,
        "service_seconds_per_request": (sum(r.get("elapsed_seconds", 0.0) for r in results) / len(results)) if results else None,
        "p95_seconds": sorted((r.get("elapsed_seconds", 0.0) for r in results))[max(0, int(len(results) * .95) - 1)] if results else None,
        "started_at_utc": started, "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "rows": results,
    }
    atomic_json(output / "ARM_TERMINAL.json", terminal)
    atomic_json(output / "REQUEST_MANIFEST.json", {"workload_sha256": WORKLOAD_SHA256, "rows": len(results), "response_sha256": [r.get("response_sha256") for r in results]})
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--arm", choices=("control_all_triton", "candidate_50_triton_10_flex"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()
    rows = load_workload()
    if args.preflight:
        print(json.dumps({"preflight": "pass", "workload_sha256": WORKLOAD_SHA256, "rows": len(rows), "gpu_pool_called": False}, sort_keys=True))
        return 0
    if not args.url or not args.arm or not args.output:
        parser.error("--url, --arm, and --output are required")
    terminal = run_arm(args.url.rstrip("/") + "/v1/completions", args.output.resolve(), args.arm, args.timeout)
    print(json.dumps({k: terminal[k] for k in ("classification", "arm", "request_rows", "successful_rows", "service_seconds_per_request", "p95_seconds")}, sort_keys=True))
    return 0 if terminal["classification"] == "endpoint_arm_complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
