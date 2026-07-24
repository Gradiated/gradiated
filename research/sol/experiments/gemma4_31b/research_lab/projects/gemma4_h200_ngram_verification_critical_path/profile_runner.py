#!/usr/bin/env python3
"""Run the pinned SGLang exact-token c32 background workload."""

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
CONCURRENCY = 32
SEED = "gemma4-background-exact-mix-c32-20260718"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: pathlib.Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


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


def post_control(path: str, body: dict) -> bytes:
    request = urllib.request.Request(
        BASE + path,
        canonical(body),
        {"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=60).read()


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


def one(index: int, body: dict, root: pathlib.Path, ready: threading.Barrier, release: threading.Barrier) -> dict:
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
                    if choice.get("token_ids"):
                        output_ids.extend(choice["token_ids"])
                    if item.get("usage"):
                        usage = item["usage"]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:2000]
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
        "queue_seconds_proxy": None,
        "error": error,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "returned_token_ids": len(output_ids),
        "text_nonempty": bool(text),
        "text_finite": error is None,
        "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
        "response_sha256": hashlib.sha256(raw_response).hexdigest(),
    }
    atomic(root / f"request-{index:02d}.json", row)
    return row


def finite_summary(values: list[float | None]) -> dict[str, float | None]:
    data = [x for x in values if x is not None and math.isfinite(x)]
    return {"mean": statistics.mean(data) if data else None, "median": statistics.median(data) if data else None, "max": max(data) if data else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--concurrency", type=int, default=32)
    args = parser.parse_args()
    concurrency = args.concurrency
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    prefix = tokens("common-prefix", COMMON_TOKENS)
    bodies = []
    for index in range(concurrency):
        suffix = tokens(f"suffix-{index}", PROMPT_TOKENS - COMMON_TOKENS)
        suffix[0] = 200000 + index
        bodies.append({"model": MODEL, "prompt": prefix + suffix, "max_tokens": OUTPUT_TOKENS, "min_tokens": OUTPUT_TOKENS, "ignore_eos": True, "temperature": 0, "seed": 20260718, "stream": True, "stream_options": {"include_usage": True}, "return_token_ids": True, "add_special_tokens": False})
    atomic(root / "WORKLOAD.json", {"prompt_tokens": PROMPT_TOKENS, "output_tokens": OUTPUT_TOKENS, "concurrency": concurrency, "shared_prefix_tokens": COMMON_TOKENS, "intended_shared_prefix_fraction": COMMON_TOKENS / PROMPT_TOKENS, "request_sha256": [hashlib.sha256(canonical(x)).hexdigest() for x in bodies]})
    get("/v1/models")
    try:
        urllib.request.urlopen(urllib.request.Request(BASE + "/flush_cache", b"{}", {"Content-Type": "application/json"}), timeout=30).read()
    except Exception as exc:
        (root / "flush_cache.error").write_text(repr(exc) + "\n")
    warmup_suffix = tokens("warmup-suffix", PROMPT_TOKENS - COMMON_TOKENS)
    warmup_suffix[0] = 199999
    warmup = dict(bodies[0]); warmup.update({"prompt": prefix + warmup_suffix, "max_tokens": 1, "min_tokens": 1, "stream": False})
    with post(warmup) as response:
        (root / "warmup.json").write_bytes(response.read())
    profile_output = "/work/artifacts/profile/torch"
    profile_response = post_control(
        "/start_profile",
        {
            "output_dir": profile_output,
            "num_steps": 16,
            "activities": ["CPU", "GPU"],
            "merge_profiles": False,
        },
    )
    (root / "profile-start.json").write_bytes(profile_response)
    before = get("/metrics"); (root / "metrics-before.prom").write_bytes(before)
    ready = threading.Barrier(concurrency + 1)
    release = threading.Barrier(concurrency + 1)
    stop = threading.Event(); sampler = threading.Thread(target=gpu_sample, args=(root / "gpu.csv", stop), daemon=True); sampler.start()
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one, i, body, root, ready, release) for i, body in enumerate(bodies)]
        ready.wait(timeout=120)
        release.wait(timeout=120)
        rows = [future.result() for future in futures]
    batch_seconds = time.monotonic() - started
    stop.set(); sampler.join(timeout=3)
    after = get("/metrics"); (root / "metrics-after.prom").write_bytes(after)
    prompt_before = metric_sum(before, "sglang:prompt_tokens_histogram_sum")
    prompt_after = metric_sum(after, "sglang:prompt_tokens_histogram_sum")
    uncached_before = metric_sum(before, "sglang:uncached_prompt_tokens_histogram_sum")
    uncached_after = metric_sum(after, "sglang:uncached_prompt_tokens_histogram_sum")
    prompt_delta = None if prompt_before is None or prompt_after is None else prompt_after - prompt_before
    uncached_delta = None if uncached_before is None or uncached_after is None else uncached_after - uncached_before
    cached_delta = None if prompt_delta is None or uncached_delta is None else prompt_delta - uncached_delta
    valid = all(row["error"] is None and row["prompt_tokens"] == PROMPT_TOKENS and row["completion_tokens"] == OUTPUT_TOKENS and row["text_nonempty"] and row["text_finite"] for row in rows)
    terminal = {"schema_version": 1, "kind": "gemma4_sglang_v0512_exact_mix", "arm": args.arm, "pass": valid, "concurrency": concurrency, "complete_requests": sum(row["error"] is None for row in rows), "batch_seconds": batch_seconds, "service_seconds_per_request": batch_seconds / concurrency, "complete_request_throughput": concurrency / batch_seconds, "output_tokens_per_second": concurrency * OUTPUT_TOKENS / batch_seconds, "cache": {"prompt_tokens_delta": prompt_delta, "uncached_prompt_tokens_delta": uncached_delta, "cached_prompt_tokens_delta": cached_delta, "cached_fraction": None if cached_delta is None or not prompt_delta else cached_delta / prompt_delta, "fresh_tokens_per_request": None if uncached_delta is None else uncached_delta / concurrency}, "phases": {"ttft": finite_summary([row["ttft_seconds"] for row in rows]), "decode": finite_summary([row["decode_seconds"] for row in rows]), "end_to_end": finite_summary([row["wall_seconds"] for row in rows])}, "rows": rows}
    atomic(root / "TERMINAL.json", terminal)
    return 0 if valid else 72


if __name__ == "__main__":
    raise SystemExit(main())
