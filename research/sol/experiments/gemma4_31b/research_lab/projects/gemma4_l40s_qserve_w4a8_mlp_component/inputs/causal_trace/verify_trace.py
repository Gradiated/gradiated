#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    failures = []
    for item in manifest["files"]:
        path = args.root / item["path"]
        if not path.is_file():
            failures.append({"path": item["path"], "reason": "missing"})
            continue
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != item["sha256"]:
            failures.append(
                {
                    "path": item["path"],
                    "reason": "sha256",
                    "expected": item["sha256"],
                    "observed": observed,
                }
            )
    result = {"schema_version": 1, "pass": not failures, "failures": failures}
    print(json.dumps(result, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
