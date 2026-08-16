#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
FILES = {
    LAB / "post_l40s_fp8_successor_selection/SELECTION.json": "f94e40c4d63d67a939d0b6c8fa855a995cff06d66b254cbf8a41727ecaf2d326",
    LAB / "h100_hybrid_attention_kernel_mechanism/MECHANISM.json": "3960c453e88b1a12e01351d2062dbaa7f8a800e63fe6674e997ddbbcfeebdda1",
    LAB / "exact_geometry_runtime_opportunities/GEOMETRY.json": "024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72",
    LAB / "exact_bf16_mtp_h100_frontier/artifacts/preflight-20260717T000000Z/hf-config.json": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    Path("/root/workspace/research/factory/data/accelerator_inventory.json"): "bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8",
    Path("/root/workspace/research/factory/data/gpu_prices.json"): "3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01",
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

actual = {str(path): sha(path) for path in FILES}
expected = {str(path): digest for path, digest in FILES.items()}
selection = json.loads((LAB / "post_l40s_fp8_successor_selection/SELECTION.json").read_text())
arm = selection["selected_paid_arm"]
identity = arm["mechanical_identity"]
budget = arm["budgets"]
project = (HERE / "PROJECT.md").read_text()

checks = {
    "all_authoritative_hashes": actual == expected,
    "selection_terminal": selection.get("terminal") is True,
    "selected_arm": selection.get("decision") == "run_one_checkpoint_free_h100_actual_paged_fp8_kv_component_falsifier",
    "model_revision": f'{identity["model"]}@{identity["model_revision"]}' in project,
    "runtime_image": identity["runtime_image"] in project,
    "observed_vllm": identity["observed_image_vllm"] in project,
    "source_prior_distinguished": identity["source_revision"] in project and "analytical prior, not execution-equivalent" in project,
    "h100": arm["hardware"]["accelerator"] == "one full NVIDIA H100 SXM" and "NVIDIA H100 SXM" in project,
    "geometry": identity["geometry"]["local"]["head_dim"] == 256 and identity["geometry"]["global"]["head_dim"] == 512,
    "checkpoint_free": arm["type"] == "checkpoint_free_component" and "no checkpoint" in project,
    "budgets": budget["wall_clock_minutes"] == 40 and budget["provider_exposure_minutes"] == 25 and budget["spend_usd_max"] == 1.3 and budget["allocations"] == 1 and budget["repairs_or_restarts"] == 0,
    "first_rows": len(arm["scientific_contract"]["first_atomically_retrieved_rows"]) == 2,
    "whole_request_hurdle": "0.027398761575976767" in project,
    "adjacent_trigger": arm["optional_adjacent_retained_session"]["decision_trigger"] == "H100_FP8_KV_PRIMARY_PASS_AND_SETUP_DOMINATES" and "H100_FP8_KV_PRIMARY_PASS_AND_SETUP_DOMINATES" in project,
}
result = {
    "schema_version": 1,
    "type": "h100_actual_paged_fp8_kv_director_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "authoritative_hashes": actual,
    "mechanical_identity": identity,
    "budgets": budget,
}
out = HERE / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(out)
print(sha(out))
raise SystemExit(0 if result["pass"] else 1)
