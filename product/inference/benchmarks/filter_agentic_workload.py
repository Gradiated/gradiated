#!/usr/bin/env python3
"""Deduplicate a workload and exclude IDs assigned to earlier partitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def session_ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8") as stream:
        return {
            str(json.loads(line)["session_id"])
            for line in stream
            if line.strip()
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, action="append", default=[])
    args = parser.parse_args()

    excluded: set[str] = set()
    for path in args.exclude:
        excluded.update(session_ids(path))
    seen: set[str] = set()
    kept: list[dict[str, object]] = []
    with args.input.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            identifier = str(record["session_id"])
            if identifier in excluded or identifier in seen:
                continue
            seen.add(identifier)
            kept.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for record in kept:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "input": str(args.input),
                "output": str(args.output),
                "excluded_session_ids": len(excluded),
                "sessions": len(kept),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
