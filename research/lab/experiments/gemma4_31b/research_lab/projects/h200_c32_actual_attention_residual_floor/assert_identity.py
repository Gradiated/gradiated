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


geometry_path = LAB / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json"
component_path = LAB / "projects/h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json"
kv_path = LAB / "projects/h200_bf16_kv_attention_bandwidth_floor/KV_ATTENTION_FLOOR.json"
gate_path = LAB / "projects/h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json"
trace_path = LAB / "projects/gemma_exact_cache_trace_contract/TRACE_PACKET.json"
brief = (PROJECT / "PROJECT.md").read_text()

geometry = load(geometry_path)
component = load(component_path)
kv = load(kv_path)
gate = load(gate_path)
trace = load(trace_path)
target = geometry["target_text_geometry_measured_from_config"]
runtime = trace["identity"]["runtime_image"]
checks = {
    "geometry_sha": sha(geometry_path) == "024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72",
    "component_sha": sha(component_path) == "9f12b3ae4c8d82176f0ec9b09845c6e97ab1f278a458bd023adcbe433fd004fe",
    "kv_sha": sha(kv_path) == "8d0d1ef6bc39adef386a072947bc0ae820e3193af4d6e8b28c19bc6f59fcb442",
    "gate_sha": sha(gate_path) == "3f4ce08c7e3a6649c18af99f14e0d48dcaf3979ac818462f7cf159cd9dab9afd",
    "revision": geometry["identities"]["target_model"]["revision"] == gate["identities"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
    "runtime": runtime == "vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79" and runtime in brief,
    "hybrid_layers": target["attention_pattern"]["sliding_attention_layers"] == 50 and target["attention_pattern"]["full_attention_layers"] == 10,
    "attention_geometry": target["num_attention_heads"] == 32 and target["head_dim_sliding"] == 256 and target["num_key_value_heads_sliding"] == 16 and target["global_head_dim"] == 512 and target["num_global_key_value_heads"] == 4,
    "window": target["sliding_window_tokens"] == 1024,
    "component_decision": component["classification"] == "cuda_event_component_floor_falsifies_c1_c4_c8_preserves_c16_c32",
    "kv_decision": kv["decision"]["c16"] == "falsified_by_optimistic_kv_read_floor" and kv["decision"]["c32"] == "preserved_not_proven",
    "gate": gate["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"] == [2.094181, 2.118591],
}
artifact = {
    "schema_version": 1,
    "type": "director_paid_actual_attention_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "bound": {
        "model": geometry["identities"]["target_model"]["id"],
        "revision": geometry["identities"]["target_model"]["revision"],
        "runtime_image": runtime,
        "batch": 32,
        "decode_contexts_inclusive": [4214, 4571],
        "sliding": {"layers": 50, "q_heads": 32, "kv_heads": 16, "head_dim": 256, "context": 1024},
        "global": {"layers": 10, "q_heads": 32, "kv_heads": 4, "head_dim": 512, "attention_k_eq_v": True},
        "linears_head_seconds_per_request": 0.22476958992984145,
        "optimistic_kv_seconds_per_request_reference_only": 0.05799790933333333,
        "whole_service_ceiling_seconds_per_request": [0.47201182295214134, 0.47751364375858635],
    },
}
path = PROJECT / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json"
path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
print(json.dumps({"pass": artifact["pass"], "checks": checks, "artifact": str(path)}, sort_keys=True))
raise SystemExit(0 if artifact["pass"] else 1)
