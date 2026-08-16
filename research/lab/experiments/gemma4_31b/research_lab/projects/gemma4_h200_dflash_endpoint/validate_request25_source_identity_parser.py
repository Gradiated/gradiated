#!/usr/bin/env python3
"""Deterministic pre-claim gate for the hash-bound source identity parser."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import tempfile

PARSER_SENTINEL = 'if not re.match(r"^[0-9a-f]{64}\\s+", line):'
DUPLICATE_SENTINEL = 'if normalized in observed:'


def parse(binding_path: pathlib.Path, observed_path: pathlib.Path) -> dict[str, str]:
    binding = json.loads(binding_path.read_text())
    expected = {row["source_path"]: row["sha256"] for row in binding["executed_source"]}
    observed: dict[str, str] = {}
    for line in observed_path.read_text().splitlines():
        if not re.match(r"^[0-9a-f]{64}\s+", line):
            continue
        digest, path = line.split(None, 1)
        normalized = path.removeprefix("/sgl-workspace/sglang/")
        if normalized in observed:
            raise ValueError(f"duplicate installed source record: {normalized}")
        observed[normalized] = digest
    if observed != expected:
        raise ValueError(f"installed source mismatch: observed={observed!r}")
    return observed


def rejection(binding: pathlib.Path, fixture: pathlib.Path) -> str | None:
    try:
        parse(binding, fixture)
    except ValueError as exc:
        return str(exc)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--binding", type=pathlib.Path, required=True)
    parser.add_argument("--positive", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_text = source_bytes.decode()
    if PARSER_SENTINEL not in source_text or DUPLICATE_SENTINEL not in source_text:
        raise SystemExit("hash-bound parser sentinel missing")

    accepted = parse(args.binding, args.positive)
    lines = args.positive.read_text().splitlines()
    checksum_indexes = [
        index for index, line in enumerate(lines)
        if re.match(r"^[0-9a-f]{64}\s+", line)
    ]
    if len(checksum_indexes) != 8:
        raise SystemExit(f"positive fixture has {len(checksum_indexes)} checksum rows")

    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        missing = root / "missing.txt"
        missing.write_text("\n".join(
            line for index, line in enumerate(lines) if index != checksum_indexes[-1]
        ) + "\n")
        altered = root / "altered.txt"
        altered_lines = list(lines)
        altered_lines[checksum_indexes[0]] = "0" * 64 + altered_lines[checksum_indexes[0]][64:]
        altered.write_text("\n".join(altered_lines) + "\n")
        identical_duplicate = root / "identical_duplicate.txt"
        identical_duplicate.write_text(args.positive.read_text() + lines[checksum_indexes[0]] + "\n")
        conflicting_duplicate = root / "conflicting_duplicate.txt"
        conflicting_duplicate.write_text(
            args.positive.read_text() + ("0" * 64) + lines[checksum_indexes[0]][64:] + "\n"
        )
        unexpected = root / "unexpected.txt"
        unexpected.write_text(
            args.positive.read_text()
            + ("1" * 64)
            + "  /sgl-workspace/sglang/python/sglang/unexpected.py\n"
        )
        outcomes = {
            fixture.name: rejection(args.binding, fixture)
            for fixture in (missing, altered, unexpected, identical_duplicate, conflicting_duplicate)
        }

    failures = [
        name for name, reason in outcomes.items() if reason is None
    ]
    result = {
        "schema_version": 1,
        "classification": "parser_gate_failed" if failures else "parser_gate_pass",
        "hash_bound_source": str(args.source),
        "hash_bound_source_sha256": source_sha256,
        "positive_fixture_sha256": hashlib.sha256(args.positive.read_bytes()).hexdigest(),
        "accepted_records": len(accepted),
        "negative_cases": outcomes,
        "unexpectedly_accepted_negative_cases": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
