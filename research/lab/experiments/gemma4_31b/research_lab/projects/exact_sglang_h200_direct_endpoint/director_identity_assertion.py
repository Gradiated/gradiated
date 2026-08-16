#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]


def load(relative: str):
    path = (HERE / relative).resolve()
    return path, json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


start_path, start = load("../sglang_gemma4_exact_precreate_binding/START_PACKET.json")
checkpoint_path, checkpoint = load(
    "../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json"
)
trace_path, trace = load("../gemma_exact_cache_trace_contract/TRACE_PACKET.json")
gate_path, gate = load("../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json")
brief_path = HERE / "PROJECT.md"
brief = brief_path.read_text()

model, revision = start["identities"]["model"].split("@", 1)
sglang_image = start["identities"]["sglang"]["image_manifest"]
vllm_image = start["identities"]["vllm_control"]["image"]
checkpoint_index = next(
    row["sha256"] for row in checkpoint["files"] if row["path"] == "model.safetensors.index.json"
)
checkpoint_project_relative = checkpoint["checkpoint_root"].split("/projects/", 1)[1]

checks = {
    "start_packet_classification": start["classification"] == "start_packet",
    "checkpoint_pass": checkpoint["pass"] is True,
    "model_match": checkpoint["model"] == model == trace["identity"]["model"],
    "revision_match": checkpoint["revision"] == revision == trace["identity"]["revision"] == gate["identities"]["revision"],
    "checkpoint_index_match": checkpoint_index == trace["identity"]["checkpoint_index_sha256"],
    "vllm_image_match": vllm_image == trace["identity"]["runtime_image"],
    "brief_model": model in brief,
    "brief_revision": revision in brief,
    "brief_sglang_image": sglang_image in brief,
    "brief_vllm_image": vllm_image in brief,
    "brief_checkpoint_root": checkpoint["checkpoint_root"] in brief or f"../{checkpoint_project_relative}" in brief,
    "brief_primary_workload": "4,214 input / 358 output" in brief and "c1/c4/c8/c16" in brief,
    "brief_separate_workload": "10,000-input / 358-output" in brief,
    "brief_hardware": "gpu-h200-sxm" in brief and "1gpu-16vcpu-200gb" in brief,
    "brief_market_gate": "2.094181–2.118591" in brief,
    "brief_single_allocation": "one allocation" in brief and "Do not repair or create a second allocation" in brief,
}

result = {
    "schema_version": 1,
    "classification": "director_predelegation_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "authoritative_inputs": {
        "start_packet": {"path": str(start_path), "sha256": sha256(start_path)},
        "checkpoint_terminal": {"path": str(checkpoint_path), "sha256": sha256(checkpoint_path)},
        "trace_packet": {"path": str(trace_path), "sha256": sha256(trace_path)},
        "economic_gate": {"path": str(gate_path), "sha256": sha256(gate_path)},
        "project_brief": {"path": str(brief_path), "sha256": sha256(brief_path)},
    },
    "bound": {
        "model": model,
        "revision": revision,
        "checkpoint_root": checkpoint["checkpoint_root"],
        "checkpoint_index_sha256": checkpoint_index,
        "sglang_image": sglang_image,
        "sglang_amd64_child": start["identities"]["sglang"]["image_amd64_child_manifest"],
        "sglang_source_commit": start["identities"]["sglang"]["source_commit"],
        "vllm_image": vllm_image,
        "trace_kind": trace["kind"],
        "primary_concurrency": [row["concurrency"] for row in trace["primary_groups"]],
        "market_planning_base_rps": gate["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"],
    },
}

output = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"path": str(output), "pass": result["pass"], "failed": [k for k, v in checks.items() if not v]}))
raise SystemExit(0 if result["pass"] else 1)
