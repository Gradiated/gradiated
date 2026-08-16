#!/usr/bin/env python3
import hashlib, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
H200 = LAB / "projects/h200_bf16_exact_linear_floor"
W4 = LAB / "projects/h100_w4_marlin_direct_falsifier"
MECH = LAB / "projects/h100_w4_marlin_exact_shape_mechanism/MECHANISM.json"

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

campaign = (LAB / "CAMPAIGN.md").read_text()
brief = (HERE / "PROJECT.md").read_text()
h200 = json.loads((H200 / "artifacts/RECONCILED_TERMINAL.json").read_text())
w4 = json.loads((W4 / "artifacts/RECONCILED_TERMINAL.json").read_text())
mechanism = json.loads(MECH.read_text())
model = re.search(r"`(google/gemma-4-31B-it)` at revision `([0-9a-f]{40})`", campaign)
required_model = mechanism["immutable_inputs"]["model_geometry"]
required_image = h200["measurement_validity"]["runtime_image"]
ceiling = mechanism["immutable_inputs"]["planning_ceiling_seconds_per_request"]
checks = {
  "h200_terminal_complete": h200["status"] == "complete" and h200["measurement_validity"]["primary_pass"] and h200["measurement_validity"]["conditional_pass"],
  "h200_program_hash_bound": sha(H200 / "h200_bf16_linear_bench.py") in (H200 / "artifacts/POST_CREATE_CORRECTION_AUDIT.json").read_text(),
  "campaign_model": model is not None and required_model == f"{model.group(1)}@{model.group(2)}",
  "h200_model_case_only_discontinuity": h200["economic_gate"]["revision"] == required_model.split("@", 1)[1] and h200["economic_gate"]["model"].lower() == required_model.split("@", 1)[0].lower(),
  "brief_model": required_model in brief,
  "brief_image": required_image in brief,
  "workload": h200["economic_gate"]["workload"] == {"prompt_tokens": 4214, "output_tokens": 358, "cache_prompt_fraction": 0.127},
  "brief_workload": "4,214 prompt / 358 output / 12.7% cache" in brief,
  "h100_ceiling": str(ceiling) in brief,
  "w4_cleanup": w4["cleanup"]["cleanup_pass"] and w4["cleanup"]["final_instance_count"] == 0 and w4["cleanup"]["final_disk_count"] == 0,
  "six_shapes": len(mechanism["immutable_inputs"]["shapes"]) == 6 and all(str(s["k"]) in brief and str(s["n"]) in brief and f"×{s['multiplicity']}" in brief for s in mechanism["immutable_inputs"]["shapes"]),
  "sentinel_sweep": "sliding-QKV M8 sentinel" in brief and "24-row sweep" in brief,
  "adjacent_trigger": "H100_BF16_LINEAR_SURVIVES_AND_SETUP_DOMINATES_AND_HEAD_READY" in brief,
  "budgets": "20 minutes" in brief and "0.34 H100 GPU-hours" in brief and "`$1.30`" in brief,
  "one_allocation": "one allocation" in brief and "zero repair/restart" in brief,
}
result = {"schema_version": 1, "type": "h100_bf16_linear_head_director_identity_assertion", "pass": all(checks.values()), "checks": checks, "identity": {"model": required_model, "image": required_image, "vllm": h200["measurement_validity"]["vllm_version"], "gpu": "NVIDIA H100 80GB HBM3", "ceiling_seconds_per_request": ceiling}, "authoritative_hashes": {"CAMPAIGN.md": sha(LAB / "CAMPAIGN.md"), "H200_RECONCILED_TERMINAL.json": sha(H200 / "artifacts/RECONCILED_TERMINAL.json"), "h200_bf16_linear_bench.py": sha(H200 / "h200_bf16_linear_bench.py"), "W4_RECONCILED_TERMINAL.json": sha(W4 / "artifacts/RECONCILED_TERMINAL.json"), "H100_MECHANISM.json": sha(MECH), "PROJECT.md": sha(HERE / "PROJECT.md")}}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["pass"] else 1)
