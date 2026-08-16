#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
MECH_DIR = LAB / "projects" / "h100_w4_marlin_exact_shape_mechanism"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

campaign = (LAB / "CAMPAIGN.md").read_text()
project = (HERE / "PROJECT.md").read_text()
mechanism = json.loads((MECH_DIR / "MECHANISM.json").read_text())
mechanism_status = json.loads((MECH_DIR / "STATUS.json").read_text())
identity = mechanism["immutable_inputs"]
model = re.search(r"`(google/gemma-4-31B-it)` at revision `([0-9a-f]{40})`", campaign)
image = re.search(r"docker\.io/vllm/vllm-openai:gemma4@sha256:[0-9a-f]{64}", json.dumps(mechanism))
checks = {
    "campaign_model_found": model is not None,
    "mechanism_terminal_hash": sha(MECH_DIR / "MECHANISM.json") == mechanism_status["terminal_artifact_sha256"],
    "mechanism_ready": mechanism["decision"] == "content_bound_h100_w4_direct_falsifier" and mechanism["answer"]["program_ready"] is True,
    "cpu_contract": mechanism["local_evidence"]["cpu_contract_pass"] is True and sha(MECH_DIR / "CPU_CONTRACT.json") == mechanism["local_evidence"]["cpu_contract_sha256"],
    "program_hash": sha(MECH_DIR / "h100_w4_marlin_falsifier.py") == mechanism["local_evidence"]["program_sha256"],
    "campaign_matches_mechanism": model is not None and identity["model_geometry"] == f"{model.group(1)}@{model.group(2)}",
    "image_bound": image is not None and image.group(0) == identity["runtime_image"],
    "brief_identity": identity["model_geometry"] in project and identity["runtime_image"] in project,
    "h100_identity": "NVIDIA H100 80GB HBM3" in identity["accelerator"] and "capability 9.0" in project,
    "geometry": len(identity["shapes"]) == 6 and identity["m_values"] == [8, 16, 32, 3679],
    "ceiling": str(identity["planning_ceiling_seconds_per_request"]) in project,
    "sentinel_then_sweep": "sliding-QKV M8 sentinel" in project and "exact 24 rows" in project,
    "adjacent_trigger": "W4_SWEEP_PASS_AND_SETUP_DOMINATES_AND_HEAD_READY" in project,
    "budgets": "20 minutes" in project and "0.34 H100 GPU-hours" in project and "`$1.30`" in project,
    "one_allocation": "One allocation" in project and "zero repair/restart" in project,
}
result = {
    "schema_version": 1,
    "type": "h100_w4_marlin_director_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "authoritative_hashes": {
        "CAMPAIGN.md": sha(LAB / "CAMPAIGN.md"),
        "MECHANISM.json": sha(MECH_DIR / "MECHANISM.json"),
        "STATUS.json": sha(MECH_DIR / "STATUS.json"),
        "CPU_CONTRACT.json": sha(MECH_DIR / "CPU_CONTRACT.json"),
        "h100_w4_marlin_falsifier.py": sha(MECH_DIR / "h100_w4_marlin_falsifier.py"),
        "PROJECT.md": sha(HERE / "PROJECT.md"),
    },
    "identity": identity,
}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["pass"] else 1)
