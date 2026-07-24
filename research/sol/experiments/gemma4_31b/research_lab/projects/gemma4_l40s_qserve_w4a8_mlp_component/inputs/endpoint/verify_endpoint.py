#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    failures = []
    for row in manifest["files"]:
        path = args.root / row["name"]
        observed = sha256(path) if path.is_file() else None
        if observed != row["sha256"]:
            failures.append({"name": row["name"], "observed": observed})
    print(json.dumps({"pass": not failures, "failures": failures}))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
