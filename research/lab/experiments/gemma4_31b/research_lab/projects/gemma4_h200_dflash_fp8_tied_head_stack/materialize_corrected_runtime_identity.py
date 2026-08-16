#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


ORIGINAL_SHA256 = "f9845ea6b80a39ba99486842d15e64eabc84713a63daf16470453b395c13c16e"
SOURCE_PATH = (
    "python/sglang/srt/speculative/triton_ops/dflash_accept_bonus.py"
)
FALSE_SHA256 = (
    "422ffbd00b54913f3d9c14d2596ffd79e51800b6565dc0de78603a36dbd6fd4e"
)
CORRECT_SHA256 = (
    "422ffbd00b54913f3d9c14d2596ffd79e51800b6565dc0de78603a36dbd6fdce"
)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    observed = digest(args.original)
    if observed != ORIGINAL_SHA256:
        raise RuntimeError(
            f"original runtime binding drifted: {observed} != {ORIGINAL_SHA256}"
        )
    value = json.loads(args.original.read_text())
    sources = value["runtime_source"]["dflash_sources"]
    if sources[SOURCE_PATH] != FALSE_SHA256:
        raise RuntimeError(
            f"unexpected original source digest: {sources[SOURCE_PATH]}"
        )
    sources[SOURCE_PATH] = CORRECT_SHA256
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
