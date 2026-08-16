#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from cache_on_smoke_packet import evaluate_smoke, metric_totals
from v2_replay_contract import PROJECT, canonical, request_payload, validate_v2_plan


WORKLOADS = PROJECT.parents[2] / "campaign_100" / "workloads"
sys.path.insert(0, str(WORKLOADS))

from replay_api import ReplayError, measure_openai_stream


def usage_cached_tokens(usage):
    details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else None
    value = details.get("cached_tokens") if isinstance(details, dict) else None
    return value if isinstance(value, int) and value >= 0 else None


def evaluate_repetitions(repetitions):
    failures = []
    sequences = []
    for rows in repetitions:
        rows = sorted(rows, key=lambda row: row.get("request_id", ""))
        sequences.append([(row.get("request_id"), row.get("stream_sha256")) for row in rows])
        for row in rows:
            if row.get("status") != "success":
                failures.append("request_success")
            if usage_cached_tokens(row.get("usage")) is None:
                failures.append("prompt_tokens_details.cached_tokens")
            salt = row.get("cache_salt")
            if not isinstance(salt, str) or len(salt) != 64:
                failures.append("cache_salt")
    semantic_repeat_pass = len(sequences) >= 2 and all(sequence == sequences[0] for sequence in sequences[1:])
    if not semantic_repeat_pass:
        failures.append("semantic_output_digest_identity")
    return {
        "pass": not failures,
        "failures": sorted(set(failures)),
        "semantic_repeat_pass": semantic_repeat_pass,
        "digest_sequences": sequences,
    }


def get_metrics(base_url):
    with urllib.request.urlopen(base_url.rstrip("/") + "/metrics", timeout=30) as response:
        return response.read().decode()


def flush_cache(base_url):
    request = urllib.request.Request(base_url.rstrip("/") + "/flush_cache", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        if not 200 <= response.status < 300:
            raise ReplayError("cache reset returned a non-success status")
        response.read()


def stream_lines(base_url, row, timeout):
    payload = request_payload(row)
    request = urllib.request.Request(base_url.rstrip("/") + "/v1/chat/completions", data=canonical(payload), headers={"Content-Type": "application/json"}, method="POST")
    captured = []

    def lines():
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                for raw in response:
                    captured.append(raw)
                    yield raw
        except urllib.error.HTTPError as error:
            raise ReplayError(f"stream transport failed: HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ReplayError(f"stream transport failed: {type(error).__name__}") from error

    return payload, captured, lines()


def final_usage(captured):
    usage = None
    for raw in captured:
        line = raw.strip()
        if not line.startswith(b"data:"):
            continue
        data = line[5:].strip()
        if data == b"[DONE]":
            continue
        try:
            value = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("usage"), dict):
            usage = value["usage"]
    return usage


def execute_one(base_url, row, origin_ns, timeout):
    target = origin_ns + row["scheduled_offset_ms"] * 1_000_000
    remaining = (target - time.monotonic_ns()) / 1_000_000_000
    if remaining > 0:
        time.sleep(remaining)
    try:
        payload, captured, lines = stream_lines(base_url, row, timeout)
        measured = measure_openai_stream({**row, "api_kind": "chat_messages", "model": row.get("served_model_name", "glm-4.7-flash-awq"), "length_finish_is_expected": False}, lines)
        usage = final_usage(captured)
        return {
            **measured,
            "cache_salt": row["cache_salt"],
            "session_index": row["session_index"],
            "payload_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
            "usage": usage,
        }
    except ReplayError as error:
        return {
            "request_id": row["request_id"], "status": "error", "cache_salt": row["cache_salt"],
            "session_index": row["session_index"], "usage": None, "stream_sha256": None,
            "error": {"type": type(error).__name__, "message": str(error)},
        }


def execute_rows(base_url, rows, concurrency, timeout):
    origin = time.monotonic_ns()
    lock = threading.Lock()
    outcomes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(execute_one, base_url, row, origin, timeout) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            with lock:
                outcomes.append(future.result())
    return sorted(outcomes, key=lambda row: row["request_id"])


def write_jsonl(path, rows):
    Path(path).write_bytes(b"".join(canonical(row) + b"\n" for row in rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--plan", default=str(PROJECT / "artifacts" / "agent_prefix_c8_v2_tenant_isolated.plan.json"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    arguments = parser.parse_args()
    plan = validate_v2_plan(json.loads(Path(arguments.plan).read_text()))
    if arguments.repetitions != 2:
        raise SystemExit("INVALID: smoke requires exactly two deterministic repetitions")
    output = Path(arguments.output)
    output.mkdir(parents=True, exist_ok=True)
    all_repetitions = []
    smoke_evaluations = []
    for repetition in range(1, arguments.repetitions + 1):
        warmup = execute_rows(arguments.base_url, plan["requests"][:3], 1, 180)
        write_jsonl(output / f"warmup-r{repetition}.jsonl", warmup)
        if any(row["status"] != "success" for row in warmup):
            raise SystemExit("INVALID: warmup failed")
        flush_cache(arguments.base_url)
        before_text = get_metrics(arguments.base_url)
        (output / f"metrics-r{repetition}-before.prom").write_text(before_text)
        rows = execute_rows(arguments.base_url, plan["requests"], 8, 180)
        write_jsonl(output / f"outcomes-r{repetition}.jsonl", rows)
        after_text = get_metrics(arguments.base_url)
        (output / f"metrics-r{repetition}-after.prom").write_text(after_text)
        evaluation = evaluate_smoke(metric_totals(before_text), metric_totals(after_text), rows)
        (output / f"evaluation-r{repetition}.json").write_bytes(json.dumps(evaluation, indent=2, sort_keys=True).encode() + b"\n")
        all_repetitions.append(rows)
        smoke_evaluations.append(evaluation)
    repeat = evaluate_repetitions(all_repetitions)
    result = {"schema_version": 1, "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(), "smoke_evaluations": smoke_evaluations, "repeat": repeat, "pass": all(row["pass"] for row in smoke_evaluations) and repeat["pass"]}
    (output / "result.json").write_bytes(json.dumps(result, indent=2, sort_keys=True).encode() + b"\n")
    if not result["pass"]:
        raise SystemExit("INVALID: cache-on smoke did not meet its evidence gate")


if __name__ == "__main__":
    main()
