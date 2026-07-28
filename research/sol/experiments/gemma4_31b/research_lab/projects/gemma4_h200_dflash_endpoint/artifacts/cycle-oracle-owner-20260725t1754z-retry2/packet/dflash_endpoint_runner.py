#!/usr/bin/env python3
"""Run one exact DFlash or autoregressive endpoint arm and retain raw evidence."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import pathlib
import statistics
import threading
import time
import urllib.request

MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS, OUTPUT_TOKENS, COMMON_TOKENS = 4214, 358, 535
SEED = "gemma4-background-exact-mix-c32-20260718"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def tokens(label: str, count: int) -> list[int]:
    values: list[int] = []
    index = 0
    while len(values) < count:
        digest = hashlib.sha256(f"{SEED}|{label}|{index}".encode()).digest()
        values.extend(1000 + int.from_bytes(digest[offset : offset + 4], "big") % 249000 for offset in range(0, len(digest), 4))
        index += 1
    return values[:count]


def request(base: str, body: dict, timeout: float):
    return urllib.request.urlopen(
        urllib.request.Request(
            base + "/generate",
            canonical(body),
            {"Content-Type": "application/json"},
        ),
        timeout=timeout,
    )


def one(base: str, index: int, body: dict, root: pathlib.Path, ready: threading.Barrier, release: threading.Barrier) -> dict:
    ready.wait(timeout=120); release.wait(timeout=120)
    started, first, error, text, meta, ids, chunks = time.monotonic(), None, None, "", {}, [], []
    try:
        with request(base, body, 1200) as response:
            for raw in response:
                chunks.append(raw)
                if raw.startswith(b"data: "):
                    item = json.loads(raw[6:])
                    if item.get("error"):
                        raise RuntimeError(str(item["error"]))
                    delta_text = item.get("text") or ""
                    delta_ids = item.get("output_ids") or []
                    if (delta_text or delta_ids) and first is None:
                        first = time.monotonic()
                    text += delta_text
                    ids.extend(int(value) for value in delta_ids)
                    if item.get("meta_info"):
                        meta = item["meta_info"]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:2000]
    ended, raw = time.monotonic(), b"".join(chunks)
    (root / f"response-{index:02d}.sse").write_bytes(raw)
    (root / f"response-{index:02d}.txt").write_text(text)
    row = {"index": index, "started_monotonic_s": started, "first_token_monotonic_s": first, "ended_monotonic_s": ended, "wall_seconds": ended-started, "ttft_seconds": None if first is None else first-started, "decode_seconds": None if first is None else ended-first, "error": error, "prompt_tokens": meta.get("prompt_tokens"), "completion_tokens": meta.get("completion_tokens"), "cached_tokens": meta.get("cached_tokens"), "token_ids": ids, "returned_token_ids": len(ids), "text_nonempty": bool(text), "text_finite": error is None and all(math.isfinite(float(ord(c))) for c in text), "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "request_sha256": hashlib.sha256(canonical(body)).hexdigest(), "response_sha256": hashlib.sha256(raw).hexdigest()}
    atomic(root / f"request-{index:02d}.json", row)
    return row


def summary(values: list[float | None]) -> dict[str, float | None]:
    finite = [value for value in values if value is not None and math.isfinite(value)]
    return {"mean": statistics.mean(finite) if finite else None, "median": statistics.median(finite) if finite else None, "max": max(finite) if finite else None}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--base", default="http://127.0.0.1:30000"); parser.add_argument("--output", type=pathlib.Path, required=True); parser.add_argument("--arm", required=True); parser.add_argument("--concurrency", type=int, required=True); args = parser.parse_args()
    root = args.output; root.mkdir(parents=True, exist_ok=False)
    prefix = tokens("common-prefix", COMMON_TOKENS); bodies = []
    for index in range(args.concurrency):
        suffix = tokens(f"suffix-{index}", PROMPT_TOKENS-COMMON_TOKENS); suffix[0] = 200000 + index
        bodies.append({"input_ids": prefix+suffix, "sampling_params": {"max_new_tokens": OUTPUT_TOKENS, "min_new_tokens": OUTPUT_TOKENS, "ignore_eos": True, "temperature": 0, "sampling_seed": 20260718}, "stream": True})
    atomic(root / "WORKLOAD.json", {"prompt_tokens": PROMPT_TOKENS, "output_tokens": OUTPUT_TOKENS, "concurrency": args.concurrency, "shared_prefix_tokens": COMMON_TOKENS, "api": "/generate", "request_sha256": [hashlib.sha256(canonical(body)).hexdigest() for body in bodies], "input_ids_sha256": [hashlib.sha256(canonical(body["input_ids"])).hexdigest() for body in bodies]})
    urllib.request.urlopen(args.base + "/v1/models", timeout=30).read()
    try: urllib.request.urlopen(urllib.request.Request(args.base + "/flush_cache", b"{}", {"Content-Type": "application/json"}), timeout=30).read()
    except Exception as exc: (root / "flush_cache.error").write_text(repr(exc) + "\n")
    before = urllib.request.urlopen(args.base + "/metrics", timeout=30).read(); (root / "metrics-before.prom").write_bytes(before)
    ready, release = threading.Barrier(args.concurrency+1), threading.Barrier(args.concurrency+1); started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(one, args.base, index, body, root, ready, release) for index, body in enumerate(bodies)]
        ready.wait(timeout=120); release.wait(timeout=120); rows = [future.result() for future in futures]
    batch_seconds = time.monotonic()-started; after = urllib.request.urlopen(args.base + "/metrics", timeout=30).read(); (root / "metrics-after.prom").write_bytes(after)
    valid = all(row["error"] is None and row["prompt_tokens"] == PROMPT_TOKENS and row["completion_tokens"] == OUTPUT_TOKENS and row["text_nonempty"] and row["text_finite"] for row in rows)
    atomic(root / "TERMINAL.json", {"schema_version": 1, "arm": args.arm, "pass": valid, "concurrency": args.concurrency, "complete_requests": sum(row["error"] is None for row in rows), "batch_seconds": batch_seconds, "service_seconds_per_request": batch_seconds/args.concurrency, "output_tokens_per_second": args.concurrency*OUTPUT_TOKENS/batch_seconds, "raw_token_ids_present": all(row["returned_token_ids"] == OUTPUT_TOKENS for row in rows), "phases": {"ttft": summary([row["ttft_seconds"] for row in rows]), "decode": summary([row["decode_seconds"] for row in rows])}, "rows": rows})
    return 0 if valid else 72


if __name__ == "__main__": raise SystemExit(main())
