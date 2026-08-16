#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(relative):
    path = (HERE / relative).resolve()
    return path, json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


checkpoint_path, checkpoint = load("../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json")
trace_path, trace = load("../gemma_exact_cache_trace_contract/TRACE_PACKET.json")
start_path, start = load("../sglang_gemma4_exact_precreate_binding/START_PACKET.json")
gate_path, gate = load("../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json")
corrected_program = (HERE / "../exact_vllm_h200_transfer_view_endpoint/launch_transfer_view.py").resolve()
runner = (HERE / "../exact_vllm_h200_fixed_session_endpoint/trace_endpoint_runner.py").resolve()
owner = (HERE / "../exact_vllm_h200_fixed_session_endpoint/vllm_fixed_session_owner.py").resolve()
brief_path = HERE / "PROJECT.md"
brief = brief_path.read_text()
raw = Path(checkpoint["checkpoint_root"])
model, revision = start["identities"]["model"].split("@", 1)
vllm_image = start["identities"]["vllm_control"]["image"]
sglang_image = start["identities"]["sglang"]["image_manifest"]
files_pass = all((raw / row["path"]).is_file() and (raw / row["path"]).stat().st_size == row["bytes"] for row in checkpoint["files"])
checks = {
    "checkpoint_pass": checkpoint["pass"] is True and files_pass,
    "model_revision": checkpoint["model"] == model == trace["identity"]["model"] and checkpoint["revision"] == revision == trace["identity"]["revision"] == gate["identities"]["revision"],
    "trace_groups": [row["concurrency"] for row in trace["primary_groups"]] == [1, 4, 8, 16],
    "runtime_image": vllm_image == trace["identity"]["runtime_image"],
    "corrected_program_sources": corrected_program.is_file() and runner.is_file() and owner.is_file(),
    "corrected_lower_features": all(token in corrected_program.read_text() for token in ("corrected_remote", "--entrypoint nvidia-smi", "--entrypoint vllm", "baseline_after_semantic", "trap finalize EXIT", "VLLM_MARKET_TRIGGER", "fp8_e5m2")),
    "brief_bindings": all(token in brief for token in (model, revision, vllm_image, sglang_image, "gpu-h200-sxm", "1gpu-16vcpu-200gb", "2.094181–2.118591", "/root/workspace/.agents/runtime/gemma4-31b/<owner-name>/checkpoint")),
}
result = {
    "schema_version": 1,
    "classification": "director_predelegation_owner_local_view_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "bound": {
        "model": model,
        "revision": revision,
        "raw_checkpoint": str(raw),
        "checkpoint_files": checkpoint["files"],
        "vllm_image": vllm_image,
        "sglang_conditional_image": sglang_image,
        "primary_concurrency": [row["concurrency"] for row in trace["primary_groups"]],
        "market_planning_base_rps": gate["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"],
        "runtime_view_root": "/root/workspace/.agents/runtime/gemma4-31b/<owner-name>/checkpoint",
    },
    "inputs": {str(path): sha(path) for path in (checkpoint_path, trace_path, start_path, gate_path, corrected_program, runner, owner, brief_path)},
}
output = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"path": str(output), "pass": result["pass"], "failed": [key for key, value in checks.items() if not value]}))
raise SystemExit(0 if result["pass"] else 1)
