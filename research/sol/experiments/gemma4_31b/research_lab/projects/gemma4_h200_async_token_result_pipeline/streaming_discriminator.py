#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import statistics
import threading
import time
import urllib.request


BASE = "http://127.0.0.1:30000"
MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
COMMON_TOKENS = 535
DEFAULT_OUTPUT_TOKENS = 16
DEFAULT_CONCURRENCY = 32
SEED = "gemma4-background-exact-mix-c32-20260718"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic_json(path: pathlib.Path, value: object) -> None:
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
                1000
                + int.from_bytes(digest[offset : offset + 4], "big") % 249000
            )
            if len(result) == count:
                return result
        index += 1
    return result


def get(path: str) -> bytes:
    return urllib.request.urlopen(BASE + path, timeout=30).read()


def post(body: dict, timeout: float = 900):
    request = urllib.request.Request(
        BASE + "/v1/completions",
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


def one(
    index: int,
    body: dict,
    root: pathlib.Path,
    ready: threading.Barrier,
    release: threading.Barrier,
) -> dict[str, object]:
    ready.wait(timeout=120)
    release.wait(timeout=120)
    started = time.monotonic()
    first = None
    chunks: list[bytes] = []
    normalized_events: list[dict[str, object]] = []
    output_ids: list[int] = []
    usage: dict[str, object] = {}
    text = ""
    error = None
    try:
        with post(body) as response:
            for raw in response:
                now = time.monotonic()
                chunks.append(raw)
                if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                    continue
                item = json.loads(raw[6:])
                choice = (item.get("choices") or [{}])[0]
                token_ids = list(choice.get("token_ids") or [])
                chunk_text = choice.get("text") or ""
                if (token_ids or chunk_text) and first is None:
                    first = now
                output_ids.extend(token_ids)
                text += chunk_text
                if item.get("usage"):
                    usage = item["usage"]
                normalized_events.append(
                    {
                        "token_ids": token_ids,
                        "text": chunk_text,
                        "finish_reason": choice.get("finish_reason"),
                        "usage": item.get("usage"),
                    }
                )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:2000]
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
        "output_ids": output_ids,
        "normalized_events": normalized_events,
        "text": text,
        "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
        "raw_response_sha256": hashlib.sha256(raw_response).hexdigest(),
    }
    atomic_json(root / f"row-{index:02d}.json", row)
    return row


def finite_summary(values: list[float | None]) -> dict[str, float | None]:
    data = [value for value in values if value is not None]
    return {
        "mean": statistics.mean(data) if data else None,
        "median": statistics.median(data) if data else None,
        "max": max(data) if data else None,
    }


def recover_serialized_token_ids(
    rows: list[dict[str, object]], checkpoint: str
) -> bool:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    passed = True
    for row in rows:
        output_ids: list[int] = []
        for event in row["normalized_events"]:
            if not event["text"]:
                continue
            ids = tokenizer.encode(event["text"], add_special_tokens=False)
            if len(ids) != 1:
                passed = False
                continue
            event["token_ids"] = ids
            output_ids.extend(ids)
        row["output_ids"] = output_ids
        row["returned_token_ids"] = len(output_ids)
    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--arm", choices=["control", "candidate"])
    parser.add_argument("--arm-file", type=pathlib.Path)
    parser.add_argument("--output-tokens", type=int, default=DEFAULT_OUTPUT_TOKENS)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--checkpoint", default="/work/checkpoint")
    parser.add_argument("--repair-existing", type=pathlib.Path)
    args = parser.parse_args()
    if args.repair_existing is not None:
        root = args.repair_existing
        terminal = json.loads((root / "TERMINAL.json").read_text())
        rows = [
            json.loads((root / f"row-{index:02d}.json").read_text())
            for index in range(int(terminal["concurrency"]))
        ]
        token_recovery_pass = recover_serialized_token_ids(rows, args.checkpoint)
        for index, row in enumerate(rows):
            atomic_json(root / f"row-{index:02d}.json", row)
        terminal["rows"] = rows
        terminal["serialized_token_recovery"] = {
            "method": "checkpoint_tokenizer_per_stream_event",
            "all_nonempty_events_map_to_one_token": token_recovery_pass,
        }
        terminal["pass"] = bool(
            token_recovery_pass
            and all(
                row["error"] is None
                and row["prompt_tokens"] == PROMPT_TOKENS
                and row["completion_tokens"] == terminal["output_tokens"]
                and row["returned_token_ids"] == terminal["output_tokens"]
                and bool(row["text"])
                for row in rows
            )
        )
        atomic_json(root / "TERMINAL.json", terminal)
        return 0 if terminal["pass"] else 72
    if args.output is None or args.arm is None or args.arm_file is None:
        parser.error("--output, --arm, and --arm-file are required for a new run")
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    args.arm_file.write_text(args.arm + "\n")

    prefix = tokens("common-prefix", COMMON_TOKENS)
    bodies = []
    for index in range(args.concurrency):
        suffix = tokens(f"suffix-{index}", PROMPT_TOKENS - COMMON_TOKENS)
        suffix[0] = 200000 + index
        bodies.append(
            {
                "model": MODEL,
                "prompt": prefix + suffix,
                "max_tokens": args.output_tokens,
                "min_tokens": args.output_tokens,
                "ignore_eos": True,
                "temperature": 0,
                "seed": 20260718,
                "stream": True,
                "stream_options": {"include_usage": True},
                "return_token_ids": True,
                "add_special_tokens": False,
            }
        )
    atomic_json(
        root / "WORKLOAD.json",
        {
            "arm": args.arm,
            "prompt_tokens": PROMPT_TOKENS,
            "output_tokens": args.output_tokens,
            "concurrency": args.concurrency,
            "shared_prefix_tokens": COMMON_TOKENS,
            "request_sha256": [
                hashlib.sha256(canonical(body)).hexdigest() for body in bodies
            ],
        },
    )
    get("/v1/models")
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                BASE + "/flush_cache",
                b"{}",
                {"Content-Type": "application/json"},
            ),
            timeout=30,
        ).read()
    except Exception as exc:
        (root / "flush_cache.error").write_text(repr(exc) + "\n")

    warmup_suffix = tokens("warmup-suffix", PROMPT_TOKENS - COMMON_TOKENS)
    warmup_suffix[0] = 199999
    warmup = dict(bodies[0])
    warmup.update(
        {
            "prompt": prefix + warmup_suffix,
            "max_tokens": 1,
            "min_tokens": 1,
            "stream": False,
        }
    )
    with post(warmup) as response:
        (root / "warmup.json").write_bytes(response.read())

    before = get("/metrics")
    (root / "metrics-before.prom").write_bytes(before)
    ready = threading.Barrier(args.concurrency + 1)
    release = threading.Barrier(args.concurrency + 1)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as pool:
        futures = [
            pool.submit(one, index, body, root, ready, release)
            for index, body in enumerate(bodies)
        ]
        ready.wait(timeout=120)
        release.wait(timeout=120)
        rows = [future.result() for future in futures]
    ended = time.monotonic()
    token_recovery_pass = recover_serialized_token_ids(rows, args.checkpoint)
    for index, row in enumerate(rows):
        atomic_json(root / f"row-{index:02d}.json", row)
    after = get("/metrics")
    (root / "metrics-after.prom").write_bytes(after)

    prompt_before = metric_sum(before, "sglang:prompt_tokens_histogram_sum")
    prompt_after = metric_sum(after, "sglang:prompt_tokens_histogram_sum")
    uncached_before = metric_sum(before, "sglang:uncached_prompt_tokens_histogram_sum")
    uncached_after = metric_sum(after, "sglang:uncached_prompt_tokens_histogram_sum")
    prompt_delta = (
        None
        if prompt_before is None or prompt_after is None
        else prompt_after - prompt_before
    )
    uncached_delta = (
        None
        if uncached_before is None or uncached_after is None
        else uncached_after - uncached_before
    )
    cached_delta = (
        None
        if prompt_delta is None or uncached_delta is None
        else prompt_delta - uncached_delta
    )
    valid = all(
        row["error"] is None
        and row["prompt_tokens"] == PROMPT_TOKENS
        and row["completion_tokens"] == args.output_tokens
        and row["returned_token_ids"] == args.output_tokens
        and bool(row["text"])
        for row in rows
    ) and token_recovery_pass
    terminal = {
        "schema_version": 1,
        "kind": "gemma4_async_result_16_token_discriminator",
        "arm": args.arm,
        "pass": valid,
        "concurrency": args.concurrency,
        "output_tokens": args.output_tokens,
        "complete_requests": sum(row["error"] is None for row in rows),
        "serialized_token_recovery": {
            "method": "checkpoint_tokenizer_per_stream_event",
            "all_nonempty_events_map_to_one_token": token_recovery_pass,
        },
        "started_monotonic_s": started,
        "ended_monotonic_s": ended,
        "batch_seconds": ended - started,
        "service_seconds_per_request": (ended - started) / args.concurrency,
        "cache": {
            "prompt_tokens_delta": prompt_delta,
            "uncached_prompt_tokens_delta": uncached_delta,
            "cached_prompt_tokens_delta": cached_delta,
        },
        "phases": {
            "ttft": finite_summary([row["ttft_seconds"] for row in rows]),
            "decode": finite_summary([row["decode_seconds"] for row in rows]),
            "end_to_end": finite_summary([row["wall_seconds"] for row in rows]),
        },
        "rows": rows,
    }
    atomic_json(root / "TERMINAL.json", terminal)
    return 0 if valid else 72


if __name__ == "__main__":
    raise SystemExit(main())
