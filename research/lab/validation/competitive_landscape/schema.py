from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA_VERSION = "inference-foundry.competitive-simulation-landscape.v1"
REQUIRED_ENTRY_IDS = {
    "nvidia_dynosim_aiconfigurator",
    "nvidia_model_hardware_codesign",
    "fireworks_fireoptimizer_3d",
    "etched_vertical_inference_clusters",
    "furiosa_rngd_model_compiler",
    "astra_sim",
    "timeloop_accelergy",
    "llmservingsim_2",
    "mlperf_inference",
    "aa_agentperf",
    "indexcache_cross_layer_dsa",
    "tisa_temporal_dsa",
    "hisa_hierarchical_dsa",
    "misa_indexer_head_routing",
    "unique_page_sparse_attention",
    "spin_sparse_hierarchical_kv",
    "intra_token_sparse_gather",
    "salca_sparse_attention_accelerator",
    "nosa_locality_trained_offload",
}
REQUIRED_PERMISSION_KEYS = {
    "commercial_moat",
    "competitive_superiority",
    "custom_silicon_tapeout",
    "five_x_performance_gain",
    "independent_competitor_reproduction",
    "market_completeness",
    "measured_cost_per_token",
    "provider_competitiveness",
    "ten_x_performance_gain",
}
SOURCE_KINDS = {
    "benchmark_methodology",
    "official_documentation",
    "official_repository",
    "primary_paper",
    "vendor_product_page",
    "vendor_technical_blog",
}
EVIDENCE_CLASSES = {
    "author_reported_result",
    "benchmark_operator_methodology",
    "official_documented_capability",
    "public_artifact_observation",
    "vendor_assertion",
}
REPRODUCTION_STATUSES = {
    "methodology_target_only",
    "not_run_locally",
    "public_artifact_inspected_not_benchmarked",
}
ENTRY_KINDS = {
    "commercial_software",
    "custom_accelerator_vendor",
    "open_simulator",
    "research_mechanism",
    "validation_benchmark",
    "vertically_integrated_hardware_vendor",
}
LAYER_IDS = {
    "accelerator_microarchitecture",
    "compiler",
    "cost_accounting",
    "fleet_planner",
    "kernel",
    "kv_cache",
    "manufacturing",
    "memory_hierarchy",
    "model_architecture",
    "network_topology",
    "parallelism",
    "physical_design",
    "power_energy",
    "quality_validation",
    "routing",
    "serving_scheduler",
    "workload",
}


def content_identity(document: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in document.items()
        if key != "content_identity_sha256"
    }
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_landscape(
    document: dict[str, Any],
    *,
    verify_identity: bool = True,
) -> None:
    if not isinstance(document, dict):
        raise ValueError("landscape root must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported landscape schema version")
    if document.get("as_of_date") != "2026-07-12":
        raise ValueError("landscape as_of_date must be 2026-07-12")
    scope = _object(document, "scope")
    _nonempty_string(scope, "question")
    _nonempty_string(scope, "supported_claim")
    _string_list(scope, "unsupported_claims")
    evidence_policy = _object(document, "evidence_policy")
    if evidence_policy.get("primary_sources_only") is not True:
        raise ValueError("evidence policy must require primary sources")
    if evidence_policy.get("independently_reproduced_fact_count") != 0:
        raise ValueError("independently reproduced fact count must remain zero")
    if evidence_policy.get("market_snapshot_not_exhaustive") is not True:
        raise ValueError("evidence policy must reject market completeness")
    sources = _object_list(document, "sources")
    source_ids = _validate_sources(sources, str(document["as_of_date"]))
    entries = _object_list(document, "entries")
    entry_ids = _validate_entries(entries, source_ids)
    if entry_ids != REQUIRED_ENTRY_IDS:
        raise ValueError("landscape does not cover every required competitive surface")
    _validate_layers(_object_list(document, "commoditized_layers"), entry_ids)
    gates = _object_list(document, "decision_gates")
    gate_ids = _validate_gates(gates)
    _validate_wedge(_object(document, "surviving_wedge"), gate_ids)
    _validate_targets(_object_list(document, "validation_targets"), source_ids)
    permissions = _object(document, "claim_permissions")
    if set(permissions) != REQUIRED_PERMISSION_KEYS or any(
        value is not False for value in permissions.values()
    ):
        raise ValueError("claim permissions must contain every required false flag")
    conclusion = _object(document, "conclusion")
    _nonempty_string(conclusion, "current_decision")
    _nonempty_string(conclusion, "strongest_negative_evidence")
    _nonempty_string(conclusion, "strongest_remaining_opportunity")
    if conclusion.get("business_claim_status") != "unproven":
        raise ValueError("business claim status must remain unproven")
    if verify_identity:
        claimed = str(document.get("content_identity_sha256", ""))
        if claimed != content_identity(document):
            raise ValueError("landscape content identity does not verify")


def _validate_sources(sources: list[dict[str, Any]], as_of_date: str) -> set[str]:
    identifiers: set[str] = set()
    for source in sources:
        identifier = _nonempty_string(source, "source_id")
        if identifier in identifiers:
            raise ValueError(f"duplicate source id: {identifier}")
        identifiers.add(identifier)
        if source.get("primary_source") is not True:
            raise ValueError(f"every source must be primary: {identifier}")
        if source.get("source_kind") not in SOURCE_KINDS:
            raise ValueError(f"unsupported source kind: {identifier}")
        url = _nonempty_string(source, "url")
        if not url.startswith("https://"):
            raise ValueError(f"source URL must use HTTPS: {identifier}")
        _nonempty_string(source, "title")
        _nonempty_string(source, "publisher")
        _nonempty_string(source, "claimant_relation")
        if source.get("accessed_on") != as_of_date:
            raise ValueError(f"source access date is not pinned: {identifier}")
        pin = source.get("version_pin")
        if not isinstance(pin, dict) or not pin:
            raise ValueError(f"source version pin is missing: {identifier}")
    if len(identifiers) < 15:
        raise ValueError("landscape requires at least fifteen primary sources")
    return identifiers


def _validate_entries(
    entries: list[dict[str, Any]],
    source_ids: set[str],
) -> set[str]:
    identifiers: set[str] = set()
    for entry in entries:
        identifier = _nonempty_string(entry, "entry_id")
        if identifier in identifiers:
            raise ValueError(f"duplicate entry id: {identifier}")
        identifiers.add(identifier)
        if entry.get("entry_kind") not in ENTRY_KINDS:
            raise ValueError(f"unsupported entry kind: {identifier}")
        covered_layers = entry.get("covered_layers")
        if (
            not isinstance(covered_layers, list)
            or not covered_layers
            or any(layer not in LAYER_IDS for layer in covered_layers)
        ):
            raise ValueError(f"invalid covered layers: {identifier}")
        referenced_sources = _string_list(entry, "source_ids")
        unknown = set(referenced_sources) - source_ids
        if unknown:
            raise ValueError(f"entry references unknown source: {sorted(unknown)}")
        claims = entry.get("public_claims")
        if not isinstance(claims, list) or not claims:
            raise ValueError(f"entry must contain public claims: {identifier}")
        claim_ids: set[str] = set()
        for claim in claims:
            if not isinstance(claim, dict):
                raise ValueError(f"claim must be an object: {identifier}")
            claim_id = _nonempty_string(claim, "claim_id")
            if claim_id in claim_ids:
                raise ValueError(f"duplicate claim id: {claim_id}")
            claim_ids.add(claim_id)
            _nonempty_string(claim, "statement")
            if claim.get("evidence_class") not in EVIDENCE_CLASSES:
                raise ValueError(f"unsupported evidence class: {claim_id}")
            if claim.get("reproduction_status") not in REPRODUCTION_STATUSES:
                raise ValueError(f"unsupported reproduction status: {claim_id}")
            if claim.get("independently_reproduced") is not False:
                raise ValueError(f"claim is not independently reproduced: {claim_id}")
            claim_sources = _string_list(claim, "source_ids")
            if not set(claim_sources).issubset(set(referenced_sources)):
                raise ValueError(f"claim references an undeclared source: {claim_id}")
        reproduced = entry.get("independently_reproduced_facts")
        if reproduced != []:
            raise ValueError(
                f"independently reproduced facts must remain empty: {identifier}"
            )
        _nonempty_string(entry, "competitive_implication")
        _nonempty_string(entry, "public_evidence_limit")
    return identifiers


def _validate_layers(
    layers: list[dict[str, Any]],
    entry_ids: set[str],
) -> None:
    identifiers: set[str] = set()
    allowed_statuses = {
        "commercially_occupied",
        "competitively_occupied_not_commodity",
        "open_source_building_block",
        "publicly_documented_design_space",
    }
    for layer in layers:
        identifier = _nonempty_string(layer, "layer_id")
        if identifier in identifiers:
            raise ValueError(f"duplicate commoditized layer id: {identifier}")
        identifiers.add(identifier)
        if layer.get("status") not in allowed_statuses:
            raise ValueError(f"invalid commoditized layer status: {identifier}")
        evidence_entries = _string_list(layer, "evidence_entry_ids")
        if not set(evidence_entries).issubset(entry_ids):
            raise ValueError(f"layer references unknown entry: {identifier}")
        _nonempty_string(layer, "business_implication")
    if len(identifiers) < 7:
        raise ValueError("landscape must identify at least seven occupied layers")


def _validate_gates(gates: list[dict[str, Any]]) -> set[str]:
    if not 3 <= len(gates) <= 5:
        raise ValueError("landscape must define three to five decision gates")
    identifiers: set[str] = set()
    for gate in gates:
        identifier = _nonempty_string(gate, "gate_id")
        if identifier in identifiers:
            raise ValueError(f"duplicate gate id: {identifier}")
        identifiers.add(identifier)
        if gate.get("current_status") != "not_met":
            raise ValueError(f"gate must remain not_met: {identifier}")
        if gate.get("evidence_type") != "pre_registered_proposal":
            raise ValueError(f"gate evidence type must be proposed: {identifier}")
        _nonempty_string(gate, "decision_scope")
        _nonempty_string(gate, "current_evidence_gap")
        _string_list(gate, "measurements")
        _string_list(gate, "promotion_if_all")
        _string_list(gate, "kill_if_any")
        _nonempty_string(gate, "kill_action")
    return identifiers


def _validate_wedge(wedge: dict[str, Any], gate_ids: set[str]) -> None:
    if wedge.get("status") != "hypothesis":
        raise ValueError("surviving wedge must remain a hypothesis")
    if wedge.get("moat_claim_permitted") is not False:
        raise ValueError("surviving wedge cannot permit a moat claim")
    _nonempty_string(wedge, "hypothesis")
    _nonempty_string(wedge, "why_it_survives_public_source_review")
    _string_list(wedge, "required_components")
    falsifier_ids = set(_string_list(wedge, "falsifier_gate_ids"))
    if falsifier_ids != gate_ids:
        raise ValueError("every decision gate must falsify the surviving wedge")


def _validate_targets(
    targets: list[dict[str, Any]],
    source_ids: set[str],
) -> None:
    target_ids = {_nonempty_string(target, "target_id") for target in targets}
    if target_ids != {"aa_agentperf", "mlperf_inference"}:
        raise ValueError("validation targets must be MLPerf Inference and AA-AgentPerf")
    for target in targets:
        referenced_sources = set(_string_list(target, "source_ids"))
        if not referenced_sources.issubset(source_ids):
            raise ValueError("validation target references unknown source")
        _string_list(target, "required_measurements")
        _nonempty_string(target, "use_in_foundry")
        if target.get("completed_locally") is not False:
            raise ValueError("validation targets have not been completed locally")


def _object(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _object_list(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, dict) for item in value)
    ):
        raise ValueError(f"{key} must be a non-empty object array")
    return value


def _string_list(document: dict[str, Any], key: str) -> list[str]:
    value = document.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{key} must be a non-empty string array")
    return value


def _nonempty_string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value
