#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import sys


root = Path(sys.argv[2])
stdout = root / "stdout.log"
stderr = root / "stderr.log"
invocation = json.loads((root / "INVOCATION_STATE.json").read_text())
if not invocation.get("candidate_cuda_invocation_started"):
    raise RuntimeError("candidate_submission_evidence_missing")
if "CUDA error: unspecified launch failure" not in stderr.read_text():
    raise RuntimeError("expected_cuda_launch_failure_missing")

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

record = {
    "schema_version": 1,
    "classification": "candidate_cuda_launch_failure_after_submission",
    "scientific_result": False,
    "replay_permitted": False,
    "reason": "exact corrected fixture reached candidate CUDA submission then failed at torch.cuda.synchronize without an interpretable component row",
    "invocation": invocation,
    "stdout_sha256": digest(stdout),
    "stderr_sha256": digest(stderr),
}
(root / "RUNTIME_INCOMPATIBILITY.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
(root / "REPAIR_TERMINAL.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
