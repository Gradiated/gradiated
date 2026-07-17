#!/usr/bin/env python3
"""Semantic-first exact-trace runner for the Gemma 4 online-FP8 endpoint."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import statistics
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:30000"
MODEL = "google/gemma-4-31B-it"
TRACE_SHA256 = "ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68"
METRICS = (
    "prefix_cache_queries", "prefix_cache_hits", "request_queue_time_seconds_sum",
    "request_prefill_time_seconds_sum", "request_decode_time_seconds_sum",
    "time_to_first_token_seconds_sum", "inter_token_latency_seconds_sum",
    "request_time_per_output_token_seconds_sum", "num_requests_running",
    "num_requests_waiting", "gpu_cache_usage_perc",
)
PLANNING_HURDLE_RPS = 0.7170614380702235
CONSERVATIVE_HURDLE_RPS = 1.1583551336753017
PLANNING_GPU_RATE_USD_PER_HOUR = 1.10
PRODUCTION_GPU_RATE_RANGE_USD_PER_HOUR = (1.00, 1.25)


class RunError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    rows = sorted(values)
    return rows[min(len(rows) - 1, max(0, math.ceil(q * len(rows)) - 1))]


def snapshot(path: Path) -> tuple[str, dict[str, float], set[str]]:
    with urllib.request.urlopen(BASE + "/metrics", timeout=30) as response:
        text = response.read().decode(errors="replace")
    path.write_text(text)
    totals = {key: 0.0 for key in METRICS}
    present: set[str] = set()
    for line in text.splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        name, raw = line.rsplit(" ", 1)
        base = name.split("{", 1)[0].removesuffix("_total")
        for key in METRICS:
            if base.endswith(key):
                try:
                    totals[key] += float(raw)
                    present.add(key)
                except ValueError:
                    pass
    return text, totals, present


def delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {key: after[key] - before[key] for key in METRICS}


def stream(body: bytes, stem: str, out: Path, expected_prompt: list[int] | None, expected_output: int) -> dict:
    (out / "requests" / f"{stem}.json").write_bytes(body)
    request = urllib.request.Request(BASE + "/v1/completions", data=body, headers={"Content-Type": "application/json"})
    raw_path = out / "raw" / f"{stem}.sse"
    started_ns = time.time_ns()
    started = time.monotonic()
    first = ended = None
    usage = None
    prompt_ids = None
    output_ids: list[int] = []
    texts: list[str] = []
    event_times: list[float] = []
    finish_reason = None
    try:
        with urllib.request.urlopen(request, timeout=900) as response, raw_path.open("wb") as handle:
            for raw in response:
                handle.write(raw)
                line = raw.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    ended = time.monotonic()
                    break
                value = json.loads(payload)
                if isinstance(value.get("usage"), dict):
                    usage = value["usage"]
                if isinstance(value.get("prompt_token_ids"), list):
                    prompt_ids = value["prompt_token_ids"]
                for choice in value.get("choices") or []:
                    if isinstance(choice.get("prompt_token_ids"), list):
                        prompt_ids = choice["prompt_token_ids"]
                    ids = choice.get("token_ids") or []
                    if ids and (not isinstance(ids, list) or any(not isinstance(token, int) for token in ids)):
                        raise RunError("malformed returned token IDs")
                    output_ids.extend(ids)
                    text = choice.get("text") or ""
                    texts.append(text)
                    if ids or text:
                        now = time.monotonic()
                        first = first or now
                        event_times.append(now)
                    finish_reason = choice.get("finish_reason") or finish_reason
    except urllib.error.HTTPError as error:
        raise RunError(f"HTTP {error.code}: {error.read(4096).decode(errors='replace')}") from error
    if first is None or ended is None or usage is None:
        raise RunError("stream missing first token, terminal, or usage")
    if int(usage.get("completion_tokens", -1)) != expected_output or len(output_ids) != expected_output:
        raise RunError("returned output token count is incomplete")
    if expected_prompt is not None:
        if int(usage.get("prompt_tokens", -1)) != len(expected_prompt):
            raise RunError("server prompt token count differs from submitted prompt")
        if prompt_ids != expected_prompt:
            raise RunError("returned prompt token IDs differ from submitted prompt")
    intervals = [(b - a) * 1000 for a, b in zip(event_times, event_times[1:])]
    text = "".join(texts)
    return {
        "stem": stem, "request_sha256": sha(body), "raw_sha256": sha(raw_path.read_bytes()),
        "raw_bytes": raw_path.stat().st_size, "prompt_token_ids_returned": prompt_ids,
        "prompt_token_ids_match": expected_prompt is None or prompt_ids == expected_prompt,
        "output_token_ids": output_ids, "output_token_ids_sha256": sha(canonical(output_ids)),
        "text": text, "usage": usage, "finish_reason": finish_reason,
        "started_wall_ns": started_ns, "ended_wall_ns": time.time_ns(),
        "ttft_ms": (first - started) * 1000, "end_to_end_ms": (ended - started) * 1000,
        "itl_ms": {"count": len(intervals), "mean": statistics.fmean(intervals) if intervals else None,
                   "p50": percentile(intervals, .5), "p95": percentile(intervals, .95), "p99": percentile(intervals, .99)},
    }


def semantic(out: Path) -> dict:
    cases = [("semantic-17", "Answer with only the number 17.", "17"), ("semantic-blue", "Answer with only the word blue.", "blue")]
    rows = []
    for stem, prompt, expected in cases:
        body = canonical({"model": MODEL, "prompt": prompt, "temperature": 0, "max_tokens": 16,
                          "min_tokens": 16, "ignore_eos": True, "stop": [], "stop_token_ids": [],
                          "stream": True, "stream_options": {"include_usage": True}, "return_token_ids": True})
        row = stream(body, stem, out, None, 16)
        normalized = row["text"].strip().lower()
        ids = row["output_token_ids"]
        row["expected_fragment"] = expected
        row["expected_fragment_present"] = expected in normalized
        row["degenerate"] = len(set(ids)) <= 2 or (ids and max(ids.count(token) for token in set(ids)) / len(ids) > .75)
        row["finite_raw"] = "nan" not in normalized and "inf" not in normalized
        rows.append(row)
    passed = all(row["expected_fragment_present"] and not row["degenerate"] and row["finite_raw"] for row in rows)
    result = {"pass": passed, "cases": rows, "decision": "continue_exact_trace" if passed else "stop_corrupt_online_fp8"}
    atomic_json(out / "semantic-terminal.json", result)
    return result


def group(group: dict, out: Path, mode: str) -> dict:
    name = group["name"]
    concurrency = int(group["concurrency"])
    _, before, p0 = snapshot(out / f"{name}-before-warmup.prom")
    warm_body = canonical(group["warmup"]["request_body"])
    if sha(warm_body) != group["warmup"]["request_body_sha256"]:
        raise RunError("warmup canonical body identity mismatch")
    warm = stream(warm_body, name + "-warmup", out, group["warmup"]["request_body"]["prompt"], 1)
    _, after_warm, p1 = snapshot(out / f"{name}-after-warmup.prom")
    barrier = threading.Barrier(concurrency + 1)
    in_flight = maximum = 0
    lock = threading.Lock()

    def one(item: dict) -> dict:
        nonlocal in_flight, maximum
        body = canonical(item["request_body"])
        if sha(body) != item["request_body_sha256"]:
            raise RunError("scored canonical body identity mismatch")
        barrier.wait(timeout=60)
        with lock:
            in_flight += 1
            maximum = max(maximum, in_flight)
        try:
            return stream(body, item["request_id"], out, item["request_body"]["prompt"], 358)
        finally:
            with lock:
                in_flight -= 1

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one, item) for item in group["scored"]]
        barrier.wait(timeout=60)
        rows = [future.result() for future in futures]
    wall = time.monotonic() - started
    _, after, p2 = snapshot(out / f"{name}-after-scored.prom")
    scored_delta = delta(after_warm, after)
    query = scored_delta["prefix_cache_queries"]
    hits = scored_delta["prefix_cache_hits"]
    prompt_tokens = sum(int(row["usage"]["prompt_tokens"]) for row in rows)
    cache_counters_present = {"prefix_cache_queries", "prefix_cache_hits"}.issubset(p1 & p2)
    if mode == "prefix-off":
        cache_valid = cache_counters_present and query == 0 and hits == 0
    else:
        cache_valid = cache_counters_present and query == concurrency * 4214 and 0 <= hits <= concurrency * 528
    return {
        "name": name, "concurrency": concurrency, "warmup": warm, "rows": rows,
        "wall_seconds": wall, "completed_requests_per_second": concurrency / wall,
        "maximum_simultaneous_in_flight": maximum, "simultaneous_pass": maximum == concurrency,
        "metrics_present": sorted(p0 & p1 & p2), "scored_metrics_delta": scored_delta,
        "realized_cache_read_fraction": hits / prompt_tokens if cache_valid else None,
        "cache_mode": mode, "cache_counter_contract_pass": cache_valid,
        "ttft_ms": {"p50": percentile([r["ttft_ms"] for r in rows], .5), "p95": percentile([r["ttft_ms"] for r in rows], .95)},
    }


def economics(groups: list[dict]) -> dict:
    rows = []
    for group_result in groups:
        rate = float(group_result["completed_requests_per_second"])
        rows.append(
            {
                "name": group_result["name"],
                "completed_requests_per_second": rate,
                "planning_base_hurdle_rps": PLANNING_HURDLE_RPS,
                "conservative_hurdle_rps": CONSERVATIVE_HURDLE_RPS,
                "planning_base_pass": rate > PLANNING_HURDLE_RPS,
                "conservative_pass": rate > CONSERVATIVE_HURDLE_RPS,
                "planning_gpu_cost_per_completed_request_usd": PLANNING_GPU_RATE_USD_PER_HOUR / 3600 / rate,
                "production_gpu_cost_per_completed_request_usd_range": [hourly / 3600 / rate for hourly in PRODUCTION_GPU_RATE_RANGE_USD_PER_HOUR],
            }
        )
    return {
        "planning_gpu_rate_usd_per_hour": PLANNING_GPU_RATE_USD_PER_HOUR,
        "production_gpu_rate_usd_per_hour_range": list(PRODUCTION_GPU_RATE_RANGE_USD_PER_HOUR),
        "profiles": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("baseline", "prefix-on", "prefix-off"), default="baseline")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "requests").mkdir()
    (args.output / "raw").mkdir()
    raw_trace = args.trace.read_bytes()
    if sha(raw_trace) != TRACE_SHA256:
        raise RunError("trace packet hash mismatch")
    packet = json.loads(raw_trace)
    result = {"schema_version": 2, "mode": args.mode, "trace_sha256": TRACE_SHA256,
              "semantic": semantic(args.output), "groups": [], "single_10k": None,
              "economics": None, "complete_request_count": 0, "failure_count": 0,
              "pass": False}
    if not result["semantic"]["pass"]:
        result["failure_count"] = 1
        atomic_json(args.output / "runner-result.json", result)
        return 20
    try:
        groups = packet["primary_groups"] if args.mode == "baseline" else [packet["primary_groups"][-1]]
        # Persist each completed arm before attempting an allocator-sensitive
        # successor: c8/c16 failure must not erase c1/c4 evidence.
        for item in groups:
            try:
                arm = group(item, args.output, args.mode)
                result["groups"].append(arm)
                atomic_json(args.output / f"{arm['name']}-terminal.json", {"pass": arm["simultaneous_pass"] and arm["cache_counter_contract_pass"], "group": arm})
            except Exception as arm_error:
                atomic_json(args.output / f"{item['name']}-terminal.json", {"pass": False, "error": {"type": type(arm_error).__name__, "message": str(arm_error)[:2000]}})
                raise
        if args.mode == "baseline":
            item = packet["separate_10k_stream"]
            body = canonical(item["request_body"])
            if sha(body) != item["request_body_sha256"]:
                raise RunError("10K canonical body identity mismatch")
            try:
                result["single_10k"] = stream(body, item["request_id"], args.output, item["request_body"]["prompt"], 358)
                atomic_json(args.output / "single_10k-terminal.json", {"pass": True, "row": result["single_10k"]})
            except Exception as stream_error:
                atomic_json(args.output / "single_10k-terminal.json", {"pass": False, "error": {"type": type(stream_error).__name__, "message": str(stream_error)[:2000]}})
                raise
        result["useful_gpu_seconds"] = sum(g["wall_seconds"] for g in result["groups"]) + (result["single_10k"]["end_to_end_ms"] / 1000 if result["single_10k"] else 0)
        primary = result["groups"]
        prefill = sum(g["scored_metrics_delta"]["request_prefill_time_seconds_sum"] for g in primary)
        decode = sum(g["scored_metrics_delta"]["request_decode_time_seconds_sum"] for g in primary)
        metric_present = all({"request_prefill_time_seconds_sum", "request_decode_time_seconds_sum"}.issubset(set(g["metrics_present"])) for g in primary)
        share = prefill / (prefill + decode) if metric_present and prefill > 0 and decode >= 0 else None
        result["prefix_trigger"] = {"metric_present": metric_present, "prefill_seconds": prefill, "decode_seconds": decode,
                                    "prefill_wall_share": share, "threshold": .393755,
                                    "trigger": args.mode == "baseline" and share is not None and share >= .393755}
        result["economics"] = economics(result["groups"])
        result["complete_request_count"] = len(result["semantic"]["cases"]) + sum(1 + len(group_result["rows"]) for group_result in result["groups"]) + (1 if result["single_10k"] else 0)
        result["pass"] = all(g["simultaneous_pass"] and g["cache_counter_contract_pass"] for g in primary) and result["single_10k"] is not None if args.mode == "baseline" else all(g["simultaneous_pass"] and g["cache_counter_contract_pass"] for g in primary)
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:2000]}
        result["failure_count"] += 1
    atomic_json(args.output / "runner-result.json", result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
