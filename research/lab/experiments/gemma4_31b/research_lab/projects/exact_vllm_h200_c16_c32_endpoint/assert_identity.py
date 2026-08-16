#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parent.parent


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


checkpoint = LAB / "projects/sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json"
trace = LAB / "projects/gemma_exact_cache_trace_contract/TRACE_PACKET.json"
gate = LAB / "projects/h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json"
component = LAB / "projects/h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json"
staging = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/session_staging.py")
brief = (PROJECT / "PROJECT.md").read_text()

c = load(checkpoint)
t = load(trace)
g = load(gate)
r = load(component)
revision = t["identity"]["revision"]
runtime = t["identity"]["runtime_image"]
checks = {
    "model_revision_cross_source": revision == g["identities"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
    "checkpoint_pass": c.get("pass") is True or c.get("status") == "pass",
    "checkpoint_hash": sha(checkpoint) == "5f0765fa37f308e21d665571a92c29ba1998b22b5ee67d1edbfac103dafec481",
    "trace_hash": sha(trace) == "ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68",
    "gate_hash": sha(gate) == "3f4ce08c7e3a6649c18af99f14e0d48dcaf3979ac818462f7cf159cd9dab9afd",
    "component_hash": sha(component) == "9f12b3ae4c8d82176f0ec9b09845c6e97ab1f278a458bd023adcbe433fd004fe",
    "fixed_staging_hash": sha(staging) == "e9c4ab2b5b52646c3ffac2f5c6165fc627adaccc1dc77fd2adc59b6e16318295",
    "runtime": runtime == "vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79" and runtime in brief,
    "workload": t["primary_groups"][0]["concurrency"] == 1 and t["primary_groups"][-1]["concurrency"] == 16,
    "market_gate": g["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"] == [2.094181, 2.118591],
    "component_decision": r["classification"] == "cuda_event_component_floor_falsifies_c1_c4_c8_preserves_c16_c32",
    "brief_narrowing": "c16" in brief and "c32" in brief and revision in brief,
}
out = {
    "schema_version": 1,
    "type": "director_paid_endpoint_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "bound": {
        "model": t["identity"]["model"],
        "revision": revision,
        "runtime_image": runtime,
        "checkpoint_index_sha256": t["identity"]["checkpoint_index_sha256"],
        "trace_sha256": sha(trace),
        "h200_planning_base_rps": [2.094181, 2.118591],
        "admitted_concurrency": [16, 32],
        "component_combined_seconds_per_request": {"16": 0.4424622218152508, "32": 0.22476958992984145},
        "staging_sha256": sha(staging),
    },
}
path = PROJECT / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json"
path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps({"pass": out["pass"], "checks": checks, "artifact": str(path)}, sort_keys=True))
raise SystemExit(0 if out["pass"] else 1)
