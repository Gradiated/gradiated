#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parent
LAB = P.parent.parent
brief = (P / "PROJECT.md").read_text()

identity_path = LAB / "projects/gemma_l40s_vllm_fp8_consumer_bridge/IDENTITY_ASSERTION.json"
runtime_path = LAB / "projects/gemma_l40s_w4_marlin_component_bridge/artifacts/runtime-correction-final-20260717T061647Z/runtime-correction-terminal.json"
gate_path = LAB / "projects/l40s_saturation_economic_gate/SATURATION_GATE.json"
rank_path = LAB / "projects/post_bf16_c32_successor_selection/SUCCESSOR_RANK.json"

identity = json.loads(identity_path.read_text())
runtime = json.loads(runtime_path.read_text())
gate = json.loads(gate_path.read_text())
rank = json.loads(rank_path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

fp8 = {(x["fqcn"], x["source_sha256"]) for x in runtime["resolved_fp8_consumer"]}
w4 = {(x["fqcn"], x["source_sha256"]) for x in runtime["resolved_w4_consumer"]}
shapes = identity["source_derived_tp1_shapes"]
checks = {
    "source_identity_pass": identity["model"] == "google/gemma-4-31B-it" and identity["tp_size"] == 1,
    "rank_primary": rank["decision"] == "direct_l40s_online_fp8_actual_consumer_component",
    "model_in_brief": f'{identity["model"]}@{identity["model_revision"]}' in brief,
    "image_in_brief": identity["runtime_image"] in brief,
    "workload_in_brief": all(str(identity["workload"][k]) in brief for k in ("primary_input_tokens", "primary_output_tokens", "aa_input_tokens")),
    "all_shapes_in_brief": all(f'{v[0]}->{v[1]}' in brief for v in shapes.values()),
    "unique_fp8_after_dedup": len(fp8) == 1 and next(iter(fp8))[0].endswith("fp8.Fp8LinearMethod"),
    "unique_w4": len(w4) == 1 and next(iter(w4))[0].endswith("awq_marlin.AWQMarlinLinearMethod"),
    "consumer_hashes_in_brief": all(h in brief for _, h in fp8 | w4),
    "gate_identity_bound": identity["input_hashes"]["saturation_gate"] == sha(gate_path),
    "planning_hurdle_in_brief": str(gate["economic_surface"]["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"]) in brief,
    "single_allocation_no_checkpoint": "one allocation" in brief and "No checkpoint" in brief,
}
out = {
    "schema_version": 1,
    "type": "director_identity_assertion",
    "checks": checks,
    "pass": all(checks.values()),
    "extracted": {
        "model": identity["model"], "revision": identity["model_revision"], "runtime_image": identity["runtime_image"],
        "workload": identity["workload"], "shapes": shapes,
        "fp8_consumer": sorted(fp8), "w4_consumer": sorted(w4),
        "planning_hurdle": gate["economic_surface"]["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"],
        "planning_ceiling": gate["capacity_constraints"]["primary_c8"]["p50_completion_time_ceiling_seconds"] if "capacity_constraints" in gate else 1.3945806410831811,
    },
    "authoritative_inputs": {str(x): sha(x) for x in (identity_path, runtime_path, gate_path, rank_path)},
}
target = P / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps(out, sort_keys=True))
raise SystemExit(0 if out["pass"] else 1)
