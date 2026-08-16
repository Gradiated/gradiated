#!/usr/bin/env python3
"""One-shot exact Gemma 4 c32 SGLang endpoint consumer.

The workload is regenerated from the qualified seed and accepted only when its
canonical request hashes equal the mechanically supplied WORKLOAD.json.  The
science marker is written immediately before the single barrier release.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import threading
import time
import urllib.request

MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
COMMON_TOKENS = 535
CONCURRENCY = 32
SEED = "gemma4-background-exact-mix-c32-20260718"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def token_ids(label: str, count: int) -> list[int]:
    result: list[int] = []
    index = 0
    while len(result) < count:
        digest = hashlib.sha256(f"{SEED}|{label}|{index}".encode()).digest()
        for offset in range(0, len(digest), 4):
            result.append(
                1000
                + int.from_bytes(digest[offset : offset + 4], "big") % 249000
            )
            if len(result) == count:
                return result
        index += 1
    return result


def request_bodies() -> list[dict]:
    prefix = token_ids("common-prefix", COMMON_TOKENS)
    bodies = []
    for index in range(CONCURRENCY):
        suffix = token_ids(f"suffix-{index}", PROMPT_TOKENS - COMMON_TOKENS)
        suffix[0] = 200000 + index
        bodies.append(
            {
                "model": MODEL,
                "prompt": prefix + suffix,
                "max_tokens": OUTPUT_TOKENS,
                "min_tokens": OUTPUT_TOKENS,
                "ignore_eos": True,
                "temperature": 0,
                "seed": 20260718,
                "stream": True,
                "stream_options": {"include_usage": True},
                "return_token_ids": True,
                "add_special_tokens": False,
            }
        )
    return bodies


def workload_identity(bodies: list[dict]) -> dict:
    return {
        "concurrency": CONCURRENCY,
        "intended_shared_prefix_fraction": COMMON_TOKENS / PROMPT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "prompt_tokens": PROMPT_TOKENS,
        "request_sha256": [
            hashlib.sha256(canonical(body)).hexdigest() for body in bodies
        ],
        "shared_prefix_tokens": COMMON_TOKENS,
    }


def get(endpoint: str, path: str, timeout: float = 30) -> bytes:
    return urllib.request.urlopen(endpoint + path, timeout=timeout).read()


def post(endpoint: str, body: dict, timeout: float = 900):
    request = urllib.request.Request(
        endpoint + "/v1/completions",
        canonical(body),
        {"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def metric_sum(raw: bytes, name: str) -> float | None:
    values = []
    for line in raw.decode(errors="replace").splitlines():
        if line.startswith(name) and not line.startswith("#"):
            try:
                values.append(float(line.rsplit(" ", 1)[1]))
            except (IndexError, ValueError):
                pass
    return sum(values) if values else None


def one(
    index: int,
    body: dict,
    root: Path,
    endpoint: str,
    ready: threading.Barrier,
    release: threading.Barrier,
) -> dict:
    ready.wait(timeout=120)
    release.wait(timeout=120)
    started = time.monotonic()
    first = None
    chunks: list[bytes] = []
    error = None
    output_ids: list[int] = []
    usage: dict = {}
    text = ""
    try:
        with post(endpoint, body) as response:
            for raw in response:
                now = time.monotonic()
                chunks.append(raw)
                if raw.startswith(b"data: ") and raw.strip() != b"data: [DONE]":
                    item = json.loads(raw[6:])
                    choice = (item.get("choices") or [{}])[0]
                    if choice.get("text") and first is None:
                        first = now
                    text += choice.get("text") or ""
                    output_ids.extend(choice.get("token_ids") or [])
                    usage = item.get("usage") or usage
    except Exception as error_value:  # Preserve the raw partial response.
        error = f"{type(error_value).__name__}: {error_value}"[:2000]
    ended = time.monotonic()
    raw_response = b"".join(chunks)
    (root / f"response-{index:02d}.sse").write_bytes(raw_response)
    row = {
        "index": index,
        "started_monotonic_s": started,
        "first_token_monotonic_s": first,
        "ended_monotonic_s": ended,
        "wall_seconds": ended - started,
        "ttft_seconds": None if first is None else first - started,
        "decode_seconds": None if first is None else ended - first,
        "error": error,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "returned_token_ids": len(output_ids),
        "text_nonempty": bool(text),
        "text_finite": error is None,
        "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
        "response_sha256": hashlib.sha256(raw_response).hexdigest(),
    }
    atomic_json(root / f"request-{index:02d}.json", row)
    return row


def finite_summary(values: list[float | None]) -> dict[str, float | None]:
    finite = [x for x in values if x is not None and math.isfinite(x)]
    return {
        "mean": statistics.mean(finite) if finite else None,
        "median": statistics.median(finite) if finite else None,
        "max": max(finite) if finite else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:30000")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--arm", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output_must_not_exist")

    bodies = request_bodies()
    generated = workload_identity(bodies)
    supplied = json.loads(args.workload.read_text())
    if canonical(generated) != canonical(supplied):
        raise SystemExit("qualified_workload_identity_mismatch")

    root = args.output
    root.mkdir(parents=True)
    atomic_json(
        root / "WORKLOAD_IDENTITY.json",
        {
            "workload_sha256": sha256(args.workload),
            "identity": generated,
            "arm": args.arm,
        },
    )
    models = get(args.endpoint, "/v1/models")
    (root / "models-before.json").write_bytes(models)
    if MODEL.encode() not in models:
        raise SystemExit("served_model_identity_mismatch")

    try:
        request = urllib.request.Request(
            args.endpoint + "/flush_cache",
            b"{}",
            {"Content-Type": "application/json"},
        )
        (root / "flush-cache.json").write_bytes(
            urllib.request.urlopen(request, timeout=30).read()
        )
    except Exception as error:
        (root / "flush-cache.error").write_text(repr(error) + "\n")
        raise

    warmup_suffix = token_ids("warmup-suffix", PROMPT_TOKENS - COMMON_TOKENS)
    warmup_suffix[0] = 199999
    warmup = dict(bodies[0])
    warmup.update(
        {
            "prompt": token_ids("common-prefix", COMMON_TOKENS) + warmup_suffix,
            "max_tokens": 1,
            "min_tokens": 1,
            "stream": False,
        }
    )
    with post(args.endpoint, warmup) as response:
        (root / "warmup.json").write_bytes(response.read())

    before = get(args.endpoint, "/metrics")
    (root / "metrics-before.prom").write_bytes(before)
    ready = threading.Barrier(CONCURRENCY + 1)
    release = threading.Barrier(CONCURRENCY + 1)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [
            pool.submit(one, i, body, root, args.endpoint, ready, release)
            for i, body in enumerate(bodies)
        ]
        ready.wait(timeout=120)
        atomic_json(
            root / "SCIENCE_STARTED.json",
            {
                "kind": "single_exact_c32_submission",
                "request_count": CONCURRENCY,
                "workload_sha256": sha256(args.workload),
                "monotonic_s": time.monotonic(),
            },
        )
        release.wait(timeout=120)
        rows = [future.result() for future in futures]
    batch_seconds = time.monotonic() - started
    after = get(args.endpoint, "/metrics")
    (root / "metrics-after.prom").write_bytes(after)

    prompt_before = metric_sum(before, "sglang:prompt_tokens_histogram_sum")
    prompt_after = metric_sum(after, "sglang:prompt_tokens_histogram_sum")
    uncached_before = metric_sum(
        before, "sglang:uncached_prompt_tokens_histogram_sum"
    )
    uncached_after = metric_sum(after, "sglang:uncached_prompt_tokens_histogram_sum")
    prompt_delta = (
        None
        if prompt_before is None or prompt_after is None
        else prompt_after - prompt_before
    )
    uncached_delta = (
        None
        if uncached_before is None or uncached_after is None
        else uncached_after - uncached_before
    )
    cached_delta = (
        None
        if prompt_delta is None or uncached_delta is None
        else prompt_delta - uncached_delta
    )
    valid = all(
        row["error"] is None
        and row["prompt_tokens"] == PROMPT_TOKENS
        and row["completion_tokens"] == OUTPUT_TOKENS
        and row["returned_token_ids"] == OUTPUT_TOKENS
        and row["text_nonempty"]
        and row["text_finite"]
        for row in rows
    )
    terminal = {
        "schema_version": 1,
        "kind": "gemma4_current_sglang_exact_c32",
        "arm": args.arm,
        "pass": valid,
        "sample_consumed": True,
        "concurrency": CONCURRENCY,
        "complete_requests": sum(row["error"] is None for row in rows),
        "batch_seconds": batch_seconds,
        "service_seconds_per_request": batch_seconds / CONCURRENCY,
        "complete_request_throughput": CONCURRENCY / batch_seconds,
        "output_tokens_per_second": CONCURRENCY * OUTPUT_TOKENS / batch_seconds,
        "cache": {
            "prompt_tokens_delta": prompt_delta,
            "uncached_prompt_tokens_delta": uncached_delta,
            "cached_tokens_delta": cached_delta,
        },
        "phases": {
            "ttft": finite_summary([row["ttft_seconds"] for row in rows]),
            "decode": finite_summary([row["decode_seconds"] for row in rows]),
            "end_to_end": finite_summary([row["wall_seconds"] for row in rows]),
        },
        "rows": rows,
    }
    atomic_json(root / "TERMINAL.json", terminal)
    return 0 if valid else 72


if __name__ == "__main__":
    raise SystemExit(main())
