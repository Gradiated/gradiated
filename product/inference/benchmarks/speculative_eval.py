#!/usr/bin/env python3
"""Correctness and latency evaluation for speculative OpenAI runtimes."""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import json
import math
import os
import statistics
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Generation:
    request_id: str
    text: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    ttft_seconds: float
    latency_seconds: float
    error: str = ""


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return math.nan
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def load_sessions(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def request_prefixes(
    session: dict[str, object], max_turns: int
) -> list[tuple[str, list[dict[str, object]]]]:
    messages = session["messages"]
    assert isinstance(messages, list)
    prefixes = [
        (f"{session['session_id']}:{index}", messages[:index])
        for index, message in enumerate(messages)
        if isinstance(message, dict)
        and message.get("role") == "assistant"
        and index > 0
    ]
    return prefixes[-max_turns:] if max_turns else prefixes


def read_metrics(base_url: str) -> dict[str, float]:
    try:
        with urllib.request.urlopen(
            f"{base_url.rstrip('/')}/metrics", timeout=5
        ) as response:
            body = response.read().decode()
    except Exception:
        return {}
    metrics: dict[str, float] = {}
    for line in body.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        key, raw_value = line.rsplit(" ", 1)
        name = key.split("{", 1)[0]
        if any(fragment in name.lower() for fragment in ("spec", "draft", "accept")):
            try:
                metrics[key] = float(raw_value)
            except ValueError:
                pass
    return metrics


def generate(
    args: argparse.Namespace,
    request_id: str,
    messages: list[dict[str, object]],
) -> Generation:
    payload = {
        "model": args.model,
        "messages": messages,
        "max_tokens": args.output_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if args.ignore_eos:
        payload["ignore_eos"] = True
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {args.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    first_token = 0.0
    chunks: list[str] = []
    prompt_tokens = cached_tokens = completion_tokens = 0
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            for raw_line in response:
                line = raw_line.decode(errors="replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                usage = chunk.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens") or prompt_tokens)
                completion_tokens = int(
                    usage.get("completion_tokens") or completion_tokens
                )
                details = usage.get("prompt_tokens_details") or {}
                cached_tokens = int(details.get("cached_tokens") or cached_tokens)
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or delta.get("reasoning_content") or ""
                    if text:
                        if not first_token:
                            first_token = time.monotonic()
                        chunks.append(text)
        finished = time.monotonic()
        return Generation(
            request_id=request_id,
            text="".join(chunks),
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
            ttft_seconds=first_token - started if first_token else math.nan,
            latency_seconds=finished - started,
        )
    except Exception as error:  # noqa: BLE001 - preserve failures in results
        return Generation(request_id, "", 0, 0, 0, math.nan, time.monotonic() - started, str(error))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--model", default="google/gemma-4-31B-it")
    parser.add_argument("--api-key", default=os.environ.get("SGLANG_API_KEY", ""))
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--max-turns-per-session", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--ignore-eos", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.api_key:
        parser.error("--api-key or SGLANG_API_KEY is required")

    sessions = load_sessions(args.workload)
    before = read_metrics(args.base_url)
    results: list[Generation] = []
    lock = threading.Lock()

    def run_session(session: dict[str, object]) -> None:
        local_results = [
            generate(args, request_id, messages)
            for request_id, messages in request_prefixes(
                session, args.max_turns_per_session
            )
        ]
        with lock:
            results.extend(local_results)

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        list(executor.map(run_session, sessions))
    wall_seconds = time.monotonic() - started
    after = read_metrics(args.base_url)
    results.sort(key=lambda result: result.request_id)

    baseline: dict[str, str] = {}
    if args.baseline:
        with args.baseline.open(encoding="utf-8") as stream:
            baseline_payload = json.load(stream)
        baseline = {
            item["request_id"]: item["text"] for item in baseline_payload["generations"]
        }
    comparable = [result for result in results if result.request_id in baseline]
    exact = sum(result.text == baseline[result.request_id] for result in comparable)
    similarity_scores = [
        difflib.SequenceMatcher(
            None, baseline[result.request_id], result.text, autojunk=False
        ).ratio()
        for result in comparable
    ]
    successful = [result for result in results if not result.error]
    ttfts = [result.ttft_seconds for result in successful]
    latencies = [result.latency_seconds for result in successful]
    output_tokens = sum(result.completion_tokens for result in successful)
    summary = {
        "sessions": len(sessions),
        "requests": len(results),
        "successful": len(successful),
        "errors": len(results) - len(successful),
        "wall_seconds": round(wall_seconds, 3),
        "aggregate_output_tps": round(output_tokens / wall_seconds, 2),
        "ttft_p50_seconds": round(percentile(ttfts, 0.5), 4),
        "ttft_p95_seconds": round(percentile(ttfts, 0.95), 4),
        "latency_p50_seconds": round(percentile(latencies, 0.5), 4),
        "latency_p95_seconds": round(percentile(latencies, 0.95), 4),
        "exact_matches": exact,
        "exact_compared": len(comparable),
        "exact_match_rate": round(exact / len(comparable), 6) if comparable else None,
        "text_similarity_mean": round(statistics.fmean(similarity_scores), 6)
        if similarity_scores
        else None,
        "text_similarity_p05": round(percentile(similarity_scores, 0.05), 6)
        if similarity_scores
        else None,
        "mean_completion_tokens": round(
            statistics.fmean(result.completion_tokens for result in successful), 2
        ) if successful else 0,
        "speculative_metric_deltas": {
            key: after[key] - before.get(key, 0.0)
            for key in after
            if key.endswith("_total") or "_total{" in key
        },
        "speculative_metric_values": {
            key: value
            for key, value in after.items()
            if not (key.endswith("_total") or "_total{" in key)
        },
    }
    payload = {
        "summary": summary,
        "generations": [asdict(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
