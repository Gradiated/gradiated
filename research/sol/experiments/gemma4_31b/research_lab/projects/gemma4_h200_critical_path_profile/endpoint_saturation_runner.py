#!/usr/bin/env python3
"""Run one exact-distinct Gemma endpoint saturation arm on a live SGLang server."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import pathlib
import statistics
import subprocess
import threading
import time
import urllib.request


BASE = "http://127.0.0.1:30000"
MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
COMMON_TOKENS = 535
SEED = "gemma4-background-exact-mix-c32-20260718"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def tokens(label: str, count: int) -> list[int]:
    result: list[int] = []
    index = 0
    while len(result) < count:
        digest = hashlib.sha256(f"{SEED}|{label}|{index}".encode()).digest()
        for offset in range(0, len(digest), 4):
            result.append(1000 + int.from_bytes(digest[offset : offset + 4], "big") % 249000)
            if len(result) == count:
                return result
        index += 1
    return result


def get(path: str) -> bytes:
    return urllib.request.urlopen(BASE + path, timeout=30).read()


def post(body: dict, timeout: float = 900) -> urllib.response.addinfourl:
    request = urllib.request.Request(BASE + "/v1/completions", canonical(body), {"Content-Type": "application/json"})
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


def gpu_sample(path: pathlib.Path, stop: threading.Event) -> None:
    with path.open("w") as out:
        out.write("monotonic_s,utilization_gpu_pct,memory_used_mib,power_w\n")
        while not stop.is_set():
            result = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,power.draw", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False, timeout=5)
            out.write(f"{time.monotonic():.6f},{result.stdout.strip()}\n")
            out.flush()
            stop.wait(0.25)


def one(index: int, body: dict, root: pathlib.Path, ready: threading.Barrier, release: threading.Barrier, dispatch: list[float]) -> dict:
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
        with post(body) as response:
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
                    if item.get("usage"):
                        usage = item["usage"]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:2000]
    ended = time.monotonic()
    raw_response = b"".join(chunks)
    (root / f"response-{index:02d}.sse").write_bytes(raw_response)
    row = {"index": index, "started_monotonic_s": started, "first_token_monotonic_s": first, "ended_monotonic_s": ended, "wall_seconds": ended - started, "ttft_seconds": None if first is None else first - started, "queue_seconds_proxy": started - dispatch[0], "decode_seconds": None if first is None else ended - first, "error": error, "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"), "returned_token_ids": len(output_ids), "text_nonempty": bool(text), "text_finite": error is None, "request_sha256": hashlib.sha256(canonical(body)).hexdigest(), "response_sha256": hashlib.sha256(raw_response).hexdigest()}
    atomic(root / f"request-{index:02d}.json", row)
    return row


def finite_summary(values: list[float | None]) -> dict[str, float | None]:
    values = [value for value in values if value is not None and math.isfinite(value)]
    return {"mean": statistics.mean(values) if values else None, "median": statistics.median(values) if values else None, "max": max(values) if values else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--concurrency", type=int, required=True, choices=(32, 48, 64))
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    prefix = tokens("common-prefix", COMMON_TOKENS)
    bodies = []
    for index in range(args.concurrency):
        suffix = tokens(f"suffix-{index}", PROMPT_TOKENS - COMMON_TOKENS)
        suffix[0] = 200000 + index
        bodies.append({"model": MODEL, "prompt": prefix + suffix, "max_tokens": OUTPUT_TOKENS, "min_tokens": OUTPUT_TOKENS, "ignore_eos": True, "temperature": 0, "seed": 20260718, "stream": True, "stream_options": {"include_usage": True}, "return_token_ids": True, "add_special_tokens": False})
    atomic(root / "WORKLOAD.json", {"prompt_tokens": PROMPT_TOKENS, "output_tokens": OUTPUT_TOKENS, "concurrency": args.concurrency, "shared_prefix_tokens": COMMON_TOKENS, "exact_distinct_suffixes": True, "request_sha256": [hashlib.sha256(canonical(body)).hexdigest() for body in bodies]})
    get("/v1/models")
    flush = urllib.request.urlopen(urllib.request.Request(BASE + "/flush_cache", b"{}", {"Content-Type": "application/json"}), timeout=30)
    (root / "flush-cache.json").write_bytes(flush.read())
    warmup_suffix = tokens("warmup-suffix", PROMPT_TOKENS - COMMON_TOKENS)
    warmup_suffix[0] = 199999
    warmup = dict(bodies[0]); warmup.update({"prompt": prefix + warmup_suffix, "max_tokens": 1, "min_tokens": 1, "stream": False})
    with post(warmup) as response:
        (root / "warmup.json").write_bytes(response.read())
    before = get("/metrics"); (root / "metrics-before.prom").write_bytes(before)
    ready = threading.Barrier(args.concurrency + 1)
    release = threading.Barrier(args.concurrency + 1)
    dispatch = [0.0]
    stop = threading.Event(); sampler = threading.Thread(target=gpu_sample, args=(root / "gpu.csv", stop), daemon=True); sampler.start()
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(one, index, body, root, ready, release, dispatch) for index, body in enumerate(bodies)]
        ready.wait(timeout=120)
        dispatch[0] = time.monotonic()
        release.wait(timeout=120)
        rows = [future.result() for future in futures]
    batch_seconds = time.monotonic() - started
    stop.set(); sampler.join(timeout=3)
    after = get("/metrics"); (root / "metrics-after.prom").write_bytes(after)
    prompt_delta = metric_sum(after, "sglang:prompt_tokens_histogram_sum") - metric_sum(before, "sglang:prompt_tokens_histogram_sum")
    uncached_delta = metric_sum(after, "sglang:uncached_prompt_tokens_histogram_sum") - metric_sum(before, "sglang:uncached_prompt_tokens_histogram_sum")
    cached_delta = prompt_delta - uncached_delta
    expected_prompt = PROMPT_TOKENS * args.concurrency
    expected_cached = COMMON_TOKENS * args.concurrency
    expected_uncached = expected_prompt - expected_cached
    valid = all(row["error"] is None and row["prompt_tokens"] == PROMPT_TOKENS and row["completion_tokens"] == OUTPUT_TOKENS and row["text_nonempty"] and row["text_finite"] for row in rows) and (prompt_delta, uncached_delta, cached_delta) == (expected_prompt, expected_uncached, expected_cached)
    terminal = {"schema_version": 1, "kind": "gemma4_sglang_v0512_exact_distinct_saturation", "arm": args.arm, "pass": valid, "concurrency": args.concurrency, "complete_requests": sum(row["error"] is None for row in rows), "batch_seconds": batch_seconds, "service_seconds_per_request": batch_seconds / args.concurrency, "complete_request_throughput": args.concurrency / batch_seconds, "prompt_tokens_per_second": expected_prompt / batch_seconds, "output_tokens_per_second": args.concurrency * OUTPUT_TOKENS / batch_seconds, "cache": {"prompt_tokens_delta": prompt_delta, "uncached_prompt_tokens_delta": uncached_delta, "cached_prompt_tokens_delta": cached_delta, "expected_prompt_tokens_delta": expected_prompt, "expected_uncached_prompt_tokens_delta": expected_uncached, "expected_cached_prompt_tokens_delta": expected_cached, "accounting_matches": (prompt_delta, uncached_delta, cached_delta) == (expected_prompt, expected_uncached, expected_cached)}, "phases": {"ttft": finite_summary([row["ttft_seconds"] for row in rows]), "queue_proxy": finite_summary([row["queue_seconds_proxy"] for row in rows]), "decode": finite_summary([row["decode_seconds"] for row in rows]), "end_to_end": finite_summary([row["wall_seconds"] for row in rows])}, "rows": rows}
    atomic(root / "TERMINAL.json", terminal)
    return 0 if valid else 72


if __name__ == "__main__":
    raise SystemExit(main())
