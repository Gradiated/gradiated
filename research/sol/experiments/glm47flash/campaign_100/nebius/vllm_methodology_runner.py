#!/usr/bin/env python3
"""Artificial Analysis methodology-matched and public load-test measurements."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import statistics
import time
import urllib.request
from pathlib import Path

import tiktoken


BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:30000")
MODEL = os.environ.get("VLLM_MODEL", "glm-4.7-flash-awq")
ENCODING = tiktoken.get_encoding("o200k_base")
SINGLE_REQUESTS = int(os.environ.get("VLLM_SINGLE_REQUESTS", "7"))
SINGLE_INPUT_TOKENS = int(os.environ.get("VLLM_SINGLE_INPUT_TOKENS", "10000"))
SINGLE_OUTPUT_TOKENS = int(os.environ.get("VLLM_SINGLE_OUTPUT_TOKENS", "1500"))
LOAD_INPUT_TOKENS = int(os.environ.get("VLLM_LOAD_INPUT_TOKENS", "1000"))
LOAD_OUTPUT_TOKENS = int(os.environ.get("VLLM_LOAD_OUTPUT_TOKENS", "1000"))
PHASE_SECONDS = int(os.environ.get("VLLM_PHASE_SECONDS", "180"))
LADDER = tuple(int(value) for value in os.environ.get("VLLM_CONCURRENCIES", "1,2,4,8,16,32,64").split(",") if value)


class MethodologyError(RuntimeError):
    pass


def accumulate_output_token_histogram(histogram: dict[int, int], token_ids: object) -> int:
    if token_ids is None:
        return 0
    if not isinstance(token_ids, list) or any(not isinstance(token_id, int) for token_id in token_ids):
        raise MethodologyError("stream output token IDs are malformed")
    for token_id in token_ids:
        histogram[token_id] = histogram.get(token_id, 0) + 1
    return len(token_ids)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise MethodologyError("empty percentile input")
    return sorted(values)[min(len(values) - 1, max(0, int((len(values) - 1) * fraction + 0.999999)))]


def prompt_for(index: int, token_count: int, family: str) -> str:
    themes = (
        "marine ecology field notes", "distributed systems incident review", "constitutional history seminar",
        "materials-science laboratory protocol", "public-health planning memo", "language documentation interview",
        "astronomy observation log", "software security architecture", "transportation policy workshop",
    )
    seed = f"{family} {index}: Analyze the following {themes[index % len(themes)]}. Give a structured, evidence-aware answer. "
    tokens = ENCODING.encode(seed)
    filler = ENCODING.encode(" Detail, causality, alternatives, uncertainty, and verification matter.")
    while len(tokens) < token_count:
        tokens.extend(filler)
    return ENCODING.decode(tokens[:token_count])


def stream(prompt: str, max_tokens: int, request_index: int, timeout: int = 600) -> dict:
    payload = {
        "model": MODEL, "prompt": prompt, "temperature": 0, "max_tokens": max_tokens,
        "ignore_eos": True, "seed": 470100 + request_index, "stream": True,
        "stream_options": {"include_usage": True}, "return_token_ids": True,
    }
    request = urllib.request.Request(BASE_URL + "/v1/completions", data=canonical(payload), headers={"Content-Type": "application/json"}, method="POST")
    start = time.monotonic()
    first = end = None
    usage = None
    finish_reason = None
    output_token_histogram: dict[int, int] = {}
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            digest.update(raw)
            line = raw.strip()
            if not line.startswith(b"data:"):
                continue
            item = line[5:].strip()
            if item == b"[DONE]":
                end = time.monotonic()
                break
            value = json.loads(item)
            if isinstance(value.get("usage"), dict):
                usage = value["usage"]
            choices = value.get("choices") or []
            if choices:
                choice = choices[0]
                token_id_count = accumulate_output_token_histogram(output_token_histogram, choice.get("token_ids"))
                if first is None and (token_id_count or choice.get("text")):
                    first = time.monotonic()
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
    if first is None or end is None or not isinstance(usage, dict):
        raise MethodologyError("stream lacks TTFT/end/usage evidence")
    output_tokens = int(usage["completion_tokens"])
    retained_token_ids = sum(output_token_histogram.values())
    return {
        "request_index": request_index, "status": "success", "input_tokens_server": int(usage["prompt_tokens"]),
        "input_tokens_o200k": len(ENCODING.encode(prompt)), "output_tokens_server": output_tokens,
        "finish_reason": finish_reason, "ttft_ms": (first - start) * 1000,
        "post_first_token_output_tokens_per_second": output_tokens / max(end - first, 1e-9),
        "end_to_end_ms": (end - start) * 1000, "stream_sha256": digest.hexdigest(),
        "output_token_histogram": {str(token_id): output_token_histogram[token_id] for token_id in sorted(output_token_histogram)},
        "output_token_ids_complete": retained_token_ids == output_tokens,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def single_request(output: Path) -> dict:
    rows = [stream(prompt_for(index, SINGLE_INPUT_TOKENS, "single"), SINGLE_OUTPUT_TOKENS, index) for index in range(SINGLE_REQUESTS)]
    for row in rows:
        if row["input_tokens_o200k"] != SINGLE_INPUT_TOKENS or row["output_tokens_server"] < SINGLE_OUTPUT_TOKENS:
            raise MethodologyError("single-request geometry mismatch")
    result = {
        "methodology": "Artificial Analysis methodology-matched; private live prompts not replayed",
        "streaming": True, "concurrency": 1, "requests": len(rows), "rows": rows,
        "median_ttft_ms": statistics.median(row["ttft_ms"] for row in rows),
        "median_post_first_token_output_tokens_per_second": statistics.median(row["post_first_token_output_tokens_per_second"] for row in rows),
        "geometry_pass": True,
    }
    write_json(output / "aa-single-request.json", result)
    return result


def load_phase(output: Path, concurrency: int, phase_index: int) -> dict:
    prompts = [prompt_for(10_000 + phase_index * 1_000 + index, LOAD_INPUT_TOKENS, "load") for index in range(max(concurrency * 4, 128))]
    started = time.monotonic()
    deadline = started + PHASE_SECONDS
    rows: list[dict] = []
    next_index = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        inflight = {pool.submit(stream, prompts[next_index % len(prompts)], LOAD_OUTPUT_TOKENS, next_index): next_index for next_index in range(concurrency)}
        next_index = concurrency
        while inflight:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                for future in inflight:
                    future.cancel()
                break
            done, _ = concurrent.futures.wait(inflight, timeout=remaining, return_when=concurrent.futures.FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                del inflight[future]
                row = future.result()
                rows.append(row)
                if time.monotonic() < deadline:
                    inflight[pool.submit(stream, prompts[next_index % len(prompts)], LOAD_OUTPUT_TOKENS, next_index)] = next_index
                    next_index += 1
    elapsed = time.monotonic() - started
    complete = [row for row in rows if row["input_tokens_o200k"] == LOAD_INPUT_TOKENS and row["output_tokens_server"] >= LOAD_OUTPUT_TOKENS]
    result = {
        "concurrency": concurrency, "planned_phase_seconds": PHASE_SECONDS, "wall_seconds": elapsed,
        "requests_completed": len(rows), "success_fraction": len(complete) / len(rows) if rows else 0.0,
        "aggregate_output_tokens_per_second": sum(row["output_tokens_server"] for row in rows) / elapsed if elapsed else 0.0,
        "geometry_pass": bool(rows) and len(complete) == len(rows), "rows": rows,
        "ttft_ms": {"p50": percentile([row["ttft_ms"] for row in rows], .5), "p95": percentile([row["ttft_ms"] for row in rows], .95)},
    }
    write_json(output / f"aa-system-load-c{concurrency}.json", result)
    return result


def system_load(output: Path) -> dict:
    phases = []
    plateau = None
    for phase_index, concurrency in enumerate(LADDER):
        phase = load_phase(output, concurrency, phase_index)
        phases.append(phase)
        if len(phases) >= 3:
            prev, current = phases[-2:]
            gain = current["aggregate_output_tokens_per_second"] / prev["aggregate_output_tokens_per_second"] - 1
            phase["gain_vs_previous"] = gain
            if phases[-2].get("gain_vs_previous") is not None and gain < .05 and phases[-2]["gain_vs_previous"] < .05:
                plateau = {"at_concurrency": concurrency, "rule": "two adjacent steps below 5% aggregate-throughput gain"}
                break
    result = {"methodology": "Artificial Analysis public System Load Test geometry", "streaming": True, "phases": phases, "plateau": plateau}
    write_json(output / "aa-system-load-summary.json", result)
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run_single = os.environ.get("VLLM_RUN_SINGLE", "1") == "1"
    run_load = os.environ.get("VLLM_RUN_LOAD", "1") == "1"
    if not run_single and not run_load:
        raise MethodologyError("at least one methodology phase must be enabled")
    result = {"schema_version": 1, "single_request": None, "system_load": None, "pass": False}
    try:
        if run_single:
            result["single_request"] = single_request(args.output)
        if run_load:
            result["system_load"] = system_load(args.output)
        result["pass"] = True
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:1000]}
    write_json(args.output / "aa-methodology-result.json", result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
