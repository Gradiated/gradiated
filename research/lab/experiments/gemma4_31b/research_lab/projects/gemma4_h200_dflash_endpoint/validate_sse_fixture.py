#!/usr/bin/env python3
"""Validate the immutable depth-4 /generate SSE fixture with the live decoder."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from dflash_endpoint_runner import OUTPUT_TOKENS, PROMPT_TOKENS, decode_sse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workload = json.loads((args.fixture / "WORKLOAD.json").read_text())
    rows = []
    for index in range(workload["concurrency"]):
        response = args.fixture / f"response-{index:02d}.sse"
        raw = response.read_bytes()
        text, token_ids, meta = decode_sse(raw.splitlines(keepends=True))
        rows.append({
            "index": index,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_token_ids": token_ids,
            "returned_token_ids": len(token_ids),
            "finish_reason": meta.get("finish_reason"),
            "prompt_tokens": meta.get("prompt_tokens"),
            "completion_tokens": meta.get("completion_tokens"),
            "cached_tokens": meta.get("cached_tokens"),
            "usage_fields_present": all(key in meta for key in ("prompt_tokens", "completion_tokens", "cached_tokens")),
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        })
    passed = (len(rows) == 32 and all(row["returned_token_ids"] == OUTPUT_TOKENS and row["prompt_tokens"] == PROMPT_TOKENS and row["completion_tokens"] == OUTPUT_TOKENS and row["finish_reason"] and row["usage_fields_present"] for row in rows))
    value = {"schema_version": 1, "classification": "offline_sse_decoder_pass" if passed else "offline_sse_decoder_reject", "fixture": str(args.fixture), "fixture_workload_sha256": hashlib.sha256((args.fixture / "WORKLOAD.json").read_bytes()).hexdigest(), "complete_requests": sum(row["returned_token_ids"] == OUTPUT_TOKENS and row["finish_reason"] and row["usage_fields_present"] for row in rows), "expected_complete_requests": 32, "output_tokens": OUTPUT_TOKENS, "rows": rows, "pass": passed}
    tmp = args.output.with_suffix(args.output.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(args.output)
    return 0 if passed else 72


if __name__ == "__main__":
    raise SystemExit(main())
