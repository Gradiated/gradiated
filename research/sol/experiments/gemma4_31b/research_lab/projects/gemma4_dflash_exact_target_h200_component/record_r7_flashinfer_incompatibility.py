#!/usr/bin/env python3
"""Persist the R7 no-safe-request boundary without altering the live owner."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile


PROJECT = pathlib.Path(__file__).resolve().parent
ROOT = PROJECT / "artifacts/dflash-h200-r7-ngram-flashinfer/run"
STATUS = PROJECT / "STATUS.json"
OWNER = PROJECT / "dflash_component_direct_recovery_owner_r7.py"
ADOPTION = ROOT / "RECOVERY_R2_ADOPTION_7.json"


def atomic(path: pathlib.Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n")
        temporary = pathlib.Path(handle.name)
    json.loads(temporary.read_text()); os.replace(temporary, path)


def main() -> None:
    adoption = json.loads(ADOPTION.read_text())
    boundary = {
        "classification": "typed_retained_flashinfer_exact_runtime_incompatibility",
        "evidence": {
            "adoption": str(ADOPTION.relative_to(PROJECT)),
            "adoption_sha256": hashlib.sha256(ADOPTION.read_bytes()).hexdigest(),
            "worker_returncode": adoption["worker_returncode"],
            "ngram_science_started": adoption["attempt"]["science_started"]["ngram"],
            "runtime_message": "Gemma4 only supports trtllm_mha, triton, or intel_xpu; decode=flashinfer was rejected.",
        },
        "repair_request_withheld": True,
        "reason": "Any compatible backend changes R7's director-bound FlashInfer intervention; bound owner returns after request validation without re-entering worker 7.",
        "owner_source_sha256": hashlib.sha256(OWNER.read_bytes()).hexdigest(),
        "required_director_action": "Rebind a repairable owner and, if allowed, change the backend contract; preserve claim/owner until that authority arrives or its absolute deadline.",
    }
    atomic(ROOT / "R7_FLASHINFER_INCOMPATIBILITY_BOUNDARY.json", boundary)
    status = json.loads(STATUS.read_text())
    status.update({
        "decision": "r7_flashinfer_exact_runtime_incompatibility_retained",
        "summary": "Exact pinned SGLang rejects Gemma4 decode=flashinfer before NGRAM science; no compatible in-scope patch or owner retry entrypoint exists.",
        "r7_retained_authority_boundary": str((ROOT / "R7_FLASHINFER_INCOMPATIBILITY_BOUNDARY.json").relative_to(PROJECT)),
    })
    status["active_session"]["phase"] = "retained_exact_runtime_incompatibility_waiting_director_rebind"
    atomic(STATUS, status)
    with (PROJECT / "RESEARCH_LOG.md").open("a") as log:
        log.write("\n## 2026-07-30T03:34Z — R7 FlashInfer incompatibility retained\n\n")
        log.write("- Evidence: retrieved worker-7 terminal (`rc=75`) rejects `prefill=triton, decode=flashinfer` for Gemma4 before NGRAM science.\n")
        log.write("- Interpretation: switching to a listed compatible backend changes the director-bound FlashInfer arm; do not replay or signal an incompatible repair.\n")
        log.write("- Owner boundary: R7 validates a repair request then returns without worker-7 re-entry, so a request would strand the sole live claim. Rebind required.\n")


if __name__ == "__main__":
    main()
