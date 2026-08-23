#!/usr/bin/env python3
"""Replay a deterministic open-loop token manifest against the native runtime."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import statistics
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA = "gradiated.open-loop-token.v1"


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


def linear_slope(points: list[tuple[float, float]]) -> float:
    """Return the ordinary-least-squares y/x slope, or zero without enough span."""
    if len(points) < 2:
        return 0.0
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    denominator = sum((point[0] - mean_x) ** 2 for point in points)
    if denominator == 0.0:
        return 0.0
    return sum(
        (point[0] - mean_x) * (point[1] - mean_y) for point in points
    ) / denominator


def metrics(base_url: str) -> dict[str, float]:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/metrics", timeout=5) as response:
            body = response.read().decode()
    except Exception:  # noqa: BLE001 - metrics are supporting evidence, not load validity
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


def issue_request(
    event: dict[str, Any],
    base_url: str,
    api_key: str,
    runtime: str,
    timeout: float,
    phase_started: float,
    submitted_at: float,
    scheduled_offset_s: float | None = None,
) -> dict[str, Any]:
    worker_started = time.monotonic()
    if runtime == "native":
        path = "/v1/token-completions"
        payload = {
            "input_ids": event["input_ids"],
            "max_tokens": event["max_tokens"],
            "stream": False,
        }
    else:
        path = "/generate"
        payload = {
            "input_ids": event["input_ids"],
            "sampling_params": {
                "temperature": 0,
                "max_new_tokens": event["max_tokens"],
            },
            "stream": True,
        }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    sent_at = time.monotonic()
    if scheduled_offset_s is None:
        scheduled_offset_s = float(event["scheduled_offset_s"])
    result: dict[str, Any] = {
        "id": event["id"],
        "session_id": event["session_id"],
        "turn": event["turn"],
        "sampling_seed": event["sampling_seed"],
        "scheduled_offset_s": scheduled_offset_s,
        "manifest_scheduled_offset_s": event["scheduled_offset_s"],
        "submit_offset_s": submitted_at - phase_started,
        "worker_offset_s": worker_started - phase_started,
        "send_offset_s": sent_at - phase_started,
        "client_dispatch_ms": (sent_at - phase_started - scheduled_offset_s) * 1000.0,
        "input_tokens": len(event["input_ids"]),
        "expected_prefix_tokens": event["expected_prefix_tokens"],
        "output_ids": [],
        "error": "",
    }
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if runtime == "native":
                body = json.load(response)
                completed_at = time.monotonic()
                timing = body["timing"]
                usage = body["usage"]
                output_ids = [int(token) for token in body["output_ids"]]
                queue_ms = float(timing.get("queue_ms", 0.0))
                ttft_ms = float(timing["ttft_ms"])
                tpot_ms = float(timing["mean_tpot_ms"])
                request_ms = float(timing["total_ms"])
                input_tokens = int(usage["input_tokens"])
                cached_input_tokens = int(usage["cached_input_tokens"])
                finish_reason = str(body.get("finish_reason", ""))
            else:
                first_chunk_at: float | None = None
                body = None
                for raw_line in response:
                    line = raw_line.decode().strip()
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    if first_chunk_at is None:
                        first_chunk_at = time.monotonic()
                    body = json.loads(line[6:])
                completed_at = time.monotonic()
                if body is None or first_chunk_at is None:
                    raise RuntimeError("SGLang stream completed without a token event")
                meta = body["meta_info"]
                output_ids = [int(token) for token in body["output_ids"]]
                queue_ms = float(meta.get("queue_time", 0.0)) * 1000.0
                received_timestamp = meta.get("request_received_ts")
                first_timestamp = meta.get("response_sent_to_client_ts")
                if received_timestamp is not None and first_timestamp is not None:
                    ttft_ms = (float(first_timestamp) - float(received_timestamp)) * 1000.0
                else:
                    ttft_ms = (first_chunk_at - sent_at) * 1000.0
                request_ms = float(
                    meta.get("e2e_latency", completed_at - sent_at)
                ) * 1000.0
                decode_throughput = float(meta.get("decode_throughput", 0.0))
                tpot_ms = 1000.0 / decode_throughput if decode_throughput > 0.0 else 0.0
                input_tokens = int(meta.get("prompt_tokens", len(event["input_ids"])))
                cached_input_tokens = int(meta.get("cached_tokens", 0))
                raw_finish_reason = meta.get("finish_reason", "")
                finish_reason = (
                    str(raw_finish_reason.get("type", ""))
                    if isinstance(raw_finish_reason, dict)
                    else str(raw_finish_reason)
                )
        result.update(
            {
                "completion_offset_s": completed_at - phase_started,
                "client_total_ms": (completed_at - sent_at) * 1000.0,
                "queue_ms": queue_ms,
                "ttft_ms": ttft_ms,
                "tpot_ms": tpot_ms,
                "request_ms": request_ms,
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_input_tokens,
                "output_ids": output_ids,
                "finish_reason": finish_reason,
            }
        )
    except Exception as error:  # noqa: BLE001 - every failed request belongs in the result
        completed_at = time.monotonic()
        result.update(
            {
                "completion_offset_s": completed_at - phase_started,
                "client_total_ms": (completed_at - sent_at) * 1000.0,
                "queue_ms": math.nan,
                "ttft_ms": math.nan,
                "tpot_ms": math.nan,
                "request_ms": math.nan,
                "cached_input_tokens": 0,
                "finish_reason": "error",
                "error": str(error),
            }
        )
    return result


def replay_phase(
    events: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    runtime: str,
    timeout: float,
    workers: int,
) -> tuple[list[dict[str, Any]], float]:
    if not events:
        return [], 0.0
    phase_started = time.monotonic()
    futures: list[concurrent.futures.Future[dict[str, Any]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for event in events:
            deadline = phase_started + float(event["scheduled_offset_s"])
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            submitted_at = time.monotonic()
            futures.append(
                executor.submit(
                    issue_request,
                    event,
                    base_url,
                    api_key,
                    runtime,
                    timeout,
                    phase_started,
                    submitted_at,
                )
            )
        results = [future.result() for future in futures]
    return results, time.monotonic() - phase_started


def replay_live_sessions(
    events: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    runtime: str,
    timeout: float,
    workers: int,
) -> tuple[list[dict[str, Any]], float]:
    """Start sessions open-loop, but preserve causal request/response turns within a session."""
    if not events:
        return [], 0.0
    sessions: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        sessions.setdefault(str(event["session_id"]), []).append(event)
    for session_events in sessions.values():
        session_events.sort(key=lambda event: int(event["turn"]))
        for turn, event in enumerate(session_events):
            if int(event["turn"]) != turn:
                raise ValueError(f"session {event['session_id']} has a non-contiguous turn sequence")

    phase_started = time.monotonic()

    def replay_session(session_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        previous_input: list[int] = []
        previous_output: list[int] = []
        start_offset = float(session_events[0]["session_start_offset_s"])
        deadline = phase_started + start_offset
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        for turn, event in enumerate(session_events):
            if turn:
                deadline = time.monotonic() + float(event["think_time_s"])
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
            scheduled_offset = deadline - phase_started
            submitted_at = time.monotonic()
            request_event = dict(event)
            if turn == 0:
                request_input = [int(token) for token in event["input_ids"]]
                expected_prefix_tokens = 0
            else:
                request_input = previous_input + previous_output + [
                    int(token) for token in event["suffix_ids"]
                ]
                expected_prefix_tokens = len(previous_input) + len(previous_output)
            request_event["input_ids"] = request_input
            request_event["expected_prefix_tokens"] = expected_prefix_tokens
            result = issue_request(
                request_event,
                base_url,
                api_key,
                runtime,
                timeout,
                phase_started,
                submitted_at,
                scheduled_offset,
            )
            results.append(result)
            if result["error"]:
                break
            previous_input = request_input
            previous_output = [int(token) for token in result["output_ids"]]
        return results

    futures: list[concurrent.futures.Future[list[dict[str, Any]]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for session_events in sessions.values():
            futures.append(executor.submit(replay_session, session_events))
        results = [result for future in futures for result in future.result()]
    return results, time.monotonic() - phase_started


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument(
        "--api-key",
        default=os.environ.get(
            "GRADIATED_RUNTIME_API_KEY", os.environ.get("DESMOND_RUNTIME_API_KEY", "")
        ),
    )
    parser.add_argument("--runtime", choices=("native", "sglang"), default="native")
    parser.add_argument("--workers", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--warmup-settle-seconds", type=float, default=1.0)
    parser.add_argument("--steady-start-seconds", type=float, default=30.0)
    parser.add_argument("--slo-ttft-ms", type=float, default=1000.0)
    parser.add_argument("--slo-tpot-ms", type=float, default=25.0)
    parser.add_argument("--slo-request-ms", type=float, default=5000.0)
    parser.add_argument("--cached-input-price-per-million", type=float, default=0.01)
    parser.add_argument("--uncached-input-price-per-million", type=float, default=0.08)
    parser.add_argument("--output-price-per-million", type=float, default=0.35)
    parser.add_argument("--gpu-cost-per-hour", type=float, default=4.50)
    parser.add_argument("--ancillary-cost-per-hour", type=float, default=0.0)
    parser.add_argument("--marketplace-fee-fraction", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    economic_values = (
        args.cached_input_price_per_million,
        args.uncached_input_price_per_million,
        args.output_price_per_million,
        args.gpu_cost_per_hour,
        args.ancillary_cost_per_hour,
    )
    if (
        args.workers <= 0
        or args.timeout <= 0
        or args.warmup_settle_seconds < 0
        or args.steady_start_seconds < 0
        or any(value < 0 for value in economic_values)
        or not 0.0 <= args.marketplace_fee_fraction < 1.0
    ):
        raise SystemExit("worker, timeout, and settle values are invalid")
    raw_manifest = args.manifest.read_bytes()
    manifest = json.loads(raw_manifest)
    if manifest.get("schema") != SCHEMA:
        raise SystemExit("unsupported open-loop manifest schema")
    replay = (
        replay_live_sessions
        if manifest.get("arrival", {}).get("model") == "session-live"
        else replay_phase
    )
    warmup_results, _ = replay(
        manifest["warmup_events"], args.base_url, args.api_key, args.runtime,
        args.timeout, args.workers
    )
    warmup_errors = sum(bool(result["error"]) for result in warmup_results)
    if warmup_errors:
        raise SystemExit(f"{warmup_errors} warmup requests failed")
    if args.warmup_settle_seconds:
        time.sleep(args.warmup_settle_seconds)
    before = metrics(args.base_url)
    results, wall_seconds = replay(
        manifest["events"], args.base_url, args.api_key, args.runtime,
        args.timeout, args.workers
    )
    after = metrics(args.base_url)
    results.sort(key=lambda result: result["id"])
    successful = [result for result in results if not result["error"]]
    output_tokens = sum(len(result["output_ids"]) for result in successful)
    input_tokens = sum(result["input_tokens"] for result in successful)
    cached_tokens = sum(result["cached_input_tokens"] for result in successful)
    slo = [
        result
        for result in successful
        if result["ttft_ms"] <= args.slo_ttft_ms
        and result["tpot_ms"] <= args.slo_tpot_ms
        and result["request_ms"] <= args.slo_request_ms
    ]
    slo_output_tokens = sum(len(result["output_ids"]) for result in slo)
    slo_input_tokens = sum(result["input_tokens"] for result in slo)
    slo_cached_tokens = sum(result["cached_input_tokens"] for result in slo)
    metric_deltas = {
        key: value - before.get(key, 0.0)
        for key, value in after.items()
        if key.startswith("gradiated_native_") and key.endswith("_total")
    }

    def distribution(name: str) -> dict[str, float]:
        values = [float(result[name]) for result in successful]
        return {
            "p50": round(percentile(values, 0.50), 3),
            "p95": round(percentile(values, 0.95), 3),
            "p99": round(percentile(values, 0.99), 3),
        }

    def cohort_summary(cohort: list[dict[str, Any]]) -> dict[str, Any]:
        cohort_slo = [
            result
            for result in cohort
            if result["ttft_ms"] <= args.slo_ttft_ms
            and result["tpot_ms"] <= args.slo_tpot_ms
            and result["request_ms"] <= args.slo_request_ms
        ]

        def cohort_distribution(name: str) -> dict[str, float]:
            values = [float(result[name]) for result in cohort]
            return {
                "p50": round(percentile(values, 0.50), 3),
                "p95": round(percentile(values, 0.95), 3),
                "p99": round(percentile(values, 0.99), 3),
            }

        cohort_input = sum(int(result["input_tokens"]) for result in cohort)
        cohort_cached = sum(int(result["cached_input_tokens"]) for result in cohort)
        return {
            "requests": len(cohort),
            "slo_request_ratio": round(len(cohort_slo) / len(cohort), 6) if cohort else 0.0,
            "cache_ratio": round(cohort_cached / cohort_input, 6) if cohort_input else 0.0,
            "queue_ms": cohort_distribution("queue_ms"),
            "ttft_ms": cohort_distribution("ttft_ms"),
            "tpot_ms": cohort_distribution("tpot_ms"),
            "request_ms": cohort_distribution("request_ms"),
        }

    schedule_span = max(
        (
            float(event.get("session_start_offset_s", event["scheduled_offset_s"]))
            for event in manifest["events"]
        ),
        default=0.0,
    )
    def revenue(cached: int, total_input: int, output: int) -> float:
        uncached = max(0, total_input - cached)
        return (
            cached * args.cached_input_price_per_million
            + uncached * args.uncached_input_price_per_million
            + output * args.output_price_per_million
        ) / 1_000_000.0

    gross_revenue = revenue(cached_tokens, input_tokens, output_tokens)
    slo_gross_revenue = revenue(slo_cached_tokens, slo_input_tokens, slo_output_tokens)
    fee_multiplier = 1.0 - args.marketplace_fee_fraction
    net_revenue = gross_revenue * fee_multiplier
    slo_net_revenue = slo_gross_revenue * fee_multiplier
    total_hourly_cost = args.gpu_cost_per_hour + args.ancillary_cost_per_hour
    hourly_scale = 3600.0 / wall_seconds if wall_seconds else 0.0
    net_revenue_per_hour = net_revenue * hourly_scale
    slo_net_revenue_per_hour = slo_net_revenue * hourly_scale
    economics = {
        "prices_per_million": {
            "cached_input": args.cached_input_price_per_million,
            "uncached_input": args.uncached_input_price_per_million,
            "output": args.output_price_per_million,
        },
        "marketplace_fee_fraction": args.marketplace_fee_fraction,
        "gross_revenue_run": round(gross_revenue, 8),
        "net_revenue_per_hour": round(net_revenue_per_hour, 4),
        "slo_net_revenue_per_hour": round(slo_net_revenue_per_hour, 4),
        "total_cost_per_hour": round(total_hourly_cost, 4),
        "compute_recovery": round(net_revenue_per_hour / total_hourly_cost, 6)
        if total_hourly_cost
        else None,
        "slo_compute_recovery": round(slo_net_revenue_per_hour / total_hourly_cost, 6)
        if total_hourly_cost
        else None,
        "margin_per_hour": round(net_revenue_per_hour - total_hourly_cost, 4),
        "slo_margin_per_hour": round(slo_net_revenue_per_hour - total_hourly_cost, 4),
        "slo_monthly_margin_730h": round(
            (slo_net_revenue_per_hour - total_hourly_cost) * 730.0, 2
        ),
        "cost_per_million_output_tokens": round(
            total_hourly_cost / (output_tokens * hourly_scale / 1_000_000.0), 4
        )
        if output_tokens and hourly_scale
        else None,
    }
    steady_start = min(args.steady_start_seconds, schedule_span)
    steady_seconds = max(0.0, schedule_span - steady_start)
    steady = [
        result
        for result in successful
        if steady_start <= float(result["completion_offset_s"]) <= schedule_span
    ]
    steady_slo = [
        result
        for result in steady
        if result["ttft_ms"] <= args.slo_ttft_ms
        and result["tpot_ms"] <= args.slo_tpot_ms
        and result["request_ms"] <= args.slo_request_ms
    ]

    def cohort_revenue(cohort: list[dict[str, Any]]) -> float:
        cohort_input = sum(int(result["input_tokens"]) for result in cohort)
        cohort_cached = sum(int(result["cached_input_tokens"]) for result in cohort)
        cohort_output = sum(len(result["output_ids"]) for result in cohort)
        return revenue(cohort_cached, cohort_input, cohort_output) * fee_multiplier

    steady_hourly_scale = 3600.0 / steady_seconds if steady_seconds else 0.0
    steady_output_tokens = sum(len(result["output_ids"]) for result in steady)
    steady_slo_output_tokens = sum(len(result["output_ids"]) for result in steady_slo)
    steady_revenue_per_hour = cohort_revenue(steady) * steady_hourly_scale
    steady_slo_revenue_per_hour = cohort_revenue(steady_slo) * steady_hourly_scale

    # A finite overloaded trace can report attractive completion economics while an
    # ever-growing queue is hidden in the post-arrival drain. Session-live traffic needs a
    # separate stationarity signal because later turns are intentionally not submitted until
    # the previous response completes. Track first-turn births and completions at fixed wall
    # clock boundaries so continuation locality cannot disguise starvation of new sessions.
    cold_results = [result for result in successful if int(result["turn"]) == 0]
    session_birth_offsets = [
        float(event.get("session_start_offset_s", event["scheduled_offset_s"]))
        for event in manifest["events"]
        if int(event["turn"]) == 0
    ]

    def count_at_or_before(values: list[float], boundary: float) -> int:
        return sum(value <= boundary for value in values)

    cold_completion_offsets = [float(result["completion_offset_s"]) for result in cold_results]
    births_at_start = count_at_or_before(session_birth_offsets, steady_start)
    births_at_end = count_at_or_before(session_birth_offsets, schedule_span)
    cold_completions_at_start = count_at_or_before(cold_completion_offsets, steady_start)
    cold_completions_at_end = count_at_or_before(cold_completion_offsets, schedule_span)
    backlog_at_start = births_at_start - cold_completions_at_start
    backlog_at_end = births_at_end - cold_completions_at_end
    backlog_change = backlog_at_end - backlog_at_start
    steady_session_births = births_at_end - births_at_start
    steady_session_completions = cold_completions_at_end - cold_completions_at_start
    # Permit ordinary in-flight jitter of two sessions or 5% of steady births. Growth beyond
    # that is evidence of an unstable offered load, not usable steady-state economics.
    backlog_growth_tolerance = max(2, math.ceil(steady_session_births * 0.05))
    cold_queue_points = [
        (float(result["send_offset_s"]), float(result["queue_ms"]))
        for result in cold_results
        if steady_start <= float(result["send_offset_s"]) <= schedule_span
    ]
    request_queue_points = [
        (float(result["send_offset_s"]), float(result["queue_ms"]))
        for result in successful
        if steady_start <= float(result["send_offset_s"]) <= schedule_span
    ]
    live_stability = {
        "session_births": steady_session_births,
        "session_completions": steady_session_completions,
        "session_birth_rps": round(steady_session_births / steady_seconds, 4)
        if steady_seconds
        else 0.0,
        "session_completion_rps": round(steady_session_completions / steady_seconds, 4)
        if steady_seconds
        else 0.0,
        "session_backlog_at_start": backlog_at_start,
        "session_backlog_at_end": backlog_at_end,
        "session_backlog_change": backlog_change,
        "session_backlog_slope_per_s": round(backlog_change / steady_seconds, 6)
        if steady_seconds
        else 0.0,
        "cold_queue_trend_ms_per_s": round(linear_slope(cold_queue_points), 3),
        "request_queue_trend_ms_per_s": round(linear_slope(request_queue_points), 3),
        "post_arrival_drain_seconds": round(max(0.0, wall_seconds - schedule_span), 4),
        "backlog_growth_tolerance": backlog_growth_tolerance,
        "likely_stationary": backlog_change <= backlog_growth_tolerance,
    }
    steady_summary = {
        "start_offset_s": round(steady_start, 4),
        "end_offset_s": round(schedule_span, 4),
        "seconds": round(steady_seconds, 4),
        "requests": len(steady),
        "completed_rps": round(len(steady) / steady_seconds, 4) if steady_seconds else 0.0,
        "output_tps": round(steady_output_tokens / steady_seconds, 3)
        if steady_seconds
        else 0.0,
        "slo_requests": len(steady_slo),
        "slo_request_ratio": round(len(steady_slo) / len(steady), 6) if steady else 0.0,
        "slo_output_tps": round(steady_slo_output_tokens / steady_seconds, 3)
        if steady_seconds
        else 0.0,
        "net_revenue_per_hour": round(steady_revenue_per_hour, 4),
        "slo_net_revenue_per_hour": round(steady_slo_revenue_per_hour, 4),
        "compute_recovery": round(steady_revenue_per_hour / total_hourly_cost, 6)
        if total_hourly_cost
        else None,
        "slo_compute_recovery": round(steady_slo_revenue_per_hour / total_hourly_cost, 6)
        if total_hourly_cost
        else None,
        "margin_per_hour": round(steady_revenue_per_hour - total_hourly_cost, 4),
        "slo_margin_per_hour": round(steady_slo_revenue_per_hour - total_hourly_cost, 4),
        "live_stability": live_stability,
    }
    summary = {
        "requests": len(results),
        "successful": len(successful),
        "errors": len(results) - len(successful),
        "slo_requests": len(slo),
        "slo_request_ratio": round(len(slo) / len(results), 6) if results else 0.0,
        "wall_seconds": round(wall_seconds, 4),
        "schedule_span_seconds": round(schedule_span, 4),
        "offered_rps_realized": round(len(results) / schedule_span, 4) if schedule_span else 0.0,
        "session_start_rps_realized": round(
            len({result["session_id"] for result in results}) / schedule_span, 4
        )
        if schedule_span
        else 0.0,
        "completed_rps": round(len(successful) / wall_seconds, 4) if wall_seconds else 0.0,
        "aggregate_output_tps": round(output_tokens / wall_seconds, 3) if wall_seconds else 0.0,
        "slo_output_tps": round(slo_output_tokens / wall_seconds, 3) if wall_seconds else 0.0,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "cache_ratio": round(cached_tokens / input_tokens, 6) if input_tokens else 0.0,
        "queue_ms": distribution("queue_ms"),
        "ttft_ms": distribution("ttft_ms"),
        "tpot_ms": distribution("tpot_ms"),
        "request_ms": distribution("request_ms"),
        "client_dispatch_ms": distribution("client_dispatch_ms"),
        "cold_starts": cohort_summary(
            [result for result in successful if int(result["turn"]) == 0]
        ),
        "continuations": cohort_summary(
            [result for result in successful if int(result["turn"]) > 0]
        ),
        "steady_window": steady_summary,
        "economics": economics,
        "metric_deltas": metric_deltas,
    }
    payload = {
        "schema": "gradiated.open-loop-result.v1",
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "manifest": str(args.manifest),
        "runtime": args.runtime,
        "slo": {
            "ttft_ms": args.slo_ttft_ms,
            "tpot_ms": args.slo_tpot_ms,
            "request_ms": args.slo_request_ms,
        },
        "summary": summary,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=True))
    dispatch_p99 = summary["client_dispatch_ms"]["p99"]
    return 0 if summary["errors"] == 0 and dispatch_p99 <= 10.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
