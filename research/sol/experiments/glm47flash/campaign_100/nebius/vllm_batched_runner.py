#!/usr/bin/env python3
"""Conditional semantic, quality, and fixed-geometry vLLM measurement batch."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "glm-4.7-flash-awq"
BASE_URL = "http://127.0.0.1:30000"
EXPECTED_JSON = {"alpha": 17, "beta": "smoke"}
BF16_C8_TOK_S = 305.0449
L40S_HOURLY_USD = 0.8484 + 0.0097222


class BatchError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise BatchError("percentile requires observations")
    rows = sorted(values)
    index = max(0, min(len(rows) - 1, math.ceil(quantile * len(rows)) - 1))
    return rows[index]


def post_json(endpoint: str, payload: dict, timeout: int = 300) -> tuple[dict, str]:
    request = urllib.request.Request(
        BASE_URL + endpoint,
        data=canonical(payload),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read(1024).decode(errors="replace")
        raise BatchError(f"HTTP {error.code}: {detail}") from error
    value = json.loads(raw)
    if not isinstance(value, dict) or "error" in value:
        raise BatchError("endpoint returned an error or non-object")
    return value, hashlib.sha256(raw).hexdigest()


def parse_json_content(content: str) -> object:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]).strip()
    return json.loads(text)


def semantic_smoke(output: Path) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": 'Return only this JSON object: {"alpha": 17, "beta": "smoke"}'}],
        "temperature": 0,
        "max_tokens": 64,
        "seed": 20260713,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    responses = []
    hashes = []
    for index in (1, 2):
        response, digest = post_json("/v1/chat/completions", payload)
        (output / f"semantic-response-{index}.json").write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
        responses.append(response)
        hashes.append(digest)
    messages = [row["choices"][0]["message"] for row in responses]
    normalized = [{key: row.get(key) for key in ("content", "reasoning_content", "tool_calls")} for row in messages]
    parsed = [parse_json_content(str(row.get("content") or "")) for row in messages]
    result = {
        "exact_normalized_identity": normalized[0] == normalized[1],
        "semantic_json_pass": all(row == EXPECTED_JSON for row in parsed),
        "expected": EXPECTED_JSON,
        "raw_response_sha256": hashes,
        "usage": [row.get("usage") for row in responses],
    }
    result["pass"] = result["exact_normalized_identity"] and result["semantic_json_pass"]
    (output / "semantic-determinism.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if not result["pass"]:
        raise BatchError("stock vLLM semantic/determinism gate failed")
    return result


def messages_for_case(case: dict) -> list[dict]:
    if case["category"] == "long_context_retrieval":
        content = case["synthetic_context"] + "\n\n" + case["prompt"]
        return [{"role": "user", "content": content}]
    if case["category"] == "multi_turn_continuation":
        return case["history"] + [{"role": "user", "content": case["prompt"]}]
    return [{"role": "user", "content": case["prompt"]}]


def chat_quality(case: dict) -> tuple[str, list[str]]:
    payload = {
        "model": MODEL,
        "messages": messages_for_case(case),
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 256,
        "seed": 470200,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    repetitions = int(case.get("deterministic_repetitions", 1))
    outputs, hashes = [], []
    for _ in range(repetitions):
        response, digest = post_json("/v1/chat/completions", payload)
        choice = response["choices"][0]
        if choice.get("finish_reason") == "length":
            raise BatchError(f"quality response truncated: {case['case_id']}")
        message = choice["message"]
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        if content is None and isinstance(tool_calls, list) and len(tool_calls) == 1:
            function = tool_calls[0].get("function", {})
            arguments = json.loads(function.get("arguments", ""))
            content = json.dumps({"name": function.get("name"), "arguments": arguments}, sort_keys=True, separators=(",", ":"))
        if not isinstance(content, str):
            raise BatchError(f"quality response lacks content: {case['case_id']}")
        outputs.append(content)
        hashes.append(digest)
    if len(set(outputs)) != 1:
        raise BatchError(f"quality response nondeterministic: {case['case_id']}")
    return outputs[0], hashes


def extract_teacher_forced_logprobs(response: dict, minimum_scored_tokens: int) -> list[dict]:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise BatchError("vLLM completion choice evidence is missing")
    token_ids = choices[0].get("prompt_token_ids")
    rows = choices[0].get("prompt_logprobs")
    if not isinstance(token_ids, list) or not isinstance(rows, list) or len(token_ids) != len(rows):
        raise BatchError("vLLM prompt-logprob evidence is missing or misaligned")
    values = []
    for token_id, row in zip(token_ids, rows):
        if row is None:
            continue
        if not isinstance(row, dict):
            raise BatchError("vLLM prompt-logprob row is malformed")
        item = row.get(str(token_id), row.get(token_id))
        if isinstance(item, dict):
            logprob = item.get("logprob")
        elif isinstance(item, (int, float)):
            logprob = item
        else:
            raise BatchError("actual prompt token is absent from vLLM prompt-logprobs")
        values.append({"logprob": float(logprob), "token_id": int(token_id)})
    if len(values) < minimum_scored_tokens:
        raise BatchError("too few teacher-forced tokens")
    return values


def teacher_forced_quality(case: dict) -> tuple[dict, str]:
    payload = {
        "model": MODEL,
        "prompt": case["teacher_forced_text"],
        "temperature": 0,
        "max_tokens": 1,
        "prompt_logprobs": 1,
        "return_token_ids": True,
    }
    response, digest = post_json("/v1/completions", payload)
    values = extract_teacher_forced_logprobs(response, int(case["scorer"]["minimum_scored_tokens"]))
    return {
        "source": "runtime_teacher_forced_input_token_logprobs",
        "token_sequence_sha256": case["token_sequence_sha256"],
        "input_token_logprobs": values,
    }, digest


def quality_capture(output: Path, quality_dir: Path, bf16_responses: Path) -> dict:
    cases = [json.loads(line) for line in (quality_dir / "development.jsonl").read_text().splitlines()]
    responses, evidence = [], []
    for case in cases:
        if case["category"] == "teacher_forced_loss":
            value, digest = teacher_forced_quality(case)
            evidence.append({"case_id": case["case_id"], "mode": "vllm_completion_prompt_logprobs", "raw_response_sha256": digest})
        else:
            value, digests = chat_quality(case)
            evidence.append({"case_id": case["case_id"], "mode": "deterministic_chat_completion", "raw_response_sha256": digests, "exact_repetition_identity": True})
        responses.append({"case_id": case["case_id"], "output": value})
    candidate = output / "quality-awq-responses.jsonl"
    candidate.write_bytes(b"".join(canonical(row) + b"\n" for row in responses))
    (output / "quality-evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    process = subprocess.run(
        ["python3", str(quality_dir / "score_pair.py"), str(quality_dir), "development", str(bf16_responses), str(candidate)],
        text=True, capture_output=True,
    )
    (output / "paired-quality.stdout.log").write_text(process.stdout)
    (output / "paired-quality.stderr.log").write_text(process.stderr)
    if process.returncode or not process.stdout.strip():
        raise BatchError("paired quality scorer did not produce a valid result")
    result = json.loads(process.stdout)
    overall = float(result.get("overall_regression", float("inf")))
    categories = result.get("category_regressions", {})
    result["prospective_paired_non_regression_pass"] = overall <= 0.02 and bool(categories) and all(float(value) <= 0.05 for value in categories.values())
    candidate_loss = next(row["output"] for row in responses if row["case_id"] == "dev_loss_01")
    nll = -statistics.fmean(float(row["logprob"]) for row in candidate_loss["input_token_logprobs"])
    result["candidate_teacher_forced_nll"] = nll
    result["prospective_nll_ceiling"] = 8.02778927385807
    result["prospective_nll_pass"] = nll <= result["prospective_nll_ceiling"]
    result["absolute_bf16_quality_failure_carried_forward"] = True
    result["pass"] = result["prospective_paired_non_regression_pass"] and result["prospective_nll_pass"]
    (output / "paired-quality.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def get_metrics() -> str:
    with urllib.request.urlopen(BASE_URL + "/metrics", timeout=30) as response:
        return response.read().decode()


def metric_totals(text: str) -> dict[str, float]:
    wanted = (
        "request_queue_time_seconds_sum", "request_queue_time_seconds_count",
        "time_to_first_token_seconds_sum", "time_to_first_token_seconds_count",
        "request_time_per_output_token_seconds_sum", "request_time_per_output_token_seconds_count",
        "prefix_cache_queries_total", "prefix_cache_hits_total",
    )
    totals = {name: 0.0 for name in wanted}
    for line in text.splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        name, raw = line.rsplit(" ", 1)
        base = name.split("{", 1)[0]
        for suffix in wanted:
            if base.endswith(suffix):
                try: totals[suffix] += float(raw)
                except ValueError: pass
    return totals


def stream_completion(prompt: str, timeout: int = 300, max_tokens: int = 1024) -> dict:
    payload = {
        "model": MODEL, "prompt": prompt, "temperature": 0, "max_tokens": max_tokens,
        "ignore_eos": True, "seed": 470100, "stream": True,
        "stream_options": {"include_usage": True}, "return_token_ids": True,
    }
    request = urllib.request.Request(BASE_URL + "/v1/completions", data=canonical(payload), headers={"Content-Type": "application/json"}, method="POST")
    start = time.monotonic()
    first = None
    end = None
    usage = None
    finish_reason = None
    token_events = 0
    raw_hash = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            raw_hash.update(raw)
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
                token_ids = choice.get("token_ids") or []
                text = choice.get("text") or ""
                if token_ids or text:
                    if first is None: first = time.monotonic()
                    token_events += len(token_ids) if token_ids else 1
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
    if first is None or end is None or not isinstance(usage, dict):
        raise BatchError("stream lacks timing or usage evidence")
    output_tokens = int(usage["completion_tokens"])
    return {
        "status": "success", "input_tokens": int(usage["prompt_tokens"]), "output_tokens": output_tokens,
        "finish_reason": finish_reason, "ttft_ms": (first - start) * 1000,
        "tpot_ms": ((end - first) * 1000 / max(1, output_tokens - 1)),
        "end_to_end_ms": (end - start) * 1000, "token_event_count": token_events,
        "stream_sha256": raw_hash.hexdigest(),
    }


def run_profile(prompt: str, concurrency: int, requests: int, output: Path, name: str) -> dict:
    before_text = get_metrics()
    (output / f"metrics-{name}-before.txt").write_text(before_text)
    started = time.monotonic()
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(stream_completion, prompt) for _ in range(requests)]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
    elapsed = time.monotonic() - started
    after_text = get_metrics()
    (output / f"metrics-{name}-after.txt").write_text(after_text)
    before, after = metric_totals(before_text), metric_totals(after_text)
    metrics_delta = {key: after[key] - before[key] for key in before}
    total_output = sum(row["output_tokens"] for row in rows)
    result = {
        "profile_id": name, "concurrency": concurrency, "requests": requests, "success_fraction": 1.0,
        "wall_seconds": elapsed, "total_input_tokens": sum(row["input_tokens"] for row in rows),
        "total_output_tokens": total_output, "output_tokens_per_second_conservative": total_output / elapsed,
        "ttft_ms": {"p50": percentile([row["ttft_ms"] for row in rows], .5), "p95": percentile([row["ttft_ms"] for row in rows], .95), "p99": percentile([row["ttft_ms"] for row in rows], .99)},
        "tpot_ms": {"p50": percentile([row["tpot_ms"] for row in rows], .5), "p95": percentile([row["tpot_ms"] for row in rows], .95), "p99": percentile([row["tpot_ms"] for row in rows], .99)},
        "metrics_delta": metrics_delta,
        "queue_seconds_mean_from_server_metric": metrics_delta["request_queue_time_seconds_sum"] / metrics_delta["request_queue_time_seconds_count"] if metrics_delta["request_queue_time_seconds_count"] > 0 else None,
        "prefix_cache_disabled": True,
        "prefix_cache_zero_delta": metrics_delta["prefix_cache_queries_total"] == 0 and metrics_delta["prefix_cache_hits_total"] == 0,
        "exact_geometry_pass": all(row["input_tokens"] == 8192 and row["output_tokens"] == 1024 for row in rows),
        "slo_pass": all(row["ttft_ms"] <= 10000 and row["tpot_ms"] <= 100 for row in rows),
        "rows": rows,
    }
    (output / f"profile-{name}.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def profile_if_admitted(output: Path, prompt: str, quality: dict, performance: dict) -> dict:
    admitted = bool(quality.get("pass") and performance.get("beats_complete_bf16_h100_cost"))
    result = {"admitted": admitted, "reason": "paired_quality_and_cheaper_than_complete_bf16_h100"}
    if not admitted:
        (output / "profiler-admission.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    try:
        for endpoint in ("/start_profile",):
            request = urllib.request.Request(BASE_URL + endpoint, data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=60) as response:
                response.read()
        result["request"] = stream_completion(prompt, timeout=300, max_tokens=128)
        request = urllib.request.Request(BASE_URL + "/stop_profile", data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=600) as response:
            response.read()
        deadline = time.time() + 120
        traces = []
        while time.time() < deadline:
            traces = sorted((output / "profiler").glob("**/*.pt.trace.json.gz"))
            if traces and all(path.stat().st_size > 0 for path in traces):
                break
            time.sleep(2)
        if not traces:
            raise BatchError("profiler produced no nonempty trace")
        result["traces"] = [
            {"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in traces
        ]
        result["pass"] = True
    except Exception as error:
        result.update({"pass": False, "error_type": type(error).__name__, "error": str(error)[:500]})
    (output / "profiler-admission.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def performance_batch(output: Path, tokenizer_dir: Path) -> tuple[dict, str]:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir)
    atom = tokenizer.encode(" code", add_special_tokens=False)
    if len(atom) != 1:
        raise BatchError("authoritative tokenizer has no one-token fixed atom")
    prompt = tokenizer.decode(atom * 8192)
    ids = tokenizer.encode(prompt, add_special_tokens=False)
    if len(ids) != 8192:
        raise BatchError("fixed prompt is not exactly 8192 tokens")
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    warmup = stream_completion(prompt)
    if warmup["input_tokens"] != 8192 or warmup["output_tokens"] != 1024:
        raise BatchError("warmup geometry mismatch")
    c1 = run_profile(prompt, 1, 4, output, "fixed_8k_1k_c1")
    c8 = run_profile(prompt, 8, 16, output, "fixed_8k_1k_c8")
    rate = c8["output_tokens_per_second_conservative"]
    result = {
        "prompt_sha256": prompt_hash, "authoritative_tokenizer": str(tokenizer_dir), "warmup": warmup,
        "profiles": [c1, c8], "fixed_slo_pass": c1["slo_pass"] and c8["slo_pass"] and c1["exact_geometry_pass"] and c8["exact_geometry_pass"] and c1["prefix_cache_zero_delta"] and c8["prefix_cache_zero_delta"],
        "l40s_full_vm_plus_disk_hourly_usd": L40S_HOURLY_USD,
        "steady_state_usd_per_million_output_tokens": L40S_HOURLY_USD / 3600 / rate * 1_000_000,
        "beats_complete_bf16_h100_cost": rate >= 67.565,
        "beats_0_88_per_million_anchor": rate >= 270.872,
        "throughput_ratio_vs_complete_bf16_h100": rate / BF16_C8_TOK_S,
    }
    (output / "performance-summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result, prompt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--bf16-responses", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "semantic": None,
        "quality": None,
        "performance": None,
        "profiler": None,
        "batch_pass": False,
        "claim_limit": "paired diagnostic against absolute-failing BF16 control; no provider-matched or quality-adjusted claim",
    }
    try:
        result["semantic"] = semantic_smoke(args.output)
        try:
            result["quality"] = quality_capture(args.output, args.quality, args.bf16_responses)
        except Exception as error:
            result["quality"] = {
                "pass": False,
                "quality_error": {"type": type(error).__name__, "message": str(error)[:1000]},
            }
        result["performance"], fixed_prompt = performance_batch(args.output, args.tokenizer)
        result["profiler"] = profile_if_admitted(args.output, fixed_prompt, result["quality"], result["performance"])
        result["batch_pass"] = bool(
            result["semantic"]["pass"] and result["quality"]["pass"] and result["performance"]["fixed_slo_pass"]
        )
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:1000]}
        semantic_path = args.output / "semantic-determinism.json"
        if result["semantic"] is None and semantic_path.exists():
            result["semantic"] = json.loads(semantic_path.read_text())
    (args.output / "allocation-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["batch_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
