#!/usr/bin/env python3
"""Record the first R7 retained repair boundary without touching its owner."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile


PROJECT = pathlib.Path(__file__).resolve().parent
ROOT = PROJECT / "artifacts/dflash-h200-r7-ngram-flashinfer/run"
STATUS = PROJECT / "STATUS.json"


def atomic(path: pathlib.Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n")
        tmp = pathlib.Path(handle.name)
    json.loads(tmp.read_text()); os.replace(tmp, path)


def main() -> None:
    adoption = json.loads((ROOT / "RECOVERY_R2_ADOPTION_7.json").read_text())
    ready = next((ROOT / ".repair-handshakes").glob("*/REPAIR_READY.json"))
    repair = json.loads(ready.read_text())
    status = json.loads(STATUS.read_text())
    status.update({
        "decision": "r7_retained_repair_ready",
        "summary": "R7 worker 7 entered NGRAM only; server startup defect before NGRAM science marker is retained for classify repair.",
        "r7_repair_boundary": {
            "classification": adoption["attempt"]["classification"], "worker_generation": 7,
            "retry_scope": "classify", "science_started": adoption["attempt"]["science_started"],
            "repair_id": repair["repair_id"], "ready": str(ready.relative_to(PROJECT)),
        },
    })
    status["active_session"]["phase"] = "retained_repair_ready_after_ngram_worker_7"
    atomic(STATUS, status)
    with (PROJECT / "RESEARCH_LOG.md").open("a") as log:
        log.write("\n## 2026-07-30T03:32Z — R7 NGRAM-only retained repair\n\n")
        log.write("- Action: claimed the bound warm H200 at 03:29:46Z and launched durable R7 owner PID 508978.\n")
        log.write("- Evidence: worker 7 used `classify` only; returned `server_startup_defect`, with NGRAM science marker false and archived snapshot `f7779a...`.\n")
        log.write("- Interpretation: no NGRAM scientific sample was consumed; AR/DFlash remain frozen. Owner heartbeat and repair handshake remain live.\n")


if __name__ == "__main__":
    main()
