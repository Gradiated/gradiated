#!/usr/bin/env python3
"""Sustained OpenAI-compatible streaming benchmark using only the stdlib."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass


@dataclass
class Result:
    started_at: float
    finished_at: float
    ttft_seconds: float
    prompt_tokens: int
    completion_tokens: int
    error: str = ""


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def prompt(repetitions: int) -> str:
    # Put a nonce first so SGLang cannot reuse the large common prompt prefix.
    prefix = f"Request {uuid.uuid4()}. "
    sentence = (
        "Evaluate a production inference system for latency throughput reliability "
        "capacity cost and operational risk. "
    )
    return prefix + sentence * repetitions


def request_once(args: argparse.Namespace) -> Result:
    started_at = time.monotonic()
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt(args.prompt_repetitions)}],
        "max_tokens": args.output_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "ignore_eos": True,
    }
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {args.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    first_token_at = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                usage = chunk.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens") or prompt_tokens)
                completion_tokens = int(usage.get("completion_tokens") or completion_tokens)
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    emitted = delta.get("content") or delta.get("reasoning_content")
                    if emitted and first_token_at == 0.0:
                        first_token_at = time.monotonic()
        finished_at = time.monotonic()
        if first_token_at == 0.0:
            raise RuntimeError("stream completed without a content token")
        if completion_tokens == 0:
            # ignore_eos makes this exact for successful requests, even when a
            # runtime omits usage from its final streaming chunk.
            completion_tokens = args.output_tokens
        return Result(
            started_at,
            finished_at,
            first_token_at - started_at,
            prompt_tokens,
            completion_tokens,
        )
    except Exception as error:  # noqa: BLE001 - benchmark records all failures
        return Result(started_at, time.monotonic(), 0.0, 0, 0, str(error))


def read_gpu_metrics(url: str, timeout: float) -> dict[str, float]:
    with urllib.request.urlopen(f"{url.rstrip('/')}/metrics", timeout=timeout) as response:
        body = response.read().decode()
    wanted = {
        "desmond_gpu_utilization_percent": "gpu_utilization_percent",
        "desmond_gpu_memory_utilization_percent": "gpu_memory_utilization_percent",
        "desmond_gpu_power_milliwatts": "gpu_power_watts",
    }
    metrics: dict[str, float] = {}
    for line in body.splitlines():
        for prefix, name in wanted.items():
            if line.startswith(prefix + "{") or line.startswith(prefix + " "):
                value = float(line.rsplit(" ", 1)[1])
                metrics[name] = value / 1000.0 if name == "gpu_power_watts" else value
    return metrics


def run_level(args: argparse.Namespace, concurrency: int, seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + seconds
    results: list[Result] = []
    results_lock = threading.Lock()
    samples: list[dict[str, float]] = []
    stop_metrics = threading.Event()

    def worker() -> None:
        while time.monotonic() < deadline:
            result = request_once(args)
            with results_lock:
                results.append(result)

    def monitor() -> None:
        while not stop_metrics.wait(1.0):
            try:
                samples.append(read_gpu_metrics(args.desmond_url, min(args.timeout, 5.0)))
            except Exception:
                pass

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(concurrency)]
        concurrent.futures.wait(futures)
    stop_metrics.set()
    monitor_thread.join(timeout=2)

    successful = [result for result in results if not result.error]
    failed = [result for result in results if result.error]
    if not successful:
        return {
            "concurrency": concurrency,
            "requested_seconds": seconds,
            "requests": len(results),
            "successful": 0,
            "errors": len(failed),
            "error_samples": [result.error for result in failed[:3]],
        }

    wall_seconds = max(result.finished_at for result in successful) - min(
        result.started_at for result in successful
    )
    latencies = [result.finished_at - result.started_at for result in successful]
    ttfts = [result.ttft_seconds for result in successful]
    decode_rates = [
        result.completion_tokens / max(result.finished_at - result.started_at - result.ttft_seconds, 1e-9)
        for result in successful
    ]
    output_tokens = sum(result.completion_tokens for result in successful)
    input_tokens = sum(result.prompt_tokens for result in successful)

    def sample_average(name: str) -> float:
        values = [sample[name] for sample in samples if name in sample]
        return statistics.fmean(values) if values else math.nan

    return {
        "concurrency": concurrency,
        "requested_seconds": seconds,
        "wall_seconds": round(wall_seconds, 3),
        "requests": len(results),
        "successful": len(successful),
        "errors": len(failed),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "request_rate": round(len(successful) / wall_seconds, 3),
        "aggregate_output_tps": round(output_tokens / wall_seconds, 2),
        "aggregate_total_tps": round((input_tokens + output_tokens) / wall_seconds, 2),
        "latency_p50_seconds": round(percentile(latencies, 0.50), 3),
        "latency_p95_seconds": round(percentile(latencies, 0.95), 3),
        "ttft_p50_seconds": round(percentile(ttfts, 0.50), 3),
        "ttft_p95_seconds": round(percentile(ttfts, 0.95), 3),
        "per_request_decode_tps_p50": round(percentile(decode_rates, 0.50), 2),
        "per_request_decode_tps_p95": round(percentile(decode_rates, 0.95), 2),
        "gpu_utilization_percent_avg": round(sample_average("gpu_utilization_percent"), 2),
        "gpu_memory_utilization_percent_avg": round(
            sample_average("gpu_memory_utilization_percent"), 2
        ),
        "gpu_power_watts_avg": round(sample_average("gpu_power_watts"), 2),
        "error_samples": [result.error for result in failed[:3]],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://10.96.0.50:30000")
    parser.add_argument("--desmond-url", default="http://10.96.0.50:9090")
    parser.add_argument("--model", default="google/gemma-4-31B-it")
    parser.add_argument("--api-key", default=os.environ.get("SGLANG_API_KEY", ""))
    parser.add_argument("--concurrencies", default="1,2,4,8,16,24")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--sustain-concurrency", type=int, default=0)
    parser.add_argument("--sustain-seconds", type=float, default=120)
    parser.add_argument("--prompt-repetitions", type=int, default=45)
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--cooldown-seconds", type=float, default=3)
    args = parser.parse_args()
    if not args.api_key:
        parser.error("--api-key or SGLANG_API_KEY is required")
    return args


def main() -> int:
    args = parse_args()
    levels = [int(value) for value in args.concurrencies.split(",")]
    print(
        json.dumps({"benchmark": "started", "unix_time": time.time(), "levels": levels}),
        flush=True,
    )
    all_results = []
    for concurrency in levels:
        result = run_level(args, concurrency, args.seconds)
        all_results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
        time.sleep(args.cooldown_seconds)
    if args.sustain_concurrency:
        result = run_level(args, args.sustain_concurrency, args.sustain_seconds)
        result["sustained"] = True
        all_results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    print(json.dumps({"benchmark": "finished", "unix_time": time.time(), "results": all_results}))
    return 0 if all(result.get("errors", 0) == 0 for result in all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
