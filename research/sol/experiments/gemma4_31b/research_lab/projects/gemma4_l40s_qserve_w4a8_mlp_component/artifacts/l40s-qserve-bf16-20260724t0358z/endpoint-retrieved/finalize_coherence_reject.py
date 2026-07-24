#!/usr/bin/env python3
from __future__ import annotations

import collections
import json
import os
import pathlib
import sys
import time


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    output = pathlib.Path(sys.argv[1])
    coherence = json.loads(
        (output / "coherence" / "COHERENCE_TERMINAL.json").read_text()
    )
    events = []
    for line in (output / "qserve-events.jsonl").read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    counts = collections.Counter(event["event"] for event in events)
    request_start = json.loads((output / "INVOCATION_STATE.json").read_text())
    terminal = {
        "schema_version": 1,
        "classification": "endpoint_reject",
        "pass": False,
        "reason": "exact-checkpoint coherence failed on all three prompts",
        "coherence": coherence,
        "candidate_event_counts": dict(sorted(counts.items())),
        "candidate_path_observed": counts["candidate_decode_path"] > 0,
        "invocation_state": request_start,
        "c32": {
            "started": request_start["endpoint_request_started"],
            "classification": "not_run_coherence_gate",
        },
        "server_preserved": True,
        "epoch": time.time(),
    }
    atomic(output / "ENDPOINT_TERMINAL.json", terminal)
    atomic(
        output / "WORKER_TERMINAL.json",
        {
            "schema_version": 1,
            "classification": "endpoint_reject",
            "message": terminal["reason"],
            "scientific_terminal": "ENDPOINT_TERMINAL.json",
            "epoch": time.time(),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
