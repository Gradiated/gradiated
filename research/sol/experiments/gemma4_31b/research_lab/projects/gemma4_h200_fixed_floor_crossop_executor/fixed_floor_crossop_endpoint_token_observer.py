#!/usr/bin/env python3
"""Fail-closed observer for the immutable, already-consumed control SSE."""
from __future__ import annotations
import argparse, hashlib, json, pathlib

def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--control-root", type=pathlib.Path, required=True)
    p.add_argument("--expected-terminal-sha256", required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    a = p.parse_args()
    terminal = a.control_root / "TERMINAL.json"
    rows = []
    if not terminal.exists() or digest(terminal) != a.expected_terminal_sha256:
        atomic(a.output, {"classification": "immutable_control_identity_mismatch", "pass": False})
        return 2
    for sse in sorted(a.control_root.glob("response-*.sse")):
        ids = []
        events = 0
        for line in sse.read_bytes().splitlines():
            if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
                continue
            events += 1
            item = json.loads(line[6:])
            choice = (item.get("choices") or [{}])[0]
            ids.extend(choice.get("token_ids") or [])
        rows.append({"path": sse.name, "sha256": digest(sse), "sse_events": events, "observed_token_ids": ids})
    passed = len(rows) == 32 and all(len(row["observed_token_ids"]) == 358 for row in rows)
    atomic(a.output, {"schema_version": 1, "classification": "immutable_control_sse_token_observer", "pass": passed, "rows": rows, "provenance": "only persisted response-*.sse; no tokenizer decode/reencode"})
    return 0 if passed else 72

if __name__ == "__main__":
    raise SystemExit(main())
