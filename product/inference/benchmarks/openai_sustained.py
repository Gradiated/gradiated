#!/usr/bin/env python3
"""Sustained OpenAI-compatible streaming benchmark using only the stdlib."""

from __future__ import annotations

import argparse
import collections
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
    cached_prompt_tokens: int
    cacheable_prompt_tokens: int
    completion_tokens: int
    error: str = ""
    provider: str = ""


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


def unique_prompt(repetitions: int) -> str:
    # Put a nonce first so SGLang cannot reuse the large common prompt prefix.
    prefix = f"Request {uuid.uuid4()}. "
    sentence = (
        "Evaluate a production inference system for latency throughput reliability "
        "capacity cost and operational risk. "
    )
    return prefix + sentence * repetitions


def session_prefix_prompt(args: argparse.Namespace, session_id: str) -> str:
    prefix_sentence = (
        "The coding agent is inspecting a production repository. It must preserve existing "
        "behavior, use tools carefully, reason about tests, and make minimal verified changes. "
        "Repository context includes application code, configuration, logs, test output, API "
        "schemas, and prior conversation turns. "
    )
    suffix_sentence = (
        "Review the next implementation detail, identify the likely failure mode, and propose "
        "the smallest safe code change with a focused verification step. "
    )
    stable_prefix = (
        f"Coding-agent session {session_id}.\n\n"
        + prefix_sentence * args.session_prefix_repetitions
    )
    changing_suffix = (
        f"\n\nCurrent turn {uuid.uuid4()}.\n"
        + suffix_sentence * args.session_suffix_repetitions
    )
    return stable_prefix + changing_suffix


def request_once(
    args: argparse.Namespace,
    prompt_text: str | None = None,
    output_tokens: int | None = None,
    messages: list[dict[str, object]] | None = None,
) -> Result:
    started_at = time.monotonic()
    requested_output_tokens = output_tokens or args.output_tokens
    payload = {
        "model": args.model,
        "messages": messages
        or [
            {
                "role": "user",
                "content": prompt_text or unique_prompt(args.prompt_repetitions),
            }
        ],
        "max_tokens": requested_output_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if args.ignore_eos:
        payload["ignore_eos"] = True
    if args.provider:
        payload["provider"] = {
            "only": [args.provider],
            "allow_fallbacks": False,
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
    cached_prompt_tokens = 0
    completion_tokens = 0
    provider = ""
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                if isinstance(chunk.get("provider"), str):
                    provider = chunk["provider"]
                usage = chunk.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens") or prompt_tokens)
                prompt_details = usage.get("prompt_tokens_details") or {}
                cached_prompt_tokens = int(
                    prompt_details.get("cached_tokens") or cached_prompt_tokens
                )
                completion_tokens = int(usage.get("completion_tokens") or completion_tokens)
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    emitted = (
                        delta.get("content")
                        or delta.get("reasoning_content")
                        or delta.get("reasoning")
                    )
                    if emitted and first_token_at == 0.0:
                        first_token_at = time.monotonic()
        finished_at = time.monotonic()
        if first_token_at == 0.0:
            raise RuntimeError("stream completed without a content token")
        if completion_tokens == 0:
            # ignore_eos makes this exact for successful requests, even when a
            # runtime omits usage from its final streaming chunk.
            completion_tokens = requested_output_tokens
        return Result(
            started_at,
            finished_at,
            first_token_at - started_at,
            prompt_tokens,
            cached_prompt_tokens,
            0,
            completion_tokens,
            provider=provider,
        )
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace").strip()
        detail = ""
        try:
            payload_error = json.loads(body).get("error") or {}
            metadata = payload_error.get("metadata") or {}
            safe_error = {
                "message": payload_error.get("message"),
                "code": payload_error.get("code"),
                "provider_name": metadata.get("provider_name"),
                "limit_source": metadata.get("limit_source"),
                "raw": metadata.get("raw"),
            }
            detail = json.dumps(
                {key: value for key, value in safe_error.items() if value is not None},
                separators=(",", ":"),
            )[:1000]
        except (AttributeError, json.JSONDecodeError):
            detail = "response body omitted"
        message = f"HTTP {error.code}"
        if detail:
            message = f"{message}: {detail}"
        return Result(started_at, time.monotonic(), 0.0, 0, 0, 0, 0, message)
    except Exception as error:  # noqa: BLE001 - benchmark records all failures
        return Result(started_at, time.monotonic(), 0.0, 0, 0, 0, 0, str(error))


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


def read_sglang_work_metrics(url: str, timeout: float) -> dict[str, float]:
    with urllib.request.urlopen(f"{url.rstrip('/')}/metrics", timeout=timeout) as response:
        body = response.read().decode()
    metrics: dict[str, float] = {}
    for line in body.splitlines():
        if line.startswith("sglang:realtime_tokens_total{"):
            value = float(line.rsplit(" ", 1)[1])
            if 'mode="prefill_cache"' in line:
                metrics["cached_tokens"] = value
            elif 'mode="prefill_compute"' in line:
                metrics["computed_prompt_tokens"] = value
    return metrics


def load_trace_sessions(path: str) -> list[dict[str, object]]:
    sessions = []
    with open(path, encoding="utf-8") as workload:
        for line_number, line in enumerate(workload, start=1):
            if not line.strip():
                continue
            session = json.loads(line)
            messages = session.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError(f"{path}:{line_number}: messages must be a non-empty list")
            sessions.append(session)
    if not sessions:
        raise ValueError(f"{path}: no sessions found")
    return sessions


def namespaced_trace_messages(
    messages: list[dict[str, object]], namespace: str
) -> list[dict[str, object]]:
    copied = [dict(message) for message in messages]
    marker = f"Benchmark replay {namespace}.\n"
    if copied[0].get("role") == "system":
        copied[0]["content"] = marker + str(copied[0].get("content") or "")
    else:
        copied.insert(0, {"role": "system", "content": marker})
    return copied


def trace_request_prefixes(
    session: dict[str, object], namespace: str
) -> list[list[dict[str, object]]]:
    messages = namespaced_trace_messages(session["messages"], namespace)  # type: ignore[arg-type]
    return [
        messages[:index]
        for index, message in enumerate(messages)
        if message.get("role") == "assistant"
        and index > 0
        and messages[index - 1].get("role") == "user"
    ]


def run_level(
    args: argparse.Namespace,
    concurrency: int,
    seconds: float,
    trace_sessions: list[dict[str, object]],
) -> dict[str, object]:
    results: list[Result] = []
    results_lock = threading.Lock()
    samples: list[dict[str, float]] = []
    stop_metrics = threading.Event()

    session_ids = [str(uuid.uuid4()) for _ in range(concurrency)]
    trace_namespace = str(uuid.uuid4())

    def prompt_for_session(index: int) -> str | None:
        if args.prompt_mode == "session-prefix":
            return session_prefix_prompt(args, session_ids[index])
        return None

    warmup_results: list[Result] = []
    if args.prompt_mode == "session-prefix" and args.warm_session_prefixes:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            warmup_results = list(
                executor.map(
                    lambda index: request_once(
                        args, prompt_for_session(index), args.warmup_output_tokens
                    ),
                    range(concurrency),
                )
            )

    try:
        sglang_before = read_sglang_work_metrics(args.base_url, min(args.timeout, 5.0))
    except Exception:
        sglang_before = {}
    deadline = time.monotonic() + seconds

    def worker(index: int) -> None:
        if args.prompt_mode == "agent-trace":
            session_index = index
            while time.monotonic() < deadline and session_index < len(trace_sessions):
                session = trace_sessions[session_index]
                namespace = f"{trace_namespace}-{session_index}"
                previous_prompt_tokens = 0
                for messages in trace_request_prefixes(session, namespace):
                    if time.monotonic() >= deadline:
                        break
                    result = request_once(args, messages=messages)
                    if not result.error:
                        # Each replay prefix grows from the same immutable trace.
                        # The prior rendered prompt is therefore cacheable apart
                        # from a few chat-template generation-marker tokens.
                        result.cacheable_prompt_tokens = min(
                            previous_prompt_tokens, result.prompt_tokens
                        )
                        previous_prompt_tokens = result.prompt_tokens
                    with results_lock:
                        results.append(result)
                session_index += concurrency
            return
        while time.monotonic() < deadline:
            result = request_once(args, prompt_for_session(index))
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
        futures = [executor.submit(worker, index) for index in range(concurrency)]
        concurrent.futures.wait(futures)
    stop_metrics.set()
    monitor_thread.join(timeout=2)
    try:
        sglang_after = read_sglang_work_metrics(args.base_url, min(args.timeout, 5.0))
    except Exception:
        sglang_after = {}

    successful = [result for result in results if not result.error]
    failed = [result for result in results if result.error]
    error_counts = collections.Counter(
        result.error.partition(":")[0] for result in failed
    )
    if not successful:
        return {
            "concurrency": concurrency,
            "requested_seconds": seconds,
            "requests": len(results),
            "successful": 0,
            "errors": len(failed),
            "errors_by_type": dict(sorted(error_counts.items())),
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
    cached_input_tokens = sum(result.cached_prompt_tokens for result in successful)
    cacheable_input_tokens = sum(
        result.cacheable_prompt_tokens for result in successful
    )
    provider_counts: dict[str, int] = {}
    for result in successful:
        if result.provider:
            provider_counts[result.provider] = provider_counts.get(result.provider, 0) + 1
    measured_cached_tokens = max(
        0.0,
        sglang_after.get("cached_tokens", 0.0)
        - sglang_before.get("cached_tokens", 0.0),
    )
    measured_computed_prompt_tokens = max(
        0.0,
        sglang_after.get("computed_prompt_tokens", 0.0)
        - sglang_before.get("computed_prompt_tokens", 0.0),
    )
    measured_prefill_tokens = measured_cached_tokens + measured_computed_prompt_tokens

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
        "errors_by_type": dict(sorted(error_counts.items())),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cacheable_input_tokens": cacheable_input_tokens,
        "workload_cacheable_ratio": round(cacheable_input_tokens / input_tokens, 4)
        if input_tokens
        else 0,
        "reported_cache_hit_ratio": round(cached_input_tokens / input_tokens, 4)
        if input_tokens
        else 0,
        "server_cached_tokens": int(measured_cached_tokens),
        "server_computed_prompt_tokens": int(measured_computed_prompt_tokens),
        "server_cache_hit_ratio": round(measured_cached_tokens / measured_prefill_tokens, 4)
        if measured_prefill_tokens
        else 0,
        "server_cache_metrics_valid": measured_prefill_tokens <= input_tokens * 1.1,
        "output_tokens": output_tokens,
        "providers": provider_counts,
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
        "warmup_requests": len(warmup_results),
        "warmup_errors": sum(1 for result in warmup_results if result.error),
        "trace_sessions_available": len(trace_sessions),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://10.96.0.50:30000")
    parser.add_argument("--desmond-url", default="http://10.96.0.50:9090")
    parser.add_argument("--model", default="google/gemma-4-31B-it")
    parser.add_argument("--provider", default="")
    parser.add_argument("--api-key", default=os.environ.get("SGLANG_API_KEY", ""))
    parser.add_argument("--concurrencies", default="1,2,4,8,16,24")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--sustain-concurrency", type=int, default=0)
    parser.add_argument("--sustain-seconds", type=float, default=120)
    parser.add_argument("--prompt-repetitions", type=int, default=45)
    parser.add_argument(
        "--prompt-mode",
        choices=("unique", "session-prefix", "agent-trace"),
        default="unique",
    )
    parser.add_argument("--trace-workload", default="")
    parser.add_argument("--session-prefix-repetitions", type=int, default=160)
    parser.add_argument("--session-suffix-repetitions", type=int, default=16)
    parser.add_argument(
        "--warm-session-prefixes", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--warmup-output-tokens", type=int, default=1)
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument(
        "--ignore-eos", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--cooldown-seconds", type=float, default=3)
    args = parser.parse_args()
    if not args.api_key:
        parser.error("--api-key or SGLANG_API_KEY is required")
    if args.prompt_mode == "agent-trace" and not args.trace_workload:
        parser.error("--trace-workload is required with --prompt-mode agent-trace")
    return args


def main() -> int:
    args = parse_args()
    levels = [int(value) for value in args.concurrencies.split(",")]
    trace_sessions = load_trace_sessions(args.trace_workload) if args.trace_workload else []
    print(
        json.dumps(
            {
                "benchmark": "started",
                "unix_time": time.time(),
                "levels": levels,
                "prompt_mode": args.prompt_mode,
                "session_prefix_repetitions": args.session_prefix_repetitions,
                "session_suffix_repetitions": args.session_suffix_repetitions,
                "output_tokens": args.output_tokens,
                "provider": args.provider,
                "ignore_eos": args.ignore_eos,
                "trace_workload": args.trace_workload,
                "trace_sessions": len(trace_sessions),
            }
        ),
        flush=True,
    )
    all_results = []
    for concurrency in levels:
        result = run_level(args, concurrency, args.seconds, trace_sessions)
        all_results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
        time.sleep(args.cooldown_seconds)
    if args.sustain_concurrency:
        result = run_level(
            args, args.sustain_concurrency, args.sustain_seconds, trace_sessions
        )
        result["sustained"] = True
        all_results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    print(json.dumps({"benchmark": "finished", "unix_time": time.time(), "results": all_results}))
    return 0 if all(result.get("errors", 0) == 0 for result in all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
