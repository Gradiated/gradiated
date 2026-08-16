#!/usr/bin/env python3
"""Exact Gemma campaign runner adapted from the shared vLLM batched runner.

The submitted prompt-token IDs, rather than a coordinator tokenizer estimate,
are authoritative.  Every response is streamed and its original SSE bytes are
retained next to the normalized timing/token evidence.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import random
import statistics
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


MODEL = os.environ.get("VLLM_MODEL", "google/gemma-4-31B-it")
BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:30000")
PRIMARY_INPUT_TOKENS = 4214
OUTPUT_TOKENS = 358
SHARED_PREFIX_TOKENS = 535
CONCURRENCIES = (1, 4, 8, 16)
REQUESTS_BY_CONCURRENCY = {1: 4, 4: 8, 8: 16, 16: 32}
METRIC_SUFFIXES = (
    "request_queue_time_seconds_sum",
    "request_queue_time_seconds_count",
    "request_prefill_time_seconds_sum",
    "request_prefill_time_seconds_count",
    "request_decode_time_seconds_sum",
    "request_decode_time_seconds_count",
    "time_to_first_token_seconds_sum",
    "time_to_first_token_seconds_count",
    "inter_token_latency_seconds_sum",
    "inter_token_latency_seconds_count",
    "request_time_per_output_token_seconds_sum",
    "request_time_per_output_token_seconds_count",
    "prefix_cache_queries_total",
    "prefix_cache_hits_total",
    "gpu_cache_usage_perc",
    "num_requests_running",
    "num_requests_waiting",
)


class RunnerError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    rows = sorted(values)
    return rows[min(len(rows) - 1, max(0, math.ceil(fraction * len(rows)) - 1))]


def shared_prefix(vocab_size: int) -> list[int]:
    if vocab_size <= 80_000:
        raise RunnerError("tokenizer vocabulary is unexpectedly small")
    return [1000 + ((position * 7919 + 17) % 48_000) for position in range(SHARED_PREFIX_TOKENS)]


def prompt_ids(token_count: int, request_key: int, vocab_size: int, *, shared: bool) -> list[int]:
    """Return valid deterministic IDs with a mechanically exact common prefix.

    The first suffix ID is request-specific and outside the filler range, so
    pairwise longest-common-prefix length is exactly 535 for primary prompts.
    """
    prefix = shared_prefix(vocab_size) if shared else []
    suffix_count = token_count - len(prefix)
    if suffix_count <= 0:
        raise RunnerError("prompt is shorter than its declared shared prefix")
    first = 60_000 + (request_key % 10_000)
    rng = random.Random(0x47454D4D410000 + request_key)
    suffix = [first] + [1000 + rng.randrange(48_000) for _ in range(suffix_count - 1)]
    result = prefix + suffix
    if len(result) != token_count or any(token < 0 or token >= vocab_size for token in result):
        raise RunnerError("generated prompt token IDs violate the exact geometry")
    return result


def longest_common_prefix(left: list[int], right: list[int]) -> int:
    result = 0
    for a, b in zip(left, right):
        if a != b:
            break
        result += 1
    return result


def build_primary_prompts(keys: list[int], vocab_size: int) -> list[list[int]]:
    prompts = [prompt_ids(PRIMARY_INPUT_TOKENS, key, vocab_size, shared=True) for key in keys]
    if len({digest(canonical(prompt[SHARED_PREFIX_TOKENS:])) for prompt in prompts}) != len(prompts):
        raise RunnerError("primary suffix hashes are not distinct")
    if len(prompts) > 1 and any(
        longest_common_prefix(prompts[0], prompt) != SHARED_PREFIX_TOKENS for prompt in prompts[1:]
    ):
        raise RunnerError("primary prompts share content beyond the intended 535 tokenizer IDs")
    return prompts


def get_metrics() -> tuple[str, dict[str, float]]:
    with urllib.request.urlopen(BASE_URL + "/metrics", timeout=30) as response:
        text = response.read().decode(errors="replace")
    totals = {suffix: 0.0 for suffix in METRIC_SUFFIXES}
    for line in text.splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        name, raw = line.rsplit(" ", 1)
        base = name.split("{", 1)[0]
        for suffix in METRIC_SUFFIXES:
            if base.endswith(suffix):
                try:
                    totals[suffix] += float(raw)
                except ValueError:
                    pass
    return text, totals


def metrics_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {key: after[key] - before[key] for key in before}


def stream_completion(
    prompt: list[int],
    request_index: int,
    concurrency: int,
    output: Path,
    tokenizer,
    *,
    timeout: int = 900,
) -> dict:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": OUTPUT_TOKENS,
        "ignore_eos": True,
        "seed": 20260717 + request_index,
        "stream": True,
        "stream_options": {"include_usage": True},
        "return_token_ids": True,
    }
    body = canonical(payload)
    stem = f"c{concurrency}-r{request_index:04d}"
    (output / "request-bodies" / f"{stem}.json").write_bytes(body)
    raw_path = output / "raw-sse" / f"{stem}.sse"
    request = urllib.request.Request(
        BASE_URL + "/v1/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started_wall_ns = time.time_ns()
    started = time.monotonic()
    first = end = None
    previous_event = None
    usage = None
    finish_reason = None
    output_ids: list[int] = []
    text_parts: list[str] = []
    event_monotonic: list[float] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, raw_path.open("wb") as raw_handle:
            for raw in response:
                raw_handle.write(raw)
                line = raw.strip()
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    end = time.monotonic()
                    break
                value = json.loads(data)
                if isinstance(value.get("usage"), dict):
                    usage = value["usage"]
                choices = value.get("choices") or []
                if choices:
                    choice = choices[0]
                    token_ids = choice.get("token_ids")
                    text = choice.get("text") or ""
                    if token_ids is not None:
                        if not isinstance(token_ids, list) or any(not isinstance(token, int) for token in token_ids):
                            raise RunnerError("stream output token IDs are malformed")
                        output_ids.extend(token_ids)
                    if text:
                        text_parts.append(text)
                    if token_ids or text:
                        now = time.monotonic()
                        if first is None:
                            first = now
                        event_monotonic.append(now)
                        previous_event = now
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice["finish_reason"]
    except urllib.error.HTTPError as error:
        detail = error.read(2048).decode(errors="replace")
        raise RunnerError(f"HTTP {error.code}: {detail}") from error
    if first is None or end is None or usage is None:
        raise RunnerError("stream lacks first-token, end, or usage evidence")
    server_input = int(usage.get("prompt_tokens", -1))
    server_output = int(usage.get("completion_tokens", -1))
    if server_input != len(prompt) or server_output != OUTPUT_TOKENS:
        raise RunnerError(f"server geometry mismatch: {server_input}/{server_output}")
    if len(output_ids) != server_output:
        raise RunnerError("streamed output token IDs are incomplete")
    text = "".join(text_parts)
    retokenized = tokenizer.encode(text, add_special_tokens=False)
    intervals = [(b - a) * 1000 for a, b in zip(event_monotonic, event_monotonic[1:])]
    ended_wall_ns = time.time_ns()
    return {
        "request_index": request_index,
        "concurrency": concurrency,
        "status": "complete",
        "input_token_ids": prompt,
        "input_token_ids_sha256": digest(canonical(prompt)),
        "input_suffix_sha256": digest(canonical(prompt[SHARED_PREFIX_TOKENS:])),
        "request_body_path": f"request-bodies/{stem}.json",
        "request_body_bytes": len(body),
        "request_body_sha256": digest(body),
        "raw_sse_path": f"raw-sse/{stem}.sse",
        "raw_sse_bytes": raw_path.stat().st_size,
        "raw_sse_sha256": digest(raw_path.read_bytes()),
        "input_tokens_server": server_input,
        "output_tokens_server": server_output,
        "output_token_ids": output_ids,
        "output_token_ids_sha256": digest(canonical(output_ids)),
        "retokenized_text_output_ids": retokenized,
        "retokenized_text_output_ids_sha256": digest(canonical(retokenized)),
        "retokenization_boundary": "diagnostic encode of concatenated streamed text; submitted/served output IDs remain authoritative",
        "finish_reason": finish_reason,
        "started_wall_ns": started_wall_ns,
        "ended_wall_ns": ended_wall_ns,
        "started_monotonic": started,
        "first_token_monotonic": first,
        "ended_monotonic": end,
        "ttft_ms": (first - started) * 1000,
        "end_to_end_ms": (end - started) * 1000,
        "itl_ms": {
            "count": len(intervals),
            "mean": statistics.fmean(intervals) if intervals else None,
            "p50": percentile(intervals, 0.50),
            "p95": percentile(intervals, 0.95),
            "p99": percentile(intervals, 0.99),
        },
    }


def run_wave(
    prompts: list[list[int]],
    request_indices: list[int],
    concurrency: int,
    output: Path,
    tokenizer,
) -> tuple[list[dict], dict]:
    barrier = threading.Barrier(concurrency)
    barrier_released_ns = 0
    lock = threading.Lock()

    def staged(prompt: list[int], request_index: int) -> dict:
        nonlocal barrier_released_ns
        barrier.wait(timeout=60)
        now = time.time_ns()
        with lock:
            if barrier_released_ns == 0:
                barrier_released_ns = now
        return stream_completion(prompt, request_index, concurrency, output, tokenizer)

    rows: list[dict] = []
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(staged, prompt, index) for prompt, index in zip(prompts, request_indices, strict=True)]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
    ended = time.monotonic()
    start_span_ms = (max(row["started_wall_ns"] for row in rows) - min(row["started_wall_ns"] for row in rows)) / 1e6
    proof = {
        "barrier_parties": concurrency,
        "barrier_released_wall_ns": barrier_released_ns,
        "request_start_span_ms": start_span_ms,
        "overlap_pass": concurrency == 1 or max(row["started_monotonic"] for row in rows) < min(row["ended_monotonic"] for row in rows),
        "wall_seconds": ended - started,
    }
    return sorted(rows, key=lambda row: row["request_index"]), proof


def run_phase(output: Path, tokenizer, vocab_size: int, concurrency: int, requests: int, key_base: int) -> dict:
    before_text, before = get_metrics()
    (output / f"metrics-c{concurrency}-before.prom").write_text(before_text)
    rows: list[dict] = []
    waves = []
    phase_started = time.monotonic()
    for wave_index, offset in enumerate(range(0, requests, concurrency)):
        keys = [key_base + offset + index for index in range(concurrency)]
        prompts = build_primary_prompts(keys, vocab_size)
        indices = [key_base + offset + index for index in range(concurrency)]
        wave_rows, proof = run_wave(prompts, indices, concurrency, output, tokenizer)
        proof["wave_index"] = wave_index
        waves.append(proof)
        rows.extend(wave_rows)
    phase_wall = time.monotonic() - phase_started
    after_text, after = get_metrics()
    (output / f"metrics-c{concurrency}-after.prom").write_text(after_text)
    delta = metrics_delta(before, after)
    result = {
        "concurrency": concurrency,
        "requests": requests,
        "streaming": True,
        "simultaneous_barrier_waves": waves,
        "simultaneous_requests_pass": all(wave["overlap_pass"] for wave in waves),
        "complete_count": len(rows),
        "failure_count": 0,
        "wall_seconds": phase_wall,
        "completed_requests_per_second": len(rows) / phase_wall,
        "ttft_ms": {
            "p50": percentile([row["ttft_ms"] for row in rows], 0.50),
            "p95": percentile([row["ttft_ms"] for row in rows], 0.95),
            "p99": percentile([row["ttft_ms"] for row in rows], 0.99),
        },
        "server_metrics_delta": delta,
        "rows": rows,
    }
    return result


def run_10k(output: Path, tokenizer, vocab_size: int, request_index: int) -> dict:
    prompt = prompt_ids(10_000, request_index, vocab_size, shared=False)
    before_text, before = get_metrics()
    (output / "metrics-10k-before.prom").write_text(before_text)
    started = time.monotonic()
    row = stream_completion(prompt, request_index, 1, output, tokenizer)
    wall = time.monotonic() - started
    after_text, after = get_metrics()
    (output / "metrics-10k-after.prom").write_text(after_text)
    row["server_metrics_delta"] = metrics_delta(before, after)
    row["wall_seconds"] = wall
    row["separate_from_primary"] = True
    return row


def summarize_prefill_share(delta: dict[str, float]) -> dict:
    prefill = delta["request_prefill_time_seconds_sum"]
    decode = delta["request_decode_time_seconds_sum"]
    share = prefill / (prefill + decode) if prefill > 0 and decode >= 0 else None
    return {
        "prefill_seconds": prefill,
        "decode_seconds": decode,
        "exposed_prefill_share": share,
        "threshold": 0.393755,
        "metric_present": prefill > 0 and decode >= 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--mode", choices=("baseline", "prefix-on", "prefix-off"), default="baseline")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "raw-sse").mkdir()
    (args.output / "request-bodies").mkdir()
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    vocab_size = int(tokenizer.vocab_size)
    result = {
        "schema_version": 2,
        "runner_provenance": "narrow exact-token adaptation of shared vllm_batched_runner.py streaming/barrier/metrics path",
        "mode": args.mode,
        "identity": {"model": MODEL, "tokenizer": str(args.tokenizer), "vocab_size": vocab_size},
        "sampling": {"temperature": 0, "top_p": 1, "max_tokens": OUTPUT_TOKENS, "ignore_eos": True, "stream": True, "return_token_ids": True},
        "template": {"applied": False, "reason": "authoritative prompt token IDs submitted directly"},
        "stop": {"sequences": [], "ignore_eos": True},
        "workload": {
            "primary_input_tokens": PRIMARY_INPUT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "shared_prefix_token_ids": shared_prefix(vocab_size),
            "shared_prefix_tokens": SHARED_PREFIX_TOKENS,
            "intended_shared_fraction": SHARED_PREFIX_TOKENS / PRIMARY_INPUT_TOKENS,
            "concurrencies": list(CONCURRENCIES),
            "separate_10k_input_tokens": 10_000,
        },
        "profiles": [],
        "single_10k": None,
        "pass": False,
    }
    global_before_text, global_before = get_metrics()
    (args.output / "metrics-global-before.prom").write_text(global_before_text)
    try:
        if args.mode == "baseline":
            for phase_index, concurrency in enumerate(CONCURRENCIES):
                result["profiles"].append(
                    run_phase(args.output, tokenizer, vocab_size, concurrency, REQUESTS_BY_CONCURRENCY[concurrency], 10_000 * (phase_index + 1))
                )
            result["single_10k"] = run_10k(args.output, tokenizer, vocab_size, 90_000)
        else:
            # Both retained arms use the same keys, geometry, and simultaneous c16 wave.
            result["profiles"].append(run_phase(args.output, tokenizer, vocab_size, 16, 16, 70_000))
        global_after_text, global_after = get_metrics()
        (args.output / "metrics-global-after.prom").write_text(global_after_text)
        delta = metrics_delta(global_before, global_after)
        result["server_metrics_delta"] = delta
        result["prefill_decode"] = summarize_prefill_share(delta)
        result["complete_count"] = sum(profile["complete_count"] for profile in result["profiles"]) + (1 if result["single_10k"] else 0)
        result["failure_count"] = 0
        result["useful_gpu_seconds"] = sum(profile["wall_seconds"] for profile in result["profiles"]) + (
            result["single_10k"]["wall_seconds"] if result["single_10k"] else 0
        )
        all_rows = [row for profile in result["profiles"] for row in profile["rows"]]
        exact_primary = all(row["input_tokens_server"] == PRIMARY_INPUT_TOKENS and row["output_tokens_server"] == OUTPUT_TOKENS for row in all_rows)
        suffixes_distinct = len({row["input_suffix_sha256"] for row in all_rows}) == len(all_rows)
        raw_complete = all(row["raw_sse_bytes"] > 0 and row["output_tokens_server"] == len(row["output_token_ids"]) for row in all_rows)
        exact_10k = result["single_10k"] is None or (
            result["single_10k"]["input_tokens_server"] == 10_000 and result["single_10k"]["output_tokens_server"] == OUTPUT_TOKENS
        )
        result["raw_metric_contract"] = {
            "all_request_body_bytes_present": all(row["request_body_bytes"] > 0 for row in all_rows),
            "all_raw_sse_bytes_present": raw_complete,
            "all_output_token_ids_complete": raw_complete,
            "global_metrics_before_after_present": True,
            "queue_prefill_decode_cache_fields_present": all(key in delta for key in METRIC_SUFFIXES),
        }
        result["pass"] = bool(
            exact_primary and suffixes_distinct and raw_complete and exact_10k
            and all(profile["simultaneous_requests_pass"] for profile in result["profiles"])
            and all(result["raw_metric_contract"].values())
        )
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
    temporary = args.output / "runner-result.json.part"
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output / "runner-result.json")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
