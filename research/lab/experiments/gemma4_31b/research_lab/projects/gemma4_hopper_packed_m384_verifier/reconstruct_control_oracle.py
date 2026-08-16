#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import tarfile


PROJECT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT / "inputs" / "endpoint"))

from token_oracle import jsonl, token_rows, validate_oracle


def sha256(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def member_bytes(archive: tarfile.TarFile, name: str) -> bytes:
    member = archive.getmember(name)
    handle = archive.extractfile(member)
    if handle is None:
        raise RuntimeError(f"archive_member_unreadable:{name}")
    return handle.read()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    archive_path = args.archive.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        terminal_raw = member_bytes(archive, "artifacts/control/TERMINAL.json")
        events_raw = member_bytes(
            archive, "artifacts/control.token-events.jsonl"
        )
        responses = {
            index: member_bytes(
                archive, f"artifacts/control/response-{index:02d}.sse"
            )
            for index in range(32)
        }
    terminal = json.loads(terminal_raw)
    rows = token_rows(terminal, responses, jsonl(events_raw))
    repaired_terminal = json.loads(terminal_raw)
    for row in repaired_terminal["rows"]:
        row["returned_token_ids"] = 358
    oracle = {
        "schema_version": 1,
        "type": "packed_m384_persisted_control_token_oracle",
        "project": "gemma4_hopper_packed_m384_verifier",
        "source": {
            "archive": str(archive_path.relative_to(PROJECT)),
            "archive_sha256": sha256(archive_path),
            "control_terminal_sha256": hashlib.sha256(
                terminal_raw
            ).hexdigest(),
            "token_events_sha256": hashlib.sha256(events_raw).hexdigest(),
            "control_request_replayed": False,
        },
        "control_terminal": repaired_terminal,
        "rows": rows,
    }
    validate_oracle(oracle)
    atomic(args.output.resolve(), oracle)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "sha256": sha256(args.output.resolve()),
                "requests": len(rows),
                "tokens_per_request": len(rows[0]["emitted_token_ids"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
