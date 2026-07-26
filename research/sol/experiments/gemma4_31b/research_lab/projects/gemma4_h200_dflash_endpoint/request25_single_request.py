#!/usr/bin/env python3
"""Submit exactly the bound request-25 body once."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import time
import urllib.request

from dflash_endpoint_runner import COMMON_TOKENS, OUTPUT_TOKENS, PROMPT_TOKENS, canonical, tokens

REQUEST_INDEX = 25
REQUEST_SEMANTIC_SHA256 = "ee2edfa7a9ff571b0268966f506c4cb868868ab880ac87c2684b055d48a0e150"
REQUEST_INPUT_IDS_SHA256 = "51a23cdfb44941cb799a80c7ca3fd7f859e8558405f70976d1f8508703f6b360"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:30000")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--science-started", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    prefix = tokens("common-prefix", COMMON_TOKENS)
    suffix = tokens(
        f"suffix-{REQUEST_INDEX}", PROMPT_TOKENS - COMMON_TOKENS
    )
    suffix[0] = 200000 + REQUEST_INDEX
    body = {
        "input_ids": prefix + suffix,
        "sampling_params": {
            "max_new_tokens": OUTPUT_TOKENS,
            "min_new_tokens": OUTPUT_TOKENS,
            "ignore_eos": True,
            "temperature": 0,
            "sampling_seed": 20260718,
        },
        "stream": True,
    }
    semantic_sha256 = hashlib.sha256(canonical(body)).hexdigest()
    input_ids_sha256 = hashlib.sha256(canonical(body["input_ids"])).hexdigest()
    if semantic_sha256 != REQUEST_SEMANTIC_SHA256:
        raise RuntimeError(f"request semantic digest mismatch: {semantic_sha256}")
    if input_ids_sha256 != REQUEST_INPUT_IDS_SHA256:
        raise RuntimeError(f"request input digest mismatch: {input_ids_sha256}")

    atomic(
        args.science_started,
        {
            "schema_version": 1,
            "started_at_utc": datetime.datetime.now(datetime.UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "request_index": REQUEST_INDEX,
            "request_semantic_sha256": semantic_sha256,
            "request_input_ids_sha256": input_ids_sha256,
            "submission_count": 1,
        },
    )
    started = time.monotonic()
    raw = bytearray()
    with urllib.request.urlopen(
        urllib.request.Request(
            args.base + "/generate",
            canonical(body),
            {"Content-Type": "application/json"},
        ),
        timeout=300,
    ) as response:
        for chunk in response:
            raw.extend(chunk)
    atomic(
        args.output,
        {
            "schema_version": 1,
            "request_index": REQUEST_INDEX,
            "request_semantic_sha256": semantic_sha256,
            "request_input_ids_sha256": input_ids_sha256,
            "submission_count": 1,
            "response_bytes": len(raw),
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "wall_seconds": time.monotonic() - started,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
