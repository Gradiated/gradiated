from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from validation.predictive_validity.gate import (
    default_gate_spec,
    evaluate_pairs,
)


SCHEMA_VERSION = "inference-foundry.simulator-predictive-validity-gate.v1"
ARTIFACT_PATH = "validation/results/simulator-predictive-validity-gate-2026-07-12.json"
BUSINESS_DECISION_PATH = (
    "validation/results/model-stack-business-decision-2026-07-12.json"
)
INVENTORY_EXCLUSIONS = [
    {
        "path": ARTIFACT_PATH,
        "reason": "gate output excluded to prevent self-reference",
    },
    {
        "path": BUSINESS_DECISION_PATH,
        "reason": "downstream decision synthesis excluded to prevent circular identity",
    },
]
CLAIM_PERMISSION_KEYS = {
    "cost_promotion",
    "custom_silicon_underwriting",
    "model_specific_codesign_advantage",
    "provider_competitiveness",
    "simulator_predictive_validity",
}
EVIDENCE_ROLES = {
    "analytical_bound",
    "business_synthesis",
    "external_claim_summary",
    "measured_hardware",
    "measured_quality",
    "modeled_economics",
    "simulated_hardware",
    "simulated_serving",
    "synthetic_workload",
    "tool_contract",
    "tool_probe",
}
REJECTION_CODES = {
    "analytical_bound_not_same_metric",
    "business_summary_not_pair_evidence",
    "calibration_holdout_split_missing",
    "cross_model_transfer_not_permitted",
    "frontend_parse_only",
    "hardware_scope_mismatch",
    "insufficient_context_regimes",
    "insufficient_interventions",
    "intervention_scope_mismatch",
    "measurement_repeat_not_prediction",
    "metric_scope_mismatch",
    "no_blinded_holdout",
    "no_measured_holdout",
    "no_predeclared_prediction",
    "no_prediction_timestamp",
    "no_regression_prediction",
    "public_or_vendor_evidence_not_local_pair",
    "quality_slo_evidence_missing",
    "simulation_to_simulation_not_valid",
    "software_scope_mismatch",
    "synthetic_workload_not_measured",
    "workload_scope_mismatch",
}
EVIDENCE_POLICY = {
    "exact_scope_identity_required": True,
    "prediction_locked_before_measurement_required": True,
    "blinded_holdout_required": True,
    "global_calibration_holdout_nonoverlap_required": True,
    "simulation_only_is_not_measurement": True,
    "analytical_bound_is_not_a_prediction_pair": True,
    "repeat_measurement_is_not_a_prediction": True,
    "frontend_parse_is_not_measurement": True,
    "cross_model_transfer_is_not_same_scope": True,
    "exact_quality_and_slo_required_for_cost_promotion": True,
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


def inventory_identity(artifacts: list[dict[str, Any]]) -> str:
    stable = sorted(artifacts, key=lambda artifact: artifact["path"])
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_current_state(
    document: dict[str, Any],
    *,
    root: Path,
    verify_identity: bool = True,
    verify_files: bool = True,
) -> None:
    if not isinstance(document, dict):
        raise ValueError("current state root must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported predictive-validity schema version")
    if document.get("as_of_date") != "2026-07-12":
        raise ValueError("current state as_of_date must be 2026-07-12")
    if document.get("gate_spec") != default_gate_spec():
        raise ValueError("gate spec does not match the frozen predeclaration")
    if document.get("evidence_policy") != EVIDENCE_POLICY:
        raise ValueError("evidence policy is not fail closed")
    admitted_pairs = _object_list(document, "admitted_pairs")
    admitted_pair_ids = [_nonempty_string(pair, "pair_id") for pair in admitted_pairs]
    if len(admitted_pair_ids) != len(set(admitted_pair_ids)):
        raise ValueError("admitted predictive pair ids must be unique")
    inventory_paths = _validate_inventory(
        _object(document, "audit_inventory"),
        root=root,
        verify_files=verify_files,
    )
    _validate_candidate_audits(
        _object_list(document, "candidate_pair_audits"),
        inventory_paths,
        set(admitted_pair_ids),
    )
    expected_result = evaluate_pairs(admitted_pairs, artifact_root=root)
    if document.get("gate_result") != expected_result:
        raise ValueError("gate result does not reproduce from admitted pairs")
    permissions = _object(document, "claim_permissions")
    if set(permissions) != CLAIM_PERMISSION_KEYS or any(
        value is not False for value in permissions.values()
    ):
        raise ValueError("claim permissions must remain fail closed")
    conclusion = _object(document, "conclusion")
    if conclusion.get("current_status") != "NOT_MET":
        raise ValueError("current conclusion must remain NOT_MET")
    if (
        conclusion.get("admissible_pair_count")
        != expected_result["admitted_pair_count"]
    ):
        raise ValueError("current conclusion admissible pair count is inconsistent")
    _nonempty_string(conclusion, "decision")
    _nonempty_string(conclusion, "next_required_evidence")
    if verify_identity:
        claimed = document.get("content_identity_sha256")
        if claimed != content_identity(document):
            raise ValueError("current-state content identity does not verify")


def _validate_inventory(
    inventory: dict[str, Any],
    *,
    root: Path,
    verify_files: bool,
) -> set[str]:
    selection = _object(inventory, "selection")
    if selection != {
        "roots": ["experiments", "validation/results"],
        "workspace_json_snapshot": True,
        "exclusions": INVENTORY_EXCLUSIONS,
    }:
        raise ValueError("inventory selection is not the frozen snapshot contract")
    artifacts = _object_list(inventory, "artifacts")
    if inventory.get("artifact_count") != len(artifacts) or len(artifacts) < 50:
        raise ValueError("inventory artifact count is incomplete")
    excluded_paths = {exclusion["path"] for exclusion in INVENTORY_EXCLUSIONS}
    paths: set[str] = set()
    for artifact in artifacts:
        path = _nonempty_string(artifact, "path")
        if path in paths:
            raise ValueError(f"duplicate inventory path: {path}")
        paths.add(path)
        if path in excluded_paths or not path.endswith(".json"):
            raise ValueError(f"invalid inventory path: {path}")
        if not path.startswith(("experiments/", "validation/results/")):
            raise ValueError(f"inventory path outside declared roots: {path}")
        file_hash = _sha256_string(artifact, "file_sha256")
        roles = artifact.get("evidence_roles")
        if (
            not isinstance(roles, list)
            or not roles
            or any(role not in EVIDENCE_ROLES for role in roles)
            or len(roles) != len(set(roles))
        ):
            raise ValueError(f"invalid evidence roles: {path}")
        declared_ids = artifact.get("declared_content_ids")
        if not isinstance(declared_ids, list):
            raise ValueError(f"declared content ids must be a list: {path}")
        absolute_path = root / path
        source_document: Any = None
        if verify_files:
            if not absolute_path.is_file():
                raise ValueError(f"inventory file missing: {path}")
            actual_hash = hashlib.sha256(absolute_path.read_bytes()).hexdigest()
            if actual_hash != file_hash:
                raise ValueError(f"inventory file hash mismatch: {path}")
            source_document = json.loads(absolute_path.read_text(encoding="utf-8"))
        for declared_id in declared_ids:
            if not isinstance(declared_id, dict) or set(declared_id) != {
                "json_path",
                "value",
            }:
                raise ValueError(f"invalid declared content id binding: {path}")
            json_path = _nonempty_string(declared_id, "json_path")
            value = _nonempty_string(declared_id, "value")
            if verify_files and _resolve_json_path(source_document, json_path) != value:
                raise ValueError(f"declared content id mismatch: {path}:{json_path}")
    if inventory.get("inventory_identity_sha256") != inventory_identity(artifacts):
        raise ValueError("inventory identity does not verify")
    workspace_paths = {
        str(path.relative_to(root))
        for source_root in (root / "experiments", root / "validation/results")
        for path in source_root.rglob("*.json")
    }
    expected_paths = workspace_paths.difference(
        exclusion["path"] for exclusion in INVENTORY_EXCLUSIONS
    )
    if paths != expected_paths:
        missing = sorted(expected_paths.difference(paths))
        unexpected = sorted(paths.difference(expected_paths))
        raise ValueError(
            f"inventory workspace coverage mismatch: missing={missing}, unexpected={unexpected}"
        )
    return paths


def _validate_candidate_audits(
    audits: list[dict[str, Any]],
    inventory_paths: set[str],
    admitted_pair_ids: set[str],
) -> None:
    if not audits:
        raise ValueError("candidate pair audits are missing")
    audit_ids: set[str] = set()
    covered_paths: set[str] = set()
    audited_pair_ids: list[str] = []
    for audit in audits:
        audit_id = _nonempty_string(audit, "audit_id")
        if audit_id in audit_ids:
            raise ValueError(f"duplicate candidate audit id: {audit_id}")
        audit_ids.add(audit_id)
        paths = _string_list(audit, "artifact_paths")
        if not set(paths).issubset(inventory_paths):
            raise ValueError(f"candidate audit references unknown artifact: {audit_id}")
        covered_paths.update(paths)
        pair_ids = _possibly_empty_string_list(audit, "pair_ids")
        rejection_codes = _possibly_empty_string_list(audit, "rejection_codes")
        status = audit.get("admission_status")
        pair_count = audit.get("same_scope_pair_count")
        if status == "ADMITTED":
            if pair_count != len(pair_ids) or pair_count < 1 or rejection_codes:
                raise ValueError(
                    f"candidate admitted audit is inconsistent: {audit_id}"
                )
            audited_pair_ids.extend(pair_ids)
        elif status == "REJECTED":
            if pair_count != 0 or pair_ids:
                raise ValueError(f"candidate rejected audit claims a pair: {audit_id}")
            if not rejection_codes or not set(rejection_codes).issubset(
                REJECTION_CODES
            ):
                raise ValueError(
                    f"candidate audit has invalid rejection codes: {audit_id}"
                )
        else:
            raise ValueError(f"candidate audit has invalid status: {audit_id}")
        _nonempty_string(audit, "finding")
    if covered_paths != inventory_paths:
        raise ValueError("candidate audits do not cover the complete inventory")
    if len(audited_pair_ids) != len(set(audited_pair_ids)):
        raise ValueError("candidate audits bind duplicate predictive pairs")
    if set(audited_pair_ids) != admitted_pair_ids:
        raise ValueError("candidate audits do not bind the admitted predictive pairs")


def _resolve_json_path(document: Any, json_path: str) -> Any:
    current = document
    for part in json_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _object(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _object_list(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{key} must be a list of objects")
    return value


def _string_list(document: dict[str, Any], key: str) -> list[str]:
    value = document.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{key} must be a unique non-empty string list")
    return value


def _possibly_empty_string_list(document: dict[str, Any], key: str) -> list[str]:
    value = document.get(key)
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{key} must be a unique string list")
    return value


def _nonempty_string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _sha256_string(document: dict[str, Any], key: str) -> str:
    value = _nonempty_string(document, key)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{key} must be a lowercase SHA-256")
    return value
