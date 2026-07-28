#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import sys


root = Path(sys.argv[2])
stdout = root / "stdout.log"
stderr = root / "stderr.log"
if "packed_m384_streaming_int32_indices_required" not in stderr.read_text():
    raise RuntimeError("expected_host_dtype_guard_missing")
if "packed_m384_streaming_cluster.cuda.o" not in stdout.read_text():
    raise RuntimeError("compiled_extension_evidence_missing")

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

record = {
    "schema_version": 1,
    "classification": "pre_science_host_dtype_guard",
    "candidate_cuda_invocation_started": False,
    "reason": "extension rejected manifest-bound fixture kv_indices=int64 before any kernel launch",
    "stdout_sha256": digest(stdout),
    "stderr_sha256": digest(stderr),
}
(root / "REPAIR_TERMINAL.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
(root / "INVOCATION_STATE.json").write_text(json.dumps({
    "schema_version": 1,
    "phase": "pre_science",
    "candidate_cuda_invocation_started": False,
    "reclassified_from": "science_started",
    "reclassification": record,
}, indent=2, sort_keys=True) + "\n")
