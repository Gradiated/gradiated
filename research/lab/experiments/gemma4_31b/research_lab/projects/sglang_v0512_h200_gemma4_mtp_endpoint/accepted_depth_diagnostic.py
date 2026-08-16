#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time
import urllib.request


BASE = "http://127.0.0.1:30000"
MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
COMMON_TOKENS = 535
SEED = "gemma4-background-exact-mix-c32-20260718"
DECODE_FRACTION = 15.416948979 / 22.46439278


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


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


def post(path: str, body: dict[str, object], timeout: int = 900) -> bytes:
    request = urllib.request.Request(
        BASE + path,
        canonical(body),
        {"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=timeout).read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    prefix = tokens("common-prefix", COMMON_TOKENS)
    suffix = tokens("suffix-0", PROMPT_TOKENS - COMMON_TOKENS)
    suffix[0] = 200000
    body = {
        "model": MODEL,
        "prompt": prefix + suffix,
        "max_tokens": OUTPUT_TOKENS,
        "min_tokens": OUTPUT_TOKENS,
        "ignore_eos": True,
        "temperature": 0,
        "seed": 20260718,
        "stream": False,
        "return_token_ids": True,
        "add_special_tokens": False,
    }
    started = time.monotonic()
    raw = post("/v1/completions", body)
    elapsed = time.monotonic() - started
    response = json.loads(raw)
    usage = response.get("usage") or {}
    rows = [
        json.loads(line)
        for line in args.audit.read_text().splitlines()
        if line.strip()
    ]
    installation = [row for row in rows if row.get("event") == "installation_complete"]
    assistant = [row for row in rows if row.get("event") == "assistant_forward"]
    verify = [row for row in rows if row.get("event") == "target_verify"]
    verify_calls = sum(int(row["batch_size"]) for row in verify)
    accepted_drafts = sum(int(row["accepted_drafts_total"]) for row in verify)
    accepted_tokens = verify_calls + accepted_drafts
    assistant_ms = sum(float(row["elapsed_ms"]) for row in assistant)
    verify_ms = sum(float(row["elapsed_ms"]) for row in verify)
    verify_ms_per_call = verify_ms / verify_calls if verify_calls else None
    assistant_equivalent_target_calls = (
        assistant_ms / verify_ms_per_call if verify_ms_per_call else None
    )
    target_forward_reduction = (
        1 - verify_calls / accepted_tokens if accepted_tokens else 0.0
    )
    decode_gain_after_overhead = (
        1
        - (verify_calls + assistant_equivalent_target_calls) / accepted_tokens
        if accepted_tokens and assistant_equivalent_target_calls is not None
        else 0.0
    )
    whole_request_bound = DECODE_FRACTION * decode_gain_after_overhead
    valid = (
        bool(installation)
        and bool(assistant)
        and bool(verify)
        and usage.get("prompt_tokens") == PROMPT_TOKENS
        and usage.get("completion_tokens") == OUTPUT_TOKENS
        and accepted_tokens == OUTPUT_TOKENS
        and all(int(row["proposed_drafts_per_request"]) == 1 for row in assistant)
    )
    value = {
        "schema_version": 1,
        "status": "terminal",
        "classification": (
            "endpoint_pair_admitted"
            if valid and whole_request_bound >= 0.03
            else "close_below_three_percent_bound"
            if valid
            else "invalid_accepted_depth_diagnostic"
        ),
        "pass": valid,
        "endpoint_pair_admitted": valid and whole_request_bound >= 0.03,
        "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "service_seconds": elapsed,
        "usage": usage,
        "assistant_forward_events": len(assistant),
        "target_verify_events": len(verify),
        "verify_calls": verify_calls,
        "accepted_drafts": accepted_drafts,
        "accepted_tokens": accepted_tokens,
        "mean_accepted_depth": accepted_tokens / verify_calls if verify_calls else 0.0,
        "target_forward_reduction_fraction": target_forward_reduction,
        "assistant_elapsed_ms": assistant_ms,
        "target_verify_elapsed_ms": verify_ms,
        "assistant_equivalent_target_calls": assistant_equivalent_target_calls,
        "decode_gain_after_assistant_verify_overhead": decode_gain_after_overhead,
        "measured_decode_wall_fraction": DECODE_FRACTION,
        "whole_request_gain_bound": whole_request_bound,
        "gate_fraction": 0.03,
        "source_installation": installation,
    }
    temporary = args.output.with_suffix(".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0 if valid else 72


if __name__ == "__main__":
    raise SystemExit(main())
