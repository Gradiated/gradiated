#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from validate_bundle import BundleError, load_and_validate


class ReplayError(ValueError):
    pass


READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read one UTF-8 file now",
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def tokenizer_binding(bundle, fixture_id, request_index=None):
    rows = {row["fixture_id"]: row for row in bundle["tokenizer_bindings"]["bindings"]}
    if fixture_id not in rows:
        fixture = next(
            (row for split in bundle["records"].values() for row in split if row["fixture_id"] == fixture_id),
            None,
        )
        if fixture is not None and fixture["workload_class"] == "fixed_8k_1k":
            return {"input_tokens": 8192, "token_ids_u32le_sha256": None}
        raise ReplayError("request fixture has no frozen tokenizer binding")
    binding = rows[fixture_id]
    if "requests" not in binding:
        if request_index is not None:
            raise ReplayError("append fixture does not accept request_index")
        return binding
    if not isinstance(request_index, int) or not 0 <= request_index < len(binding["requests"]):
        raise ReplayError("prefix fixture requires a valid request_index")
    return binding["requests"][request_index]


def fixture_by_id(bundle, fixture_id):
    fixture = next(
        (row for split in bundle["records"].values() for row in split if row["fixture_id"] == fixture_id),
        None,
    )
    if fixture is None:
        raise ReplayError("request fixture is not frozen")
    return fixture


def materialize_fixture_payload(bundle, fixture_id, request_index=None):
    fixture = fixture_by_id(bundle, fixture_id)
    if fixture["workload_class"] == "fixed_8k_1k":
        return {"kind": "completion_prompt"}
    if fixture["workload_class"] == "agent_append":
        messages = [{"role": "system", "content": fixture["session"]["system"]}]
        for turn in fixture["session"]["turns"]:
            if "tool_call" in turn:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "function": {
                            "name": turn["tool_call"]["name"],
                            "arguments": turn["tool_call"]["arguments"],
                        },
                    }],
                })
            else:
                messages.append({"role": turn["role"], "content": turn["content"]})
        return {"kind": "chat_messages", "messages": messages, "tools": [READ_FILE_TOOL]}
    if not isinstance(request_index, int) or not 0 <= request_index < len(fixture["requests"]):
        raise ReplayError("prefix fixture requires a valid request_index")
    request = fixture["requests"][request_index]
    return {
        "kind": "chat_messages",
        "messages": [
            {"role": "system", "content": fixture["shared_prefix"]["system"]},
            {"role": "user", "content": request["user"]},
        ],
        "tools": fixture["shared_prefix"]["tools"],
    }


def validate_request(bundle, request):
    required = {
        "schema_version", "request_id", "fixture_id", "max_output_tokens",
        "expected_input_tokens", "scheduled_offset_ms",
    }
    optional = {"request_index", "messages", "tools", "prompt"}
    if not isinstance(request, dict) or set(request) - required - optional or not required <= set(request):
        raise ReplayError("request fields are not exact")
    if request["schema_version"] != 1 or not isinstance(request["request_id"], str) or not request["request_id"]:
        raise ReplayError("request identity is invalid")
    if not isinstance(request["max_output_tokens"], int) or request["max_output_tokens"] <= 0:
        raise ReplayError("max_output_tokens is invalid")
    if not isinstance(request["scheduled_offset_ms"], int) or request["scheduled_offset_ms"] < 0:
        raise ReplayError("scheduled offset is invalid")
    binding = tokenizer_binding(bundle, request["fixture_id"], request.get("request_index"))
    if request["expected_input_tokens"] != binding["input_tokens"]:
        raise ReplayError("request input count differs from frozen tokenizer binding")
    result = dict(request)
    expected_payload = materialize_fixture_payload(bundle, request["fixture_id"], request.get("request_index"))
    if expected_payload["kind"] == "completion_prompt":
        if set(request) & {"messages", "tools"} or not isinstance(request.get("prompt"), str) or not request["prompt"]:
            raise ReplayError("fixed length-only request requires one materialized completion prompt")
    else:
        if "prompt" in request or request.get("messages") != expected_payload["messages"] or request.get("tools") != expected_payload["tools"]:
            raise ReplayError("request content differs from the frozen fixture")
    result["api_kind"] = expected_payload["kind"]
    result["token_ids_u32le_sha256"] = binding.get("token_ids_u32le_sha256")
    result["model"] = bundle["tokenizer_bindings"]["model"]
    result["model_revision"] = bundle["tokenizer_bindings"]["resolved_revision"]
    return result


def event_token_count(value):
    for container in [value.get("usage"), value.get("meta_info"), value.get("x_sglang")]:
        if isinstance(container, dict) and "completion_tokens" in container:
            count = container["completion_tokens"]
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                return count
    return None


def measure_openai_stream(request, lines, monotonic_ns=time.monotonic_ns):
    start_ns = monotonic_ns()
    first_token_ns = None
    previous_token_ns = None
    previous_completion_tokens = 0
    itl_ms = []
    finish_reason = None
    final_usage = None
    last_event_ns = start_ns
    done = False
    raw_digest = hashlib.sha256()
    for raw_line in lines:
        if isinstance(raw_line, str):
            raw_line = raw_line.encode()
        raw_digest.update(raw_line)
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(b"data:"):
            raise ReplayError("stream contains a non-SSE data line")
        payload = line[5:].strip()
        if payload == b"[DONE]":
            done = True
            continue
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ReplayError(f"stream contains malformed JSON: {error}") from error
        event_ns = monotonic_ns()
        last_event_ns = event_ns
        if not isinstance(value, dict):
            raise ReplayError("stream event is not an object")
        if "error" in value:
            raise ReplayError(f"server returned a streaming error: {value['error']}")
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ReplayError("stream event must contain exactly one choice")
        choice = choices[0]
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            raise ReplayError("stream choice delta is malformed")
        content = choice.get("text") if isinstance(choice.get("text"), str) else delta.get("content")
        if content:
            if not isinstance(content, str):
                raise ReplayError("stream content delta is not text")
            completion_tokens = event_token_count(value)
            if completion_tokens is None:
                raise ReplayError("per-event completion token counts are required for observable ITL")
            if completion_tokens != previous_completion_tokens + 1:
                raise ReplayError("ITL is unobservable when a stream event does not advance exactly one token")
            if first_token_ns is None:
                first_token_ns = event_ns
            elif previous_token_ns is not None:
                itl_ms.append((event_ns - previous_token_ns) / 1_000_000)
            previous_token_ns = event_ns
            previous_completion_tokens = completion_tokens
        current_finish = choice.get("finish_reason")
        if current_finish is not None:
            if finish_reason is not None or current_finish not in {"stop", "length", "tool_calls"}:
                raise ReplayError("stream finish reason is missing, duplicate, or unsupported")
            finish_reason = current_finish
        usage = value.get("usage")
        if isinstance(usage, dict) and {"prompt_tokens", "completion_tokens"} <= set(usage):
            final_usage = usage
    if not done or finish_reason is None or first_token_ns is None or final_usage is None:
        raise ReplayError("stream is incomplete or lacks finish, token, or usage evidence")
    input_tokens = final_usage.get("prompt_tokens")
    output_tokens = final_usage.get("completion_tokens")
    total_tokens = final_usage.get("total_tokens", input_tokens + output_tokens if isinstance(input_tokens, int) and isinstance(output_tokens, int) else None)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in [input_tokens, output_tokens, total_tokens]):
        raise ReplayError("final usage token counts are invalid")
    if input_tokens != request["expected_input_tokens"]:
        raise ReplayError("server prompt token count differs from frozen tokenizer binding")
    if output_tokens != previous_completion_tokens:
        raise ReplayError("final output token count differs from observed stream")
    if finish_reason == "stop" and output_tokens >= request["max_output_tokens"]:
        raise ReplayError("possible silent truncation: stop at the output-token cap")
    return {
        "schema_version": 1,
        "request_id": request["request_id"],
        "fixture_id": request["fixture_id"],
        "status": "success",
        "latency_ms": {
            "ttft": (first_token_ns - start_ns) / 1_000_000,
            "itl": itl_ms,
            "end_to_end": (last_event_ns - start_ns) / 1_000_000,
        },
        "tokens": {"input": input_tokens, "output": output_tokens, "total": total_tokens},
        "truncation": {"detected": finish_reason == "length", "finish_reason": finish_reason},
        "stream_sha256": raw_digest.hexdigest(),
        "error": None,
    }


def stream_request(base_url, request, timeout_seconds, api_key):
    payload = {
        "model": request["model"],
        "max_tokens": request["max_output_tokens"],
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 470100,
        "stream": True,
        "stream_options": {"include_usage": True, "continuous_usage_stats": True},
    }
    if request["api_kind"] == "completion_prompt":
        payload["prompt"] = request["prompt"]
        endpoint = "/v1/completions"
    else:
        payload["messages"] = request["messages"]
        payload["tools"] = request["tools"]
        endpoint = "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    http_request = urllib.request.Request(
        base_url.rstrip("/") + endpoint,
        data=canonical(payload),
        headers=headers,
        method="POST",
    )

    def lines():
        try:
            with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
                yield from response
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise ReplayError(f"stream transport failed: {type(error).__name__}") from error

    return lines()


def failure_outcome(request, error):
    return {
        "schema_version": 1,
        "request_id": request.get("request_id"),
        "fixture_id": request.get("fixture_id"),
        "status": "error",
        "latency_ms": {"ttft": None, "itl": [], "end_to_end": None},
        "tokens": {"input": None, "output": None, "total": None},
        "truncation": {"detected": None, "finish_reason": None},
        "stream_sha256": None,
        "error": {"type": type(error).__name__, "message": str(error)},
    }


def execute_requests(base_url, requests, max_concurrency, timeout_seconds, api_key):
    origin_ns = time.monotonic_ns()
    lock = threading.Lock()
    outcomes = []

    def execute(request):
        target_ns = origin_ns + request["scheduled_offset_ms"] * 1_000_000
        remaining = (target_ns - time.monotonic_ns()) / 1_000_000_000
        if remaining > 0:
            time.sleep(remaining)
        try:
            return measure_openai_stream(request, stream_request(base_url, request, timeout_seconds, api_key))
        except ReplayError as error:
            return failure_outcome(request, error)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = [executor.submit(execute, request) for request in requests]
        for future in concurrent.futures.as_completed(futures):
            with lock:
                outcomes.append(future.result())
    return sorted(outcomes, key=lambda row: row["request_id"])


def reset_server_cache(base_url, timeout_seconds, api_key):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        base_url.rstrip("/") + "/flush_cache",
        data=b"{}",
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise ReplayError("cache reset returned a non-success status")
            response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise ReplayError(f"cache reset failed: {type(error).__name__}") from error


def load_plan(bundle, path):
    try:
        plan = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayError(f"invalid replay plan: {error}") from error
    if plan.get("schema_version") != 1 or plan.get("bundle_sha256") != bundle["manifest"]["bundle_sha256"]:
        raise ReplayError("replay plan is not bound to the frozen workload bundle")
    profiles = {profile["profile_id"]: profile for profile in bundle["replay_schedule"]["profiles"]}
    profile = profiles.get(plan.get("profile_id"))
    if profile is None:
        raise ReplayError("replay plan profile is not frozen")
    requests = plan.get("requests")
    warmups = plan.get("warmup_requests")
    if not isinstance(requests, list) or len(requests) != profile["request_count"]:
        raise ReplayError("replay plan request count differs from frozen profile")
    if not isinstance(warmups, list) or len(warmups) != profile["warmup"]["request_count"]:
        raise ReplayError("replay plan warmup count differs from frozen profile")
    validated = [validate_request(bundle, request) for request in requests]
    validated_warmups = [validate_request(bundle, request) for request in warmups]
    if plan.get("cache_mode") != profile["cache"]["prefix_cache"]:
        raise ReplayError("replay plan cache mode differs from frozen profile")
    validate_arrival_offsets(profile["arrival"], validated)
    ids = [request["request_id"] for request in validated + validated_warmups]
    if len(ids) != len(set(ids)):
        raise ReplayError("replay request IDs are not unique")
    return profile, validated_warmups, validated


def validate_arrival_offsets(arrival, requests):
    actual = sorted(request["scheduled_offset_ms"] for request in requests)
    kind = arrival["kind"]
    if kind == "closed_loop":
        expected = [0] * len(requests)
    elif kind == "fixed_interval":
        expected = [index * arrival["inter_arrival_ms"] for index in range(len(requests))]
    elif kind == "session_relative":
        expected = sorted(
            session * arrival["session_start_stagger_ms"] + offset
            for session in range(arrival["session_count"])
            for offset in arrival["within_session_offsets_ms"]
        )
    else:
        raise ReplayError("replay arrival kind is unsupported")
    if actual != expected:
        raise ReplayError("request offsets differ from frozen arrival schedule")


def write_jsonl(path, rows):
    Path(path).write_bytes(b"".join(canonical(row) + b"\n" for row in rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-key-env", default="")
    arguments = parser.parse_args()
    try:
        bundle = load_and_validate(arguments.bundle)
        profile, warmups, requests = load_plan(bundle, arguments.plan)
        api_key = os.environ.get(arguments.api_key_env) if arguments.api_key_env else None
        timeout = bundle["replay_schedule"]["timeout"]["per_request_seconds"]
        outcomes = []
        for repetition in range(profile["repetitions"]):
            warmup_outcomes = execute_requests(arguments.base_url, warmups, 1, timeout, api_key)
            if any(row["status"] != "success" or row["truncation"]["detected"] for row in warmup_outcomes):
                raise ReplayError("warmup failed or truncated")
            reset_server_cache(arguments.base_url, timeout, api_key)
            measured = execute_requests(arguments.base_url, requests, profile["max_concurrency"], timeout, api_key)
            for row in measured:
                row["repetition"] = repetition + 1
            outcomes.extend(measured)
        write_jsonl(arguments.output, outcomes)
        if any(row["status"] != "success" or row["truncation"]["detected"] for row in outcomes):
            raise ReplayError("measured profile contains a failure or truncation")
    except (BundleError, ReplayError) as error:
        print(f"INVALID: {error}", file=os.sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
