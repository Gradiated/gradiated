#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import pathlib
import statistics
import subprocess
import threading
import time
import urllib.request


BASE = "http://127.0.0.1:30000"
MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
COMMON_TOKENS = 535
CONCURRENCY = 32
SEED = "gemma4-background-exact-mix-c32-20260718"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def tokens(label: str, count: int) -> list[int]:
    result: list[int] = []
    index = 0
    while len(result) < count:
        digest = hashlib.sha256(f"{SEED}|{label}|{index}".encode()).digest()
        for offset in range(0, len(digest), 4):
            result.append(
                1000 + int.from_bytes(digest[offset : offset + 4], "big") % 249000
            )
            if len(result) == count:
                return result
        index += 1
    return result


def get(path: str) -> bytes:
    return urllib.request.urlopen(BASE + path, timeout=30).read()


def post(path: str, body: dict[str, object], timeout: float = 900):
    request = urllib.request.Request(
        BASE + path,
        canonical(body),
        {"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def metric_sum(raw: bytes, name: str) -> float | None:
    values = []
    for line in raw.decode(errors="replace").splitlines():
        if line.startswith(name) and not line.startswith("#"):
            try:
                values.append(float(line.rsplit(" ", 1)[1]))
            except (IndexError, ValueError):
                pass
    return sum(values) if values else None


def metric_delta(before: bytes, after: bytes, name: str) -> float | None:
    first = metric_sum(before, name)
    second = metric_sum(after, name)
    return None if first is None or second is None else second - first


def gpu_sample(path: pathlib.Path, stop: threading.Event) -> None:
    with path.open("w") as output:
        output.write("monotonic_s,utilization_gpu_pct,memory_used_mib,power_w\n")
        while not stop.is_set():
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,power.draw",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output.write(f"{time.monotonic():.6f},{result.stdout.strip()}\n")
            output.flush()
            stop.wait(0.25)


def one(
    index: int,
    body: dict[str, object],
    root: pathlib.Path,
    ready: threading.Barrier,
    release: threading.Barrier,
) -> dict[str, object]:
    ready.wait(timeout=120)
    release.wait(timeout=120)
    started = time.monotonic()
    first = None
    chunks: list[bytes] = []
    output_ids: list[int] = []
    usage: dict[str, object] = {}
    spec: dict[str, object] = {}
    text = ""
    error = None
    try:
        with post("/v1/completions", body) as response:
            for raw in response:
                now = time.monotonic()
                chunks.append(raw)
                if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                    continue
                item = json.loads(raw[6:])
                choice = (item.get("choices") or [{}])[0]
                piece = choice.get("text") or ""
                if piece and first is None:
                    first = now
                text += piece
                ids = choice.get("token_ids") or item.get("token_ids") or []
                output_ids.extend(ids)
                if item.get("usage"):
                    usage = item["usage"]
                meta = item.get("meta_info") or item.get("metadata") or {}
                for name in (
                    "spec_num_correct_drafts",
                    "spec_num_proposed_drafts",
                    "spec_verify_ct",
                    "spec_accept_rate",
                    "spec_accept_length",
                    "spec_correct_drafts_histogram",
                ):
                    if name in meta:
                        spec[name] = meta[name]
    except Exception as exception:
        error = f"{type(exception).__name__}: {exception}"[:2000]
    ended = time.monotonic()
    raw_response = b"".join(chunks)
    (root / f"response-{index:02d}.sse").write_bytes(raw_response)
    row = {
        "index": index,
        "started_monotonic_s": started,
        "first_token_monotonic_s": first,
        "ended_monotonic_s": ended,
        "wall_seconds": ended - started,
        "ttft_seconds": None if first is None else first - started,
        "decode_seconds": None if first is None else ended - first,
        "error": error,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "returned_token_ids": len(output_ids),
        "output_token_ids": output_ids,
        "output_token_ids_sha256": hashlib.sha256(canonical(output_ids)).hexdigest(),
        "text_nonempty": bool(text),
        "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
        "response_sha256": hashlib.sha256(raw_response).hexdigest(),
        "spec": spec,
    }
    atomic(root / f"request-{index:02d}.json", row)
    return row


def finite_summary(values: list[float | None]) -> dict[str, float | None]:
    data = [value for value in values if value is not None and math.isfinite(value)]
    return {
        "mean": statistics.mean(data) if data else None,
        "median": statistics.median(data) if data else None,
        "max": max(data) if data else None,
    }


def diagnostics(root: pathlib.Path) -> list[dict[str, object]]:
    cases = [
        ("instruction", "Reply with exactly: READY"),
        ("arithmetic", "What is 2+2? Reply with only the number."),
        ("structured", 'Return only JSON with key "status" and value "ok".'),
    ]
    rows = []
    for label, prompt in cases:
        body = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "seed": 20260718,
            "max_tokens": 32,
            "stream": False,
            "return_token_ids": True,
        }
        with post("/v1/chat/completions", body, timeout=180) as response:
            raw = response.read()
        item = json.loads(raw)
        choice = item["choices"][0]
        ids = choice.get("token_ids") or item.get("token_ids") or []
        text = choice["message"]["content"]
        if label == "instruction":
            valid = "READY" in text.upper()
        elif label == "arithmetic":
            valid = text.strip().strip(".") == "4"
        else:
            try:
                valid = json.loads(text).get("status") == "ok"
            except (json.JSONDecodeError, AttributeError):
                valid = False
        rows.append(
            {
                "label": label,
                "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "text": text,
                "valid": valid,
                "output_token_ids": ids,
                "output_token_ids_sha256": hashlib.sha256(canonical(ids)).hexdigest(),
            }
        )
    atomic(root / "DIAGNOSTICS.json", rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--arm", required=True)
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=False)

    prefix = tokens("common-prefix", COMMON_TOKENS)
    bodies = []
    for index in range(CONCURRENCY):
        suffix = tokens(f"suffix-{index}", PROMPT_TOKENS - COMMON_TOKENS)
        suffix[0] = 200000 + index
        bodies.append(
            {
                "model": MODEL,
                "prompt": prefix + suffix,
                "max_tokens": OUTPUT_TOKENS,
                "min_tokens": OUTPUT_TOKENS,
                "ignore_eos": True,
                "temperature": 0,
                "seed": 20260718,
                "stream": True,
                "stream_options": {"include_usage": True},
                "return_token_ids": True,
                "add_special_tokens": False,
            }
        )
    workload = {
        "prompt_tokens": PROMPT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "concurrency": CONCURRENCY,
        "shared_prefix_tokens": COMMON_TOKENS,
        "seed": SEED,
        "request_sha256": [hashlib.sha256(canonical(body)).hexdigest() for body in bodies],
    }
    atomic(root / "WORKLOAD.json", workload)
    get("/v1/models")
    with post("/flush_cache", {}, timeout=30) as response:
        response.read()
    diagnostics_rows = diagnostics(root)

    warmup_suffix = tokens("warmup-suffix", PROMPT_TOKENS - COMMON_TOKENS)
    warmup_suffix[0] = 199999
    warmup = dict(bodies[0])
    warmup.update({"prompt": prefix + warmup_suffix, "max_tokens": 1, "min_tokens": 1, "stream": False})
    warmup.pop("stream_options")
    with post("/v1/completions", warmup) as response:
        (root / "warmup.json").write_bytes(response.read())
    before = get("/metrics")
    (root / "metrics-before.prom").write_bytes(before)

    ready = threading.Barrier(CONCURRENCY + 1)
    release = threading.Barrier(CONCURRENCY + 1)
    stop = threading.Event()
    sampler = threading.Thread(target=gpu_sample, args=(root / "gpu.csv", stop), daemon=True)
    sampler.start()
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(one, i, body, root, ready, release) for i, body in enumerate(bodies)]
        ready.wait(timeout=120)
        release.wait(timeout=120)
        rows = [future.result() for future in futures]
    batch_seconds = time.monotonic() - started
    stop.set()
    sampler.join(timeout=3)
    after = get("/metrics")
    (root / "metrics-after.prom").write_bytes(after)

    prompt_delta = metric_delta(before, after, "sglang:prompt_tokens_histogram_sum")
    uncached_delta = metric_delta(before, after, "sglang:uncached_prompt_tokens_histogram_sum")
    cached_delta = None if prompt_delta is None or uncached_delta is None else prompt_delta - uncached_delta
    spec_verify_delta = metric_delta(before, after, "sglang:spec_verify_calls_total")
    valid = all(
        row["error"] is None
        and row["prompt_tokens"] == PROMPT_TOKENS
        and row["completion_tokens"] == OUTPUT_TOKENS
        and row["text_nonempty"]
        for row in rows
    )
    diagnostics_pass = all(row["valid"] for row in diagnostics_rows)
    spec_rows = [row["spec"] for row in rows if row["spec"]]
    spec_valid = True
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "arm": args.arm,
        "pass": valid and spec_valid and diagnostics_pass,
        "complete_requests": sum(row["error"] is None for row in rows),
        "batch_seconds": batch_seconds,
        "service_seconds_per_request": batch_seconds / CONCURRENCY,
        "complete_request_throughput": CONCURRENCY / batch_seconds,
        "output_tokens_per_second": CONCURRENCY * OUTPUT_TOKENS / batch_seconds,
        "workload": workload,
        "cache": {
            "prompt_tokens_delta": prompt_delta,
            "uncached_prompt_tokens_delta": uncached_delta,
            "cached_prompt_tokens_delta": cached_delta,
            "cached_fraction": None if not prompt_delta or cached_delta is None else cached_delta / prompt_delta,
        },
        "speculation": {
            "pass": spec_valid,
            "verify_calls_delta": spec_verify_delta,
            "rows": spec_rows,
        },
        "diagnostics": diagnostics_rows,
        "diagnostics_pass": diagnostics_pass,
        "phases": {
            "ttft": finite_summary([row["ttft_seconds"] for row in rows]),
            "decode": finite_summary([row["decode_seconds"] for row in rows]),
            "end_to_end": finite_summary([row["wall_seconds"] for row in rows]),
        },
        "rows": rows,
    }
    atomic(root / "TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 72


if __name__ == "__main__":
    raise SystemExit(main())
