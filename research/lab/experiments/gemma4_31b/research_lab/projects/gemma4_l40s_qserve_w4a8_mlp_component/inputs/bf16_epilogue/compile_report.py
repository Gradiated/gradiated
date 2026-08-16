#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()
    text = args.log.read_text(errors="replace") if args.log.exists() else ""
    resources = []
    pattern = re.compile(
        r"ptxas info\s*: Used (?P<registers>\d+) registers"
        r"(?:, used (?P<barriers>\d+) barriers)?"
        r"(?:, (?P<smem>\d+) bytes smem)?"
    )
    for match in pattern.finditer(text):
        resources.append(
            {
                key: int(value)
                for key, value in match.groupdict().items()
                if value is not None
            }
        )
    terminal = {
        "schema_version": 1,
        "classification": "compile_complete" if args.exit_code == 0 else "compile_failed",
        "pass": args.exit_code == 0,
        "exit_code": args.exit_code,
        "sm89_gencode_present": "compute_89" in text and "sm_89" in text,
        "ptxas_resources": resources,
        "log": str(args.log),
    }
    atomic(args.output, terminal)
    return 0 if terminal["pass"] else args.exit_code or 1


if __name__ == "__main__":
    raise SystemExit(main())
