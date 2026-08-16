#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
FILES = {
    LAB / "h100_direct_fp8_linear_falsifier/artifacts/RECONCILED_TERMINAL.json": "26cace1bfa370e3b578935e44c16beeb7ec396d707d8b08e3253bd19ba4f6756",
    LAB / "h100_direct_fp8_live_program_audit/AUDIT.json": "005753bbbb5427f282d9bc191ad4031d81e8ab181496aac328c82ab007767a42",
    LAB / "h100_direct_fp8_linear_packet/START_PACKET.json": "f6f467fedd60e56cf1a3718d4bdd12941fe7a52afcc7866786f9f428e835c87c",
    LAB / "gemma_l40s_parallel_lm_head_measurement_final/artifacts/gemma-l40s-head-final-20260717t065653z/summary.json": "4f2f5162791b1c5643e9ebe4608e8b7583d5c3713216ec5f75d49748ddf0d15b",
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

actual = {str(path): sha(path) for path in FILES}
expected = {str(path): digest for path, digest in FILES.items()}
terminal = json.loads((LAB / "h100_direct_fp8_linear_falsifier/artifacts/RECONCILED_TERMINAL.json").read_text())
packet = json.loads((LAB / "h100_direct_fp8_linear_packet/START_PACKET.json").read_text())
project = (HERE / "PROJECT.md").read_text()
checks = {
    "all_hashes": actual == expected,
    "one_valid_row": terminal["primary_stage"]["decision_bearing_row_count"] == 1 and terminal["primary_stage"]["result_pass"] is True,
    "no_aggregate": terminal["conditional_stage"]["ran"] is False and terminal["conditional_stage"]["actual_row_count"] == 0,
    "cleanup": terminal["cleanup"]["pass"] is True and terminal["cleanup"]["final_instance_count"] == 0 and terminal["cleanup"]["final_disk_count"] == 0,
    "packet_pass": packet.get("pass") is True,
    "model": packet["identity"]["model_geometry"] in project,
    "image": packet["identity"]["runtime_image"] in project,
    "gpu": packet["identity"]["gpu"] in project and packet["identity"]["compute_capability"] == [9, 0],
    "single_correction": "one material correction" in project and "No further correction" in project,
    "scored_unchanged": "separate unscored" in project,
    "adjacent_trigger": "H100_LINEAR_SWEEP_PASS_AND_SETUP_DOMINATES" in project,
    "budgets": "18 minutes" in project and "0.31 H100 GPU-hours" in project and "`$1.20`" in project,
}
result = {"schema_version": 1, "type": "h100_direct_fp8_telemetry_corrected_director_identity_assertion", "pass": all(checks.values()), "checks": checks, "authoritative_hashes": actual, "identity": packet["identity"]}
out = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(out)
print(sha(out))
raise SystemExit(0 if result["pass"] else 1)
