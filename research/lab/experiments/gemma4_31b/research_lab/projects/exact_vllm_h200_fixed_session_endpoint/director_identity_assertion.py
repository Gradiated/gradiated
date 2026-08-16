#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(relative):
    path = (HERE / relative).resolve()
    return path, json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


start_path, start = load("../sglang_gemma4_exact_precreate_binding/START_PACKET.json")
checkpoint_path, checkpoint = load("../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json")
trace_path, trace = load("../gemma_exact_cache_trace_contract/TRACE_PACKET.json")
gate_path, gate = load("../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json")
prior_runner = (HERE / "../exact_h200_vllm_baseline_shared_runner/gemma_exact_vllm_runner.py").resolve()
prior_owner = (HERE / "../exact_h200_vllm_baseline_shared_runner/vllm_h200_owner.py").resolve()
session_staging = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/session_staging.py")
brief_path = HERE / "PROJECT.md"
brief = brief_path.read_text()
model, revision = start["identities"]["model"].split("@", 1)
vllm_image = start["identities"]["vllm_control"]["image"]
sglang_image = start["identities"]["sglang"]["image_manifest"]
index = next(row["sha256"] for row in checkpoint["files"] if row["path"] == "model.safetensors.index.json")
checks = {
    "checkpoint_pass": checkpoint["pass"] is True,
    "model": checkpoint["model"] == model == trace["identity"]["model"],
    "revision": checkpoint["revision"] == revision == trace["identity"]["revision"] == gate["identities"]["revision"],
    "index": index == trace["identity"]["checkpoint_index_sha256"],
    "vllm_image": vllm_image == trace["identity"]["runtime_image"],
    "primary_groups": [row["concurrency"] for row in trace["primary_groups"]] == [1, 4, 8, 16],
    "prior_programs": prior_runner.is_file() and prior_owner.is_file(),
    "fixed_staging": session_staging.is_file() and "sudo install -d -o {SSH_USER} -g {SSH_USER}" in session_staging.read_text(),
    "brief_identities": all(x in brief for x in (model, revision, vllm_image, sglang_image, "gpu-h200-sxm", "1gpu-16vcpu-200gb")),
    "brief_workload": "4,214/358" in brief and "c1/c4/c8/c16" in brief and "10,000/358" in brief,
    "brief_market": "2.094181–2.118591" in brief,
    "brief_owner": "one user-systemd durable owner" in brief and "no paid repair or second allocation" in brief,
}
result = {
    "schema_version": 1,
    "classification": "director_predelegation_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "bound": {
        "model": model,
        "revision": revision,
        "checkpoint_root": checkpoint["checkpoint_root"],
        "checkpoint_index_sha256": index,
        "vllm_image": vllm_image,
        "sglang_conditional_image": sglang_image,
        "primary_concurrency": [row["concurrency"] for row in trace["primary_groups"]],
        "market_planning_base_rps": gate["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"],
    },
    "authoritative_inputs": {
        "start_packet": {"path": str(start_path), "sha256": digest(start_path)},
        "checkpoint_terminal": {"path": str(checkpoint_path), "sha256": digest(checkpoint_path)},
        "trace_packet": {"path": str(trace_path), "sha256": digest(trace_path)},
        "economic_gate": {"path": str(gate_path), "sha256": digest(gate_path)},
        "prior_runner": {"path": str(prior_runner), "sha256": digest(prior_runner)},
        "prior_owner": {"path": str(prior_owner), "sha256": digest(prior_owner)},
        "session_staging": {"path": str(session_staging), "sha256": digest(session_staging)},
        "project_brief": {"path": str(brief_path), "sha256": digest(brief_path)},
    },
}
output = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"path": str(output), "pass": result["pass"], "failed": [k for k, v in checks.items() if not v]}))
raise SystemExit(0 if result["pass"] else 1)
