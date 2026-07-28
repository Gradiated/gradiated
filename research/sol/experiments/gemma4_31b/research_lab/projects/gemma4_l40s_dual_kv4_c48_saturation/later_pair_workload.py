#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4_214
OUTPUT_TOKENS = 358
SHARED_PREFIX_TOKENS = 535
SEED = "gemma4-background-exact-mix-c32-20260718"
ALLOWED_CONCURRENCY = (32, 48)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def token_ids(label: str, count: int) -> list[int]:
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


def request_bodies(concurrency: int) -> list[dict]:
    if concurrency not in ALLOWED_CONCURRENCY:
        raise ValueError(f"concurrency must be one of {ALLOWED_CONCURRENCY}")
    prefix = token_ids("common-prefix", SHARED_PREFIX_TOKENS)
    bodies = []
    for index in range(concurrency):
        suffix = token_ids(
            f"suffix-{index}", PROMPT_TOKENS - SHARED_PREFIX_TOKENS
        )
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
    return bodies


def workload_identity(concurrency: int) -> dict:
    bodies = request_bodies(concurrency)
    return {
        "concurrency": concurrency,
        "intended_shared_prefix_fraction": SHARED_PREFIX_TOKENS / PROMPT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "prompt_tokens": PROMPT_TOKENS,
        "request_sha256": [
            hashlib.sha256(canonical(body)).hexdigest() for body in bodies
        ],
        "shared_prefix_tokens": SHARED_PREFIX_TOKENS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, choices=ALLOWED_CONCURRENCY)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--requests-jsonl", type=Path)
    args = parser.parse_args()

    identity = workload_identity(args.concurrency)
    supplied = json.loads(args.identity.read_text())
    if canonical(identity) != canonical(supplied):
        raise SystemExit("locked_workload_identity_mismatch")

    if args.requests_jsonl is not None:
        if args.requests_jsonl.exists():
            raise SystemExit("requests_output_must_not_exist")
        args.requests_jsonl.write_text(
            "".join(
                json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n"
                for body in request_bodies(args.concurrency)
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
