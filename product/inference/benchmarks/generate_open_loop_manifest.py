#!/usr/bin/env python3
"""Compile tokenized conversations into a deterministic open-loop arrival manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any


SCHEMA = "gradiated.open-loop-token.v1"


def poisson_offsets(rng: random.Random, rate: float, count: int) -> list[float]:
    now = 0.0
    result: list[float] = []
    for _ in range(count):
        now += rng.expovariate(rate)
        result.append(now)
    return result


def mmpp_offsets(
    rng: random.Random,
    mean_rate: float,
    count: int,
    burst_multiplier: float,
    burst_starts_per_second: float,
    mean_burst_seconds: float,
) -> list[float]:
    """Generate a two-state Markov-modulated Poisson process at a fixed mean rate."""
    leave_burst_rate = 1.0 / mean_burst_seconds
    high_probability = burst_starts_per_second / (
        burst_starts_per_second + leave_burst_rate
    )
    low_rate = mean_rate / (
        (1.0 - high_probability) + high_probability * burst_multiplier
    )
    rates = (low_rate, low_rate * burst_multiplier)
    transition_rates = (burst_starts_per_second, leave_burst_rate)
    state = 0
    now = 0.0
    transition_at = rng.expovariate(transition_rates[state])
    arrival_at = rng.expovariate(rates[state])
    result: list[float] = []
    while len(result) < count:
        if transition_at < arrival_at:
            now = transition_at
            state = 1 - state
            transition_at = now + rng.expovariate(transition_rates[state])
            # Exponential arrivals are memoryless after a state transition.
            arrival_at = now + rng.expovariate(rates[state])
            continue
        now = arrival_at
        result.append(now)
        arrival_at = now + rng.expovariate(rates[state])
    return result


def offsets(args: argparse.Namespace, rng: random.Random, count: int) -> list[float]:
    if args.arrival_model == "poisson":
        return poisson_offsets(rng, args.offered_rps, count)
    return mmpp_offsets(
        rng,
        args.offered_rps,
        count,
        args.burst_multiplier,
        args.burst_starts_per_second,
        args.mean_burst_seconds,
    )


def compile_events(
    prompts: list[dict[str, Any]],
    schedule: list[float],
    turns: int,
    suffix_tokens: int,
    output_tokens: int,
    rng: random.Random,
    phase: str,
) -> list[dict[str, Any]]:
    if len(schedule) != len(prompts) * turns:
        raise ValueError("schedule does not cover every conversation turn")
    events: list[dict[str, Any]] = []
    # Round-robin turns keep every prefix lineage ordered while leaving enough other sessions
    # between turns for the previous request to commit its KV cache.
    for turn in range(turns):
        for conversation_index, prompt in enumerate(prompts):
            source = [int(token) for token in prompt["input_ids"]]
            first_length = len(source) - (turns - 1) * suffix_tokens
            if first_length <= 0:
                raise ValueError(
                    f"prompt {prompt['id']} is too short for {turns} turns of "
                    f"{suffix_tokens} suffix tokens"
                )
            input_length = first_length + turn * suffix_tokens
            previous_length = 0 if turn == 0 else input_length - suffix_tokens
            event_index = turn * len(prompts) + conversation_index
            session_id = f"{phase}:{conversation_index}:{prompt['id']}"
            events.append(
                {
                    "id": f"{session_id}:turn-{turn}",
                    "session_id": session_id,
                    "source_id": str(prompt["id"]),
                    "turn": turn,
                    "scheduled_offset_s": round(schedule[event_index], 9),
                    "input_ids": source[:input_length],
                    "max_tokens": output_tokens,
                    "sampling_seed": rng.randrange(0, 2**63),
                    "expected_prefix_tokens": previous_length,
                }
            )
    events.sort(key=lambda event: (event["scheduled_offset_s"], event["id"]))
    return events


def compile_session_events(
    prompts: list[dict[str, Any]],
    starts: list[float],
    turns: int,
    suffix_tokens: int,
    output_tokens: int,
    think_time_median_seconds: float,
    think_time_log_sigma: float,
    rng: random.Random,
    session_prefix: str,
) -> list[dict[str, Any]]:
    if len(prompts) != len(starts):
        raise ValueError("session starts do not match prompts")
    events: list[dict[str, Any]] = []
    for conversation_index, (prompt, start) in enumerate(zip(prompts, starts, strict=True)):
        source = [int(token) for token in prompt["input_ids"]]
        first_length = len(source) - (turns - 1) * suffix_tokens
        if first_length <= 0:
            raise ValueError(
                f"prompt {prompt['id']} is too short for {turns} turns of "
                f"{suffix_tokens} suffix tokens"
            )
        session_id = f"{session_prefix}:{conversation_index}:{prompt['id']}"
        scheduled = start
        for turn in range(turns):
            input_length = first_length + turn * suffix_tokens
            events.append(
                {
                    "id": f"{session_id}:turn-{turn}",
                    "session_id": session_id,
                    "source_id": str(prompt["id"]),
                    "turn": turn,
                    "scheduled_offset_s": scheduled,
                    "input_ids": source[:input_length],
                    "max_tokens": output_tokens,
                    "sampling_seed": rng.randrange(0, 2**63),
                    "expected_prefix_tokens": 0 if turn == 0 else input_length - suffix_tokens,
                }
            )
            if turn + 1 < turns:
                scheduled += rng.lognormvariate(
                    math.log(think_time_median_seconds), think_time_log_sigma
                )
    return events


def compile_live_session_events(
    prompts: list[dict[str, Any]],
    starts: list[float],
    turns: int,
    suffix_tokens: int,
    output_tokens: int,
    think_time_median_seconds: float,
    think_time_log_sigma: float,
    rng: random.Random,
    session_prefix: str,
) -> list[dict[str, Any]]:
    """Compile open-loop session starts with closed-loop turns inside each session."""
    if len(prompts) != len(starts):
        raise ValueError("session starts do not match prompts")
    events: list[dict[str, Any]] = []
    for conversation_index, (prompt, start) in enumerate(zip(prompts, starts, strict=True)):
        source = [int(token) for token in prompt["input_ids"]]
        first_length = len(source) - (turns - 1) * suffix_tokens
        if first_length <= 0:
            raise ValueError(
                f"prompt {prompt['id']} is too short for {turns} turns of "
                f"{suffix_tokens} suffix tokens"
            )
        session_id = f"{session_prefix}:{conversation_index}:{prompt['id']}"
        predecessor_id: str | None = None
        for turn in range(turns):
            source_input_length = first_length + turn * suffix_tokens
            nominal_input_length = first_length + turn * (suffix_tokens + output_tokens)
            event_id = f"{session_id}:turn-{turn}"
            think_time = 0.0 if turn == 0 else rng.lognormvariate(
                math.log(think_time_median_seconds), think_time_log_sigma
            )
            events.append(
                {
                    "id": event_id,
                    "session_id": session_id,
                    "source_id": str(prompt["id"]),
                    "turn": turn,
                    # Only the first turn has an absolute arrival. Later turns are released
                    # after their predecessor completes plus this event's think time.
                    "scheduled_offset_s": round(start, 9),
                    "session_start_offset_s": round(start, 9),
                    "predecessor_id": predecessor_id,
                    "think_time_s": round(think_time, 9),
                    # Turn zero is complete. Later requests are assembled by the live driver
                    # from the previous request, its actual output, and this traced suffix.
                    "input_ids": source[:first_length] if turn == 0 else [],
                    "suffix_ids": []
                    if turn == 0
                    else source[source_input_length - suffix_tokens : source_input_length],
                    "expected_input_tokens": nominal_input_length,
                    "max_tokens": output_tokens,
                    "sampling_seed": rng.randrange(0, 2**63),
                    "expected_prefix_tokens": 0
                    if turn == 0
                    else nominal_input_length - suffix_tokens,
                }
            )
            predecessor_id = event_id
    events.sort(key=lambda event: (event["session_start_offset_s"], event["turn"], event["id"]))
    return events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument(
        "--arrival-model",
        choices=("poisson", "mmpp", "session-poisson", "session-live"),
        default="poisson",
    )
    parser.add_argument("--offered-rps", type=float, required=True)
    parser.add_argument("--conversations", type=int, default=16)
    parser.add_argument("--warmup-conversations", type=int, default=4)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--suffix-tokens", type=int, default=64)
    parser.add_argument("--output-tokens", type=int, default=64)
    parser.add_argument("--maximum-context", type=int, default=8192)
    parser.add_argument("--burst-multiplier", type=float, default=5.0)
    parser.add_argument("--burst-starts-per-second", type=float, default=0.05)
    parser.add_argument("--mean-burst-seconds", type=float, default=3.0)
    parser.add_argument("--warmup-seconds", type=float, default=30.0)
    parser.add_argument("--think-time-median-seconds", type=float, default=2.0)
    parser.add_argument("--think-time-log-sigma", type=float, default=0.8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.offered_rps <= 0
        or args.conversations <= 0
        or args.warmup_conversations < 0
        or args.turns <= 0
        or args.suffix_tokens <= 0
        or args.output_tokens <= 0
        or args.maximum_context <= 0
        or args.burst_multiplier < 1.0
        or args.burst_starts_per_second <= 0
        or args.mean_burst_seconds <= 0
        or args.warmup_seconds <= 0
        or args.think_time_median_seconds <= 0
        or args.think_time_log_sigma < 0
    ):
        raise SystemExit("arrival and workload dimensions must be positive")

    raw = args.workload.read_bytes()
    workload = json.loads(raw)
    prompts = [
        prompt
        for prompt in workload["prompts"]
        if len(prompt["input_ids"]) + (args.turns - 1) * args.output_tokens
        <= args.maximum_context
    ]
    required = args.warmup_conversations + args.conversations
    if len(prompts) < required:
        raise SystemExit(
            f"workload has {len(prompts)} prompts that remain within the "
            f"{args.maximum_context}-token causal context; {required} are required"
        )
    rng = random.Random(args.seed)
    warmup_prompts = prompts[: args.warmup_conversations]
    measured_prompts = prompts[args.warmup_conversations : required]
    if args.arrival_model == "session-live":
        session_start_rate = args.offered_rps / args.turns
        warmup_starts = poisson_offsets(rng, session_start_rate, len(warmup_prompts))
        measured_starts = poisson_offsets(rng, session_start_rate, len(measured_prompts))
        warmup_events = compile_live_session_events(
            warmup_prompts,
            warmup_starts,
            args.turns,
            args.suffix_tokens,
            args.output_tokens,
            args.think_time_median_seconds,
            args.think_time_log_sigma,
            rng,
            "warmup",
        )
        events = compile_live_session_events(
            measured_prompts,
            measured_starts,
            args.turns,
            args.suffix_tokens,
            args.output_tokens,
            args.think_time_median_seconds,
            args.think_time_log_sigma,
            rng,
            "measure",
        )
    elif args.arrival_model == "session-poisson":
        warmup_starts = sorted(
            rng.uniform(-args.warmup_seconds, 0.0) for _ in warmup_prompts
        )
        session_start_rate = args.offered_rps / args.turns
        measured_starts = poisson_offsets(rng, session_start_rate, len(measured_prompts))
        all_events = compile_session_events(
            warmup_prompts,
            warmup_starts,
            args.turns,
            args.suffix_tokens,
            args.output_tokens,
            args.think_time_median_seconds,
            args.think_time_log_sigma,
            rng,
            "prewarm",
        ) + compile_session_events(
            measured_prompts,
            measured_starts,
            args.turns,
            args.suffix_tokens,
            args.output_tokens,
            args.think_time_median_seconds,
            args.think_time_log_sigma,
            rng,
            "measure",
        )
        warmup_events = [event for event in all_events if event["scheduled_offset_s"] < 0.0]
        events = [event for event in all_events if event["scheduled_offset_s"] >= 0.0]
        warmup_origin = min(
            (float(event["scheduled_offset_s"]) for event in warmup_events), default=0.0
        )
        for event in warmup_events:
            event["scheduled_offset_s"] = round(
                float(event["scheduled_offset_s"]) - warmup_origin, 9
            )
        for event in events:
            event["scheduled_offset_s"] = round(float(event["scheduled_offset_s"]), 9)
        warmup_events.sort(key=lambda event: (event["scheduled_offset_s"], event["id"]))
        events.sort(key=lambda event: (event["scheduled_offset_s"], event["id"]))
    else:
        warmup_schedule = offsets(args, rng, len(warmup_prompts) * args.turns)
        measured_schedule = offsets(args, rng, len(measured_prompts) * args.turns)
        warmup_events = compile_events(
            warmup_prompts,
            warmup_schedule,
            args.turns,
            args.suffix_tokens,
            args.output_tokens,
            rng,
            "warmup",
        )
        events = compile_events(
            measured_prompts,
            measured_schedule,
            args.turns,
            args.suffix_tokens,
            args.output_tokens,
            rng,
            "measure",
        )
    expected_input = sum(
        int(event.get("expected_input_tokens", len(event["input_ids"]))) for event in events
    )
    expected_cached = sum(event["expected_prefix_tokens"] for event in events)
    payload = {
        "schema": SCHEMA,
        "seed": args.seed,
        "source": {
            "path": str(args.workload),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "arrival": {
            "model": args.arrival_model,
            "offered_rps": args.offered_rps,
            "burst_multiplier": args.burst_multiplier,
            "burst_starts_per_second": args.burst_starts_per_second,
            "mean_burst_seconds": args.mean_burst_seconds,
            "warmup_seconds": args.warmup_seconds,
            "think_time_median_seconds": args.think_time_median_seconds,
            "think_time_log_sigma": args.think_time_log_sigma,
        },
        "workload": {
            "conversations": args.conversations,
            "warmup_conversations": args.warmup_conversations,
            "turns": args.turns,
            "suffix_tokens": args.suffix_tokens,
            "output_tokens": args.output_tokens,
            "maximum_context": args.maximum_context,
            "expected_cacheable_ratio": (
                expected_cached / expected_input if expected_input else 0.0
            ),
        },
        "warmup_events": warmup_events,
        "events": events,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    span = max(
        (
            float(event.get("session_start_offset_s", event["scheduled_offset_s"]))
            for event in events
        ),
        default=0.0,
    )
    realized = len(events) / span if span > 0 else math.nan
    sessions = len({event["session_id"] for event in events})
    print(
        json.dumps(
            {
                "events": len(events),
                "warmup_events": len(warmup_events),
                "schedule_span_s": round(span, 3),
                "realized_offered_rps": round(realized, 3),
                "realized_session_start_rps": round(sessions / span, 3)
                if span > 0
                else math.nan,
                "expected_cacheable_ratio": round(
                    payload["workload"]["expected_cacheable_ratio"], 6
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
