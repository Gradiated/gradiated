#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
CONSERVATIVE_CUMULATIVE_SPEND_USD = 0.80


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


terminal = json.loads((ARTIFACTS / "FINAL_TERMINAL.json").read_text())
terminal.update(
    {
        "classification": "reconstruction_or_coherence_reject",
        "actual_spend_usd": CONSERVATIVE_CUMULATIVE_SPEND_USD,
        "retrieved_factors": {
            "path": str(ARTIFACTS / "recovery-factors.tar"),
            "bytes": (ARTIFACTS / "recovery-factors.tar").stat().st_size,
            "sha256": "6c9760dfc4d05186336f0bc2618218a1d6a83ac02611f1c28e2b03a9dcf92021",
            "manifest_sha256": "7b6d35d71aedfb7872e1c1440d1ce5e4f8a22e90d5b754d9223c6aa4d12baaab",
            "all_60_manifest_rows_verified": True,
        },
        "retrieval_reconciliation": {
            "classification_before_repair": "typed_external_blocker",
            "defect": "guest tar could not read root-owned factor files after the scientific terminal",
            "repair": "retrieval-only re-claim; sudo archive; local archive, manifest, size, and per-file hash verification",
            "scientific_stage_replayed": False,
            "c32_candidate_started": False,
            "reconciled_utc": dt.datetime.now(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        },
    }
)
atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)

status = json.loads((HERE / "STATUS.json").read_text())
status.update(
    {
        "status": "completed",
        "actual_spend_usd": CONSERVATIVE_CUMULATIVE_SPEND_USD,
        "active_session": None,
        "summary": "reconstruction_or_coherence_reject",
        "next_action": "Director should close the fixed width-16,384 rank-256 recovery representation; held-out MLP reconstruction passed but all four preregistered coherence rows failed, so c32 was not invoked.",
        "terminal_artifact": str(ARTIFACTS / "FINAL_TERMINAL.json"),
        "last_result_classification": "reconstruction_or_coherence_reject",
    }
)
atomic(HERE / "STATUS.json", status)
