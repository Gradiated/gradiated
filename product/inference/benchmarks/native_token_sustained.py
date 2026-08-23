#!/usr/bin/env python3
"""Replay growing tokenized conversations against the native runtime."""

from __future__ import annotations

import argparse
import concurrent.futures
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
class Result:
    conversation: str
    turn: int
    input_tokens: int
    cached_tokens: int
    output_ids: list[int]
    ttft_ms: float
    mean_tpot_ms: float
    total_ms: float
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


def metrics(base_url: str) -> dict[str, float]:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/metrics", timeout=5) as response:
            body = response.read().decode()
    except Exception:  # noqa: BLE001 - metrics must not invalidate a load run
        return {}
    result: dict[str, float] = {}
    for line in body.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        key, raw = line.rsplit(" ", 1)
        try:
            result[key] = float(raw)
        except ValueError:
            pass
    return result


def request(
    base_url: str,
    api_key: str,
    conversation: str,
    turn: int,
    input_ids: list[int],
    output_tokens: int,
    timeout: float,
) -> Result:
    payload = {"input_ids": input_ids, "max_tokens": output_tokens, "stream": False}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    message = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/token-completions",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(message, timeout=timeout) as response:
            body = json.load(response)
        timing = body["timing"]
        usage = body["usage"]
        return Result(
            conversation=conversation,
            turn=turn,
            input_tokens=int(usage["input_tokens"]),
            cached_tokens=int(usage["cached_input_tokens"]),
            output_ids=[int(token) for token in body["output_ids"]],
            ttft_ms=float(timing["ttft_ms"]),
            mean_tpot_ms=float(timing["mean_tpot_ms"]),
            total_ms=float(timing["total_ms"]),
        )
    except Exception as error:  # noqa: BLE001 - retain every failed request
        return Result(
            conversation, turn, len(input_ids), 0, [], math.nan, math.nan,
            (time.monotonic() - started) * 1000.0, str(error),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--api-key", default=os.environ.get("GRADIATED_RUNTIME_API_KEY", ""))
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--conversations", type=int, default=64)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--suffix-tokens", type=int, default=256)
    parser.add_argument("--output-tokens", type=int, default=64)
    parser.add_argument("--turn-barrier", action="store_true")
    parser.add_argument("--exclude-first-turn", action="store_true")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.concurrency <= 0 or args.conversations <= 0 or args.turns <= 0:
        parser.error("concurrency, conversations and turns must be positive")

    payload = json.loads(args.workload.read_text(encoding="utf-8"))
    prompts = payload["prompts"][args.offset : args.offset + args.conversations]
    if len(prompts) < args.conversations:
        parser.error("workload has fewer prompts than requested conversations")
    before = metrics(args.base_url)
    results: list[Result] = []
    lock = threading.Lock()

    def run_conversation(prompt: dict[str, object]) -> None:
        token_ids = [int(token) for token in prompt["input_ids"]]
        first_length = len(token_ids) - (args.turns - 1) * args.suffix_tokens
        if first_length <= 0:
            raise ValueError(f"prompt {prompt['id']} is too short for turn schedule")
        local: list[Result] = []
        conversation_ids = token_ids[:first_length]
        source_cursor = first_length
        for turn in range(args.turns):
            result = request(
                args.base_url, args.api_key, str(prompt["id"]), turn,
                conversation_ids, args.output_tokens, args.timeout,
            )
            local.append(result)
            if result.error:
                break
            # A live next turn contains the assistant text just generated, followed by new
            # tool/user input. Keeping that exact history makes the previous target KV prefix
            # reusable; replaying the corpus's different recorded assistant text would not.
            conversation_ids = conversation_ids + result.output_ids
            if turn + 1 < args.turns:
                next_cursor = source_cursor + args.suffix_tokens
                conversation_ids.extend(token_ids[source_cursor:next_cursor])
                source_cursor = next_cursor
        with lock:
            results.extend(local)

    started = time.monotonic()
    if args.turn_barrier:
        states = []
        for prompt in prompts:
            token_ids = [int(token) for token in prompt["input_ids"]]
            first_length = len(token_ids) - (args.turns - 1) * args.suffix_tokens
            if first_length <= 0:
                raise ValueError(f"prompt {prompt['id']} is too short for turn schedule")
            states.append({
                "id": str(prompt["id"]),
                "source": token_ids,
                "cursor": first_length,
                "conversation": token_ids[:first_length],
                "failed": False,
            })
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            for turn in range(args.turns):
                if turn == 1 and args.exclude_first_turn:
                    results.clear()
                    before = metrics(args.base_url)
                    started = time.monotonic()
                active = [state for state in states if not state["failed"]]
                turn_results = list(executor.map(
                    lambda state: request(
                        args.base_url, args.api_key, state["id"], turn,
                        state["conversation"], args.output_tokens, args.timeout,
                    ),
                    active,
                ))
                results.extend(turn_results)
                for state, result in zip(active, turn_results, strict=True):
                    if result.error:
                        state["failed"] = True
                        continue
                    state["conversation"].extend(result.output_ids)
                    if turn + 1 < args.turns:
                        next_cursor = state["cursor"] + args.suffix_tokens
                        state["conversation"].extend(
                            state["source"][state["cursor"]:next_cursor]
                        )
                        state["cursor"] = next_cursor
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            list(executor.map(run_conversation, prompts))
    wall_seconds = time.monotonic() - started
    after = metrics(args.base_url)
    results.sort(key=lambda item: (item.conversation, item.turn))
    successful = [item for item in results if not item.error]
    output_count = sum(len(item.output_ids) for item in successful)
    input_count = sum(item.input_tokens for item in successful)
    cached_count = sum(item.cached_tokens for item in successful)

    exact = compared = 0
    if args.baseline:
        baseline_payload = json.loads(args.baseline.read_text(encoding="utf-8"))
        baseline = {
            (item["conversation"], int(item["turn"])): item["output_ids"]
            for item in baseline_payload["results"]
            if not item["error"]
        }
        for item in successful:
            key = (item.conversation, item.turn)
            if key in baseline:
                compared += 1
                exact += item.output_ids == baseline[key]

    metric_deltas = {
        key: value - before.get(key, 0.0)
        for key, value in after.items()
        if key.startswith("gradiated_native_") and key.endswith("_total")
    }
    proposed = metric_deltas.get("gradiated_native_speculative_proposed_tokens_total", 0.0)
    accepted = metric_deltas.get("gradiated_native_speculative_accepted_tokens_total", 0.0)
    summary = {
        "requests": len(results),
        "successful": len(successful),
        "errors": len(results) - len(successful),
        "wall_seconds": round(wall_seconds, 4),
        "output_tokens": output_count,
        "aggregate_output_tps": round(output_count / wall_seconds, 3),
        "input_tokens": input_count,
        "cached_input_tokens": cached_count,
        "cache_ratio": round(cached_count / input_count, 6) if input_count else 0.0,
        "ttft_p50_ms": round(percentile([item.ttft_ms for item in successful], 0.5), 3),
        "ttft_p95_ms": round(percentile([item.ttft_ms for item in successful], 0.95), 3),
        "tpot_p50_ms": round(percentile([item.mean_tpot_ms for item in successful], 0.5), 3),
        "tpot_p95_ms": round(percentile([item.mean_tpot_ms for item in successful], 0.95), 3),
        "request_p50_ms": round(percentile([item.total_ms for item in successful], 0.5), 3),
        "request_p95_ms": round(percentile([item.total_ms for item in successful], 0.95), 3),
        "exact_matches": exact,
        "exact_compared": compared,
        "exact_match_rate": round(exact / compared, 6) if compared else None,
        "speculative_acceptance": round(accepted / proposed, 6) if proposed else None,
        "metric_deltas": metric_deltas,
    }
    result_payload = {"summary": summary, "results": [asdict(item) for item in results]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result_payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
