#!/usr/bin/env python3
"""Atomically record the detached controller identity after R7 launch."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile


PROJECT = pathlib.Path(__file__).resolve().parent
STATE = PROJECT / "artifacts/dflash-h200-r7-ngram-flashinfer/OWNER_STATE_R7.json"
STATUS = PROJECT / "STATUS.json"
BINDING = PROJECT / "artifacts/dflash-h200-r7-ngram-flashinfer/EXECUTION_BINDING_R7.json"


def atomic(path: pathlib.Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n")
        tmp = pathlib.Path(handle.name)
    json.loads(tmp.read_text()); os.replace(tmp, path)


def main() -> None:
    owner = json.loads(STATE.read_text())
    binding = json.loads(BINDING.read_text())
    status = json.loads(STATUS.read_text())
    status.update({
        "actual_spend_usd": 12.648691452930557,
        "claim_allowed": False,
        "active_session": {
            "bench_id": binding["bench_id"], "claim_generation": binding["claimed_at"],
            "binding": str(BINDING.relative_to(PROJECT)),
            "binding_sha256": __import__("hashlib").sha256(BINDING.read_bytes()).hexdigest(),
            "artifact_root": str((PROJECT / "artifacts/dflash-h200-r7-ngram-flashinfer/run").resolve()),
            "unit": str(STATE.resolve()), "pid": owner["pid"], "start_ticks": owner["start_ticks"],
            "unit_manager": "pid", "deadline_utc": binding["owner_deadline_utc"],
            "phase": "ngram_only_owner_dispatched",
        },
        "decision": "r7_ngram_flashinfer_dispatched",
    })
    atomic(STATUS, status)


if __name__ == "__main__":
    main()
