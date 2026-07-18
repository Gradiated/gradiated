#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = HERE.parent / "h100_direct_fp8_linear_packet"
EXPECTED = {
    "START_PACKET.json": "f6f467fedd60e56cf1a3718d4bdd12941fe7a52afcc7866786f9f428e835c87c",
    "BEHAVIORAL_AUDIT.json": "2c4de127d7596a323df4f38ce95843d245e2c3c6dcbc9232fe9958abd8d0f6a6",
    "STAGED_MANIFEST.json": "8a35a2574c58a541ba650e28e253d5ad952f2c4eb69f8bd06678d782f3ce3151",
    "h100_direct_fp8_kernel.py": "5b949a02bbc5eed86637103ee9f07dcad1bda2feb784f92629ef30977172ca5c",
    "remote_stage.sh": "81f0fd9c1077a97e03795be178b78cee4ca8ab46d9ce6dd20a1b6947b6bee41f",
    "SOURCE_MANIFEST.json": "e6a1e2752c38dc53a1859d7945a7d7573fa276a3ccab7eb6b72889cdae5e29ea",
    "h100_contract.py": "4966dbbd51d46969e71ea20983fd8023267b3bc953bbbf6467a276280ed7bfbd",
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

actual = {name: sha(PACKET / name) for name in EXPECTED}
packet = json.loads((PACKET / "START_PACKET.json").read_text())
audit = json.loads((PACKET / "BEHAVIORAL_AUDIT.json").read_text())
project = (HERE / "PROJECT.md").read_text()
checks = {
    "all_packet_hashes": actual == EXPECTED,
    "packet_pass": packet.get("pass") is True,
    "audit_pass": audit.get("pass") is True,
    "model": packet["identity"]["model_geometry"] in project,
    "image": packet["identity"]["runtime_image"] in project,
    "vllm": packet["identity"]["vllm"] in project,
    "gpu": packet["identity"]["gpu"] in project and packet["identity"]["compute_capability"] == [9, 0],
    "program": packet["identity"]["program_sha256"] == actual["h100_direct_fp8_kernel.py"],
    "wrapper": packet["identity"]["wrapper_sha256"] == actual["remote_stage.sh"],
    "one_allocation_no_repair": packet["budgets"]["allocation_count"] == 1 and packet["budgets"]["repair_count"] == 0,
    "provider_budget": packet["budgets"]["provider_exposure_minutes"] == 20 and packet["budgets"]["spend_usd_max"] == 1.3,
    "rows": "exactly 24 rows" in project and "M8/M16/M32/M3679" in project,
    "ceiling": "0.5479752315195353" in project,
}
result = {
    "schema_version": 1,
    "type": "h100_direct_fp8_linear_director_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "authoritative_hashes": actual,
    "identity": packet["identity"],
    "packet_budgets": packet["budgets"],
}
out = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(out)
print(sha(out))
raise SystemExit(0 if result["pass"] else 1)
