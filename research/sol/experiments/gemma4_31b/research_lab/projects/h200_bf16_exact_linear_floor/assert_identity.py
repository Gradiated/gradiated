#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parent.parent


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


geometry_path = LAB / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json"
component_path = LAB / "projects/gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json"
gate_path = LAB / "projects/h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json"
head_path = LAB / "projects/gemma_l40s_parallel_lm_head_measurement_final/artifacts/gemma-l40s-head-final-20260717t065653z/summary.json"
provider_path = LAB / "projects/gemma_l40s_parallel_lm_head_measurement_final/artifacts/gemma-l40s-head-final-20260717t065653z/provider-request.json"
brief_path = PROJECT / "PROJECT.md"

geometry = load(geometry_path)
component = load(component_path)
gate = load(gate_path)
head = load(head_path)
provider = load(provider_path)
brief = brief_path.read_text()

expected_revision = geometry["identities"]["target_model"]["revision"]
expected_shapes = [[5376, 16384], [5376, 20480], [5376, 43008], [8192, 5376], [16384, 5376], [21504, 5376]]
checks = {
    "model_id": geometry["identities"]["target_model"]["id"] == "google/gemma-4-31B-it",
    "revision_cross_source": expected_revision == gate["identities"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
    "revision_in_brief": expected_revision in brief,
    "layer_geometry": geometry["target_text_geometry_measured_from_config"]["num_hidden_layers"] == 60
    and geometry["target_text_geometry_measured_from_config"]["attention_pattern"]["sliding_attention_layers"] == 50
    and geometry["target_text_geometry_measured_from_config"]["attention_pattern"]["full_attention_layers"] == 10,
    "width_geometry": geometry["target_text_geometry_measured_from_config"]["hidden_size"] == 5376
    and geometry["target_text_geometry_measured_from_config"]["intermediate_size"] == 21504,
    "six_shapes": component["scope"]["shapes"] == expected_shapes,
    "workload": gate["identities"]["workload_campaign_mix"]["prompt_tokens"] == 4214
    and gate["identities"]["workload_campaign_mix"]["output_tokens"] == 358
    and gate["identities"]["workload_campaign_mix"]["cache_prompt_fraction"] == 0.127,
    "market_gate": gate["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"] == [2.094181, 2.118591],
    "market_cost": gate["gate_by_market_target"]["frontier_summary_at_planning_rate"]["market_endpoints_excluding_AA_blend"]["planning_base_rps_range"] == [1.789798, 2.118591]
    and gate["gate_by_market_target"]["frontier_summary_at_planning_rate"]["strict_frontier_request_cost_range_usd"] == [0.000614287, 0.000621447],
    "head_actual_consumer": head["outcome"] == "PASS"
    and head["stage_records"][0]["terminal"]["all_actual_consumers_pass"] is True,
    "runtime_image": "sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79" in brief,
    "provider_request_retained": isinstance(provider, dict) and len(provider) > 0,
}

result = {
    "schema_version": 1,
    "type": "director_paid_project_identity_assertion",
    "pass": all(checks.values()),
    "checks": checks,
    "bound": {
        "model": "google/gemma-4-31B-it",
        "revision": expected_revision,
        "shapes": expected_shapes,
        "multiplicities": [50, 10, 60, 50, 10, 60],
        "runtime_image": "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79",
        "h200_planning_base_rps": [2.094181, 2.118591],
        "max_total_service_seconds_per_request": [1 / 2.094181, 1 / 2.118591],
    },
    "source_sha256": {
        str(path.relative_to(LAB)): digest(path)
        for path in [geometry_path, component_path, gate_path, head_path, provider_path]
    },
}
out = PROJECT / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json"
out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"pass": result["pass"], "artifact": str(out), "checks": checks}, sort_keys=True))
raise SystemExit(0 if result["pass"] else 1)
