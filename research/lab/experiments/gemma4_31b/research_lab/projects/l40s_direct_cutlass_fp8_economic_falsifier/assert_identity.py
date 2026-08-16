#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = HERE.parent / "exact_shape_fp8_w4_direct_kernel_packet"

EXPECTED = {
    "START_PACKET.json": "14bed1b4e33bd2c9dde062dec800c9a04080986d7cafcb080a5831ea156a4366",
    "FINAL_STAGED_PROGRAM_AUDIT.json": "5bff874897d280a9a16318a854825ae47dbd936ef52c3341234d663065b77f15",
    "STAGED_MANIFEST.json": "4b7fec791c1bd57686c3431e795e55a133adbfdd3a19381807dd769cd651f5e0",
    "direct_fp8_kernel.py": "4c285c94daf032a56c0de2136badffab845503fa710dbca12027e6a345b92667",
    "remote_stage.sh": "b1504265ab0131df0a1144292b0e3cbc3b6d9c9f6790c8d61ab4a1bab5a9cbc9",
    "SOURCE_MANIFEST.json": "a65a36ef7abec2765c301d5508e74dd0d212bc3e3083e01a18abf577ee61149c",
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

actual = {name: sha(PACKET / name) for name in EXPECTED}
start = json.loads((PACKET / "START_PACKET.json").read_text())
audit = json.loads((PACKET / "FINAL_STAGED_PROGRAM_AUDIT.json").read_text())
project = (HERE / "PROJECT.md").read_text()

checks = {
    "all_packet_hashes": actual == EXPECTED,
    "packet_pass": start.get("pass") is True,
    "audit_pass": audit.get("pass") is True,
    "model": start["identity"]["model_geometry"] in project,
    "runtime_image": start["identity"]["runtime_image"] in project,
    "vllm": start["identity"]["vllm"] in project,
    "gpu": start["identity"]["gpu"] == "NVIDIA L40S" and "NVIDIA L40S" in project,
    "compute_capability": start["identity"]["compute_capability"] == [8, 9] and "SM89" in project,
    "program": start["identity"]["program_sha256"] == actual["direct_fp8_kernel.py"],
    "wrapper": start["identity"]["wrapper_sha256"] == actual["remote_stage.sh"],
    "one_allocation_no_repair": start["budgets"]["allocation_count"] == 1 and start["budgets"]["repair_count"] == 0,
    "budgets": start["budgets"]["wall_clock_minutes"] == 38 and start["budgets"]["provider_exposure_minutes"] == 26 and start["budgets"]["spend_usd"] == 0.42,
    "w4_omitted": start["w4"]["included"] is False and "W4 is not authorized" in project,
}
result = {
    "schema_version": 1,
    "type": "l40s_direct_cutlass_fp8_director_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "authoritative_hashes": actual,
    "identity": start["identity"],
    "budgets": start["budgets"],
}
out = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(out)
print(sha(out))
raise SystemExit(0 if result["pass"] else 1)
