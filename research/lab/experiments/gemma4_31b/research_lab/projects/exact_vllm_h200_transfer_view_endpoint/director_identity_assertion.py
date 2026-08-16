#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RAW = (HERE / "../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint").resolve()
VIEW = (HERE / "../exact_h200_vllm_baseline_shared_runner/artifacts/corrected-transfer-view").resolve()


def load(relative):
    path = (HERE / relative).resolve()
    return path, json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


checkpoint_path, checkpoint = load("../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json")
trace_path, trace = load("../gemma_exact_cache_trace_contract/TRACE_PACKET.json")
start_path, start = load("../sglang_gemma4_exact_precreate_binding/START_PACKET.json")
gate_path, gate = load("../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json")
prior_owner = (HERE / "../exact_vllm_h200_fixed_session_endpoint/vllm_fixed_session_owner.py").resolve()
prior_runner = (HERE / "../exact_vllm_h200_fixed_session_endpoint/trace_endpoint_runner.py").resolve()
brief_path = HERE / "PROJECT.md"
brief = brief_path.read_text()
rows = checkpoint["files"]
expected_manifest = "".join(f"{row['sha256']}  {row['path']}\n" for row in rows)
hardlinks = all(
    (VIEW / row["path"]).is_file()
    and (VIEW / row["path"]).stat().st_size == row["bytes"]
    and (VIEW / row["path"]).stat().st_ino == (RAW / row["path"]).stat().st_ino
    and (VIEW / row["path"]).stat().st_dev == (RAW / row["path"]).stat().st_dev
    for row in rows
)
model, revision = start["identities"]["model"].split("@", 1)
vllm_image = start["identities"]["vllm_control"]["image"]
sglang_image = start["identities"]["sglang"]["image_manifest"]
checks = {
    "checkpoint_pass": checkpoint["pass"] is True,
    "model_revision": checkpoint["model"] == model == trace["identity"]["model"] and checkpoint["revision"] == revision == trace["identity"]["revision"] == gate["identities"]["revision"],
    "trace_groups": [row["concurrency"] for row in trace["primary_groups"]] == [1, 4, 8, 16],
    "runtime_image": vllm_image == trace["identity"]["runtime_image"],
    "transfer_view_manifest": (VIEW / "model-files.sha256").read_text() == expected_manifest,
    "transfer_view_hardlinks": hardlinks,
    "prior_programs": prior_owner.is_file() and prior_runner.is_file(),
    "brief_bindings": all(x in brief for x in (model, revision, "../exact_h200_vllm_baseline_shared_runner/artifacts/corrected-transfer-view", vllm_image, sglang_image, "gpu-h200-sxm", "1gpu-16vcpu-200gb", "2.094181–2.118591")),
}
result = {
    "schema_version": 1,
    "classification": "director_predelegation_transfer_view_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "bound": {
        "model": model,
        "revision": revision,
        "raw_checkpoint": str(RAW),
        "transfer_view": str(VIEW),
        "transfer_manifest_sha256": sha(VIEW / "model-files.sha256"),
        "new_weight_storage_bytes": 0,
        "vllm_image": vllm_image,
        "sglang_conditional_image": sglang_image,
        "primary_concurrency": [row["concurrency"] for row in trace["primary_groups"]],
        "market_planning_base_rps": gate["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"],
    },
    "inputs": {str(path): sha(path) for path in (checkpoint_path, trace_path, start_path, gate_path, prior_owner, prior_runner, brief_path)},
}
output = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"path": str(output), "pass": result["pass"], "failed": [k for k, v in checks.items() if not v]}))
raise SystemExit(0 if result["pass"] else 1)
