#!/usr/bin/env python3
"""Convert the bound request payload array into lab-endpoint-pair JSONL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payloads", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payloads = json.loads(args.payloads.read_text())
    identity = json.loads(args.identity.read_text())
    expected = identity["request_sha256"]
    if not isinstance(payloads, list) or len(payloads) != 32:
        raise RuntimeError("exact_32_payloads_required")
    if [hashlib.sha256(canonical(row)).hexdigest() for row in payloads] != expected:
        raise RuntimeError("payload_identity_mismatch")
    rows = [
        json.dumps(
            {"request_id": f"c32-{index:02d}", "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
        )
        for index, payload in enumerate(payloads)
    ]
    atomic(args.output, ("\n".join(rows) + "\n").encode())
    print(json.dumps({"rows": 32, "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
