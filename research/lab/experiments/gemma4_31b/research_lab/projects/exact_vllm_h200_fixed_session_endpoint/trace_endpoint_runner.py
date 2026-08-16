#!/usr/bin/env python3
"""Execute the frozen exact-token Gemma endpoint trace against an OpenAI server."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get(base: str, path: str) -> bytes:
    with urllib.request.urlopen(base + path, timeout=30) as response:
        return response.read()


def counters(raw: bytes) -> dict[str, float]:
    result = {"queries": 0.0, "hits": 0.0}
    for line in raw.decode(errors="replace").splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        name, value = line.rsplit(" ", 1)
        base = name.split("{", 1)[0]
        try:
            if base in {"vllm:prefix_cache_queries", "vllm:prefix_cache_queries_total"}:
                result["queries"] += float(value)
            elif base in {"vllm:prefix_cache_hits", "vllm:prefix_cache_hits_total"}:
                result["hits"] += float(value)
        except ValueError:
            pass
    return result


def stream_one(base: str, body: dict, root: Path, stem: str, barrier: threading.Barrier | None = None) -> dict:
    body_bytes = canonical(body)
    (root / "request-bodies" / f"{stem}.json").write_bytes(body_bytes)
    if barrier is not None:
        barrier.wait(timeout=60)
    started_wall_ns = time.time_ns()
    started = time.monotonic()
    first = None
    ended = None
    output_ids: list[int] = []
    output_token_times: list[float] = []
    usage = None
    finish_reason = None
    raw_path = root / "raw-sse" / f"{stem}.sse"
    request = urllib.request.Request(
        base + "/v1/completions",
        data=body_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1800) as response, raw_path.open("wb") as handle:
            for raw in response:
                handle.write(raw)
                line = raw.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    ended = time.monotonic()
                    break
                event = json.loads(payload)
                if isinstance(event.get("usage"), dict):
                    usage = event["usage"]
                choices = event.get("choices") or []
                if choices:
                    choice = choices[0]
                    tokens = choice.get("token_ids") or []
                    if tokens:
                        if not all(isinstance(token, int) for token in tokens):
                            raise RuntimeError("malformed returned token ids")
                        output_ids.extend(tokens)
                        output_token_times.extend([time.monotonic()] * len(tokens))
                    if tokens or choice.get("text"):
                        first = first or time.monotonic()
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice["finish_reason"]
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.read(4096).decode(errors='replace')}") from error
    prompt = body["prompt"]
    expected_output = int(body["max_tokens"])
    passed = bool(
        first is not None
        and ended is not None
        and usage
        and usage.get("prompt_tokens") == len(prompt)
        and usage.get("completion_tokens") == expected_output
        and len(output_ids) == expected_output
    )
    row = {
        "pass": passed,
        "request_id": body.get("request_id"),
        "prompt_tokens": len(prompt),
        "output_tokens": expected_output,
        "usage": usage,
        "output_token_ids": output_ids,
        "output_token_ids_sha256": sha(canonical(output_ids)),
        "request_body_sha256": sha(body_bytes),
        "raw_sse_sha256": sha(raw_path.read_bytes()),
        "raw_sse_bytes": raw_path.stat().st_size,
        "finish_reason": finish_reason,
        "started_wall_ns": started_wall_ns,
        "first_token_seconds": None if first is None else first - started,
        "per_token_arrival_seconds": [timestamp - started for timestamp in output_token_times],
        "inter_token_latency_seconds": [
            later - earlier
            for earlier, later in zip(output_token_times, output_token_times[1:])
        ],
        "wall_seconds": time.monotonic() - started,
    }
    (root / "normalized" / f"{stem}.json").write_text(json.dumps(row, sort_keys=True) + "\n")
    return row


def run_group(base: str, group: dict, output: Path) -> dict:
    name = group["name"]
    root = output / name
    root.mkdir()
    for child in ("request-bodies", "raw-sse", "normalized"):
        (root / child).mkdir()
    before = get(base, "/metrics")
    (root / "before-warmup.prom").write_bytes(before)
    warmup = stream_one(base, group["warmup"]["request_body"], root, "warmup")
    after_warmup = get(base, "/metrics")
    (root / "after-warmup.prom").write_bytes(after_warmup)
    barrier = threading.Barrier(int(group["concurrency"]))
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(group["concurrency"])) as pool:
        futures = [
            pool.submit(stream_one, base, row["request_body"], root, f"scored-{index:02d}", barrier)
            for index, row in enumerate(group["scored"])
        ]
        scored = [future.result() for future in futures]
    wall = time.monotonic() - started
    after_scored = get(base, "/metrics")
    (root / "after-scored.prom").write_bytes(after_scored)
    warm = counters(after_warmup)
    after = counters(after_scored)
    query_delta = after["queries"] - warm["queries"]
    hit_delta = after["hits"] - warm["hits"]
    expected_queries = int(group["concurrency"]) * 4214
    maximum_hits = int(group["concurrency"]) * 528
    terminal = {
        "name": name,
        "concurrency": int(group["concurrency"]),
        "pass": warmup["pass"] and all(row["pass"] for row in scored) and query_delta == expected_queries and 0 <= hit_delta <= maximum_hits,
        "warmup_pass": warmup["pass"],
        "complete_count": sum(row["pass"] for row in scored),
        "failure_count": sum(not row["pass"] for row in scored),
        "wall_seconds": wall,
        "completed_requests_per_second": len(scored) / wall,
        "cache_query_delta_tokens": query_delta,
        "cache_hit_delta_tokens": hit_delta,
        "realized_cache_read_fraction": hit_delta / expected_queries,
        "maximum_cacheable_fraction": 528 / 4214,
        "rows": scored,
    }
    (root / "TERMINAL.json").write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    return terminal


def run_10k(base: str, packet: dict, output: Path) -> dict:
    root = output / "separate_10k"
    root.mkdir()
    for child in ("request-bodies", "raw-sse", "normalized"):
        (root / child).mkdir()
    row = stream_one(base, packet["request_body"], root, "scored")
    terminal = {"name": "separate_10k", "concurrency": 1, "pass": row["pass"], "complete_count": int(row["pass"]), "failure_count": int(not row["pass"]), "rows": [row]}
    (root / "TERMINAL.json").write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base", default="http://127.0.0.1:30000")
    parser.add_argument("--mode", choices=("semantic", "baseline", "baseline_after_semantic", "sglang"), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    packet = json.loads(args.trace.read_text())
    models_raw = get(args.base, "/v1/models")
    (args.output / "models.json").write_bytes(models_raw)
    models = json.loads(models_raw)
    served = [row.get("id") for row in models.get("data", [])]
    result = {"schema_version": 1, "mode": args.mode, "served_models": served, "arms": [], "pass": False}
    try:
        groups = (
            packet["primary_groups"][:1]
            if args.mode == "semantic"
            else packet["primary_groups"][1:]
            if args.mode == "baseline_after_semantic"
            else packet["primary_groups"]
        )
        for group in groups:
            arm = run_group(args.base, group, args.output)
            result["arms"].append(arm)
            if not arm["pass"]:
                break
        if args.mode != "semantic" and all(arm["pass"] for arm in result["arms"]):
            result["single_10k"] = run_10k(args.base, packet["separate_10k_stream"], args.output)
        expected = packet["identity"]["model"]
        result["complete_count"] = sum(arm["complete_count"] for arm in result["arms"]) + int((result.get("single_10k") or {}).get("complete_count", 0))
        result["failure_count"] = sum(arm["failure_count"] for arm in result["arms"]) + int((result.get("single_10k") or {}).get("failure_count", 0))
        result["reload_count"] = 0
        result["useful_gpu_seconds"] = sum(float(arm["wall_seconds"]) for arm in result["arms"])
        result["pass"] = expected in served and all(arm["pass"] for arm in result["arms"]) and (args.mode == "semantic" or (result.get("single_10k") or {}).get("pass") is True)
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    temporary = args.output / "TERMINAL.json.part"
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output / "TERMINAL.json")
    return 0 if result["pass"] else 72


if __name__ == "__main__":
    raise SystemExit(main())
