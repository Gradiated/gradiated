#!/usr/bin/env python3
"""Validate the immutable c32 runner and mark submission immediately before exec."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import tempfile

RUNNER_SHA256 = "8672802c73137910c28e3c73be7b7f1c6152acc5899279cd8d36e3fd82783c03"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_exclusive(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--arm", choices=("ar", "dflash", "ngram"), required=True)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--marker-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if sha256(args.runner) != RUNNER_SHA256:
        raise SystemExit("bound c32 runner digest mismatch")
    if args.output.exists():
        raise SystemExit("c32 output generation already exists")
    marker = args.marker_root / f"{args.arm}.SCIENCE_STARTED.json"
    atomic_exclusive(
        marker,
        {
            "schema_version": 1,
            "arm": args.arm,
            "generation": args.generation,
            "runner_sha256": RUNNER_SHA256,
            "historical_request_25_replayed": False,
            "fresh_workload_generation": True,
            "marker_semantics": (
                "Identity and runtime health passed; the immutable runner is about "
                "to submit its first fresh request."
            ),
        },
    )
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(args.runner),
            "--output",
            str(args.output),
            "--arm",
            args.arm,
        ],
    )
    return 99


if __name__ == "__main__":
    raise SystemExit(main())
