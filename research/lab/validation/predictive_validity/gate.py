from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


SCOPE_FIELDS = (
    "model_id",
    "model_revision",
    "workload_id",
    "workload_revision",
    "context_regime",
    "hardware_id",
    "hardware_revision",
    "software_id",
    "software_revision",
    "intervention_id",
    "intervention_revision",
    "metric_id",
    "metric_unit",
    "higher_is_better",
)
EXECUTION_SCOPE_FIELDS = SCOPE_FIELDS[:-3]
PAIR_FIELDS = {
    "pair_id",
    "prediction_scope",
    "measurement_scope",
    "protocol",
    "prediction",
    "measurement",
    "cost_evidence",
}
PROTOCOL_FIELDS = {
    "prediction_locked_at_unix_ms",
    "measurement_started_at_unix_ms",
    "prediction_commit_id",
    "blinded_holdout",
    "calibration_case_ids",
    "holdout_case_id",
}
OBSERVATION_FIELDS = {
    "baseline",
    "candidate",
    "artifact_path",
    "artifact_sha256",
    "artifact_content_id",
    "artifact_content_id_json_path",
    "artifact_scope_json_path",
    "baseline_json_path",
    "candidate_json_path",
}
COST_EVIDENCE_FIELDS = {
    "bound_pair_id",
    "execution_scope",
    "artifact_path",
    "artifact_sha256",
    "artifact_content_id",
    "artifact_content_id_json_path",
    "artifact_scope_json_path",
    "criterion_id_json_path",
    "criterion_revision_json_path",
    "passed_json_path",
    "criterion_id",
    "criterion_revision",
    "passed",
}
GATE_SPEC = {
    "required_distinct_interventions": 3,
    "required_context_regimes": 2,
    "maximum_relative_effect_size_error": 0.15,
    "minimum_spearman_rank_correlation": 0.8,
    "effect_size_definition": (
        "fractional_candidate_change_from_each_baseline_oriented_positive_is_better"
    ),
    "relative_effect_size_error_definition": (
        "absolute_predicted_minus_measured_benefit_effect_divided_by_absolute_measured_benefit_effect"
    ),
    "rank_correlation_definition": (
        "spearman_of_predicted_and_measured_benefit_effects_with_average_tie_ranks"
    ),
    "pair_contract_version": "inference-foundry.predictive-pair.v1",
    "exact_scope_fields": list(SCOPE_FIELDS),
    "exact_cost_execution_scope_fields": list(EXECUTION_SCOPE_FIELDS),
    "artifact_binding_fields": [
        "artifact_path",
        "artifact_sha256",
        "artifact_content_id",
        "artifact_content_id_json_path",
        "artifact_scope_json_path",
    ],
    "observation_value_binding_fields": [
        "baseline_json_path",
        "candidate_json_path",
    ],
    "cost_criterion_binding_fields": [
        "criterion_id_json_path",
        "criterion_revision_json_path",
        "passed_json_path",
    ],
    "artifact_binding_verification": (
        "safe_workspace_relative_file_sha256_and_in_file_json_content_id"
    ),
    "require_all_directions_correct": True,
    "require_at_least_one_predicted_regression": True,
    "require_blinded_holdout": True,
    "require_prediction_locked_before_measurement": True,
    "require_global_calibration_holdout_nonoverlap": True,
    "require_exact_scope_identity": True,
    "require_exact_quality_and_slo_for_cost_promotion": True,
}


def default_gate_spec() -> dict[str, Any]:
    return deepcopy(GATE_SPEC)


def evaluate_pairs(
    pairs: list[dict[str, Any]],
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    if not isinstance(pairs, list):
        raise ValueError("pairs must be a list")
    resolved_root = Path(artifact_root).resolve()
    if not resolved_root.is_dir():
        raise ValueError("artifact root must be an existing directory")
    audits = [_audit_pair(pair, resolved_root) for pair in pairs]
    duplicate_ids = {
        pair_id
        for pair_id, count in Counter(
            audit["pair_id"] for audit in audits if audit["pair_id"]
        ).items()
        if count > 1
    }
    for audit in audits:
        if audit["pair_id"] in duplicate_ids:
            _reject(audit, "duplicate_pair_id")
    overlap_ids = _global_overlap_ids(audits)
    if overlap_ids:
        for audit in audits:
            protocol = audit["protocol"]
            pair_ids = set(protocol.get("calibration_case_ids", []))
            holdout = protocol.get("holdout_case_id")
            if holdout in overlap_ids or pair_ids.intersection(overlap_ids):
                _reject(audit, "calibration_holdout_overlap")
    for audit in audits:
        audit["admission_status"] = (
            "ADMITTED" if not audit["rejection_codes"] else "REJECTED"
        )
    admitted = [audit for audit in audits if audit["admission_status"] == "ADMITTED"]
    interventions = {
        audit["measurement_scope"]["intervention_id"] for audit in admitted
    }
    context_regimes = {
        audit["measurement_scope"]["context_regime"] for audit in admitted
    }
    errors = [audit["relative_effect_size_error"] for audit in admitted]
    predicted_benefits = [audit["predicted_benefit_effect"] for audit in admitted]
    measured_benefits = [audit["measured_benefit_effect"] for audit in admitted]
    maximum_error = max(errors) if errors else None
    rank_correlation = _spearman(predicted_benefits, measured_benefits)
    all_directions_correct = bool(admitted) and all(
        audit["direction_correct"] for audit in admitted
    )
    predicted_regression_count = sum(
        audit["predicted_benefit_effect"] < 0 for audit in admitted
    )
    exact_cost_count = sum(audit["exact_quality_slo_evidence"] for audit in admitted)
    reasons = _gate_reasons(
        admitted_count=len(admitted),
        intervention_count=len(interventions),
        context_count=len(context_regimes),
        maximum_error=maximum_error,
        rank_correlation=rank_correlation,
        all_directions_correct=all_directions_correct,
        predicted_regression_count=predicted_regression_count,
        overlap_ids=overlap_ids,
    )
    predictive_validity_met = not reasons
    cost_blockers: list[str] = []
    if not predictive_validity_met:
        cost_blockers.append("predictive_validity_gate_not_met")
    if exact_cost_count != len(admitted) or not admitted:
        cost_blockers.append("exact_quality_slo_evidence_missing")
    result_pairs = []
    for audit in audits:
        result_pairs.append(
            {
                key: value
                for key, value in audit.items()
                if key not in {"protocol", "prediction_scope", "measurement_scope"}
            }
        )
    return {
        "status": "MET" if predictive_validity_met else "NOT_MET",
        "predictive_validity_met": predictive_validity_met,
        "admitted_pair_count": len(admitted),
        "rejected_pair_count": len(audits) - len(admitted),
        "distinct_intervention_count": len(interventions),
        "context_regime_count": len(context_regimes),
        "maximum_relative_effect_size_error": maximum_error,
        "spearman_rank_correlation": rank_correlation,
        "all_directions_correct": all_directions_correct,
        "predicted_regression_count": predicted_regression_count,
        "quality_slo_exact_pair_count": exact_cost_count,
        "global_calibration_holdout_overlap_ids": sorted(overlap_ids),
        "cost_promotion_permitted": not cost_blockers,
        "reasons": reasons,
        "cost_promotion_blockers": cost_blockers,
        "pairs": result_pairs,
    }


def _audit_pair(pair: Any, artifact_root: Path) -> dict[str, Any]:
    rejection_codes: list[str] = []
    if not isinstance(pair, dict):
        return _empty_audit(["pair_not_object"])
    if set(pair) != PAIR_FIELDS:
        rejection_codes.append("pair_contract_fields_invalid")
    pair_id = pair.get("pair_id")
    if not _nonempty_string(pair_id):
        rejection_codes.append("pair_id_missing")
        pair_id = ""
    prediction_scope = pair.get("prediction_scope")
    measurement_scope = pair.get("measurement_scope")
    if not _valid_scope(prediction_scope) or not _valid_scope(measurement_scope):
        rejection_codes.append("scope_identity_incomplete")
    elif prediction_scope != measurement_scope:
        rejection_codes.append("scope_identity_mismatch")
    protocol = pair.get("protocol")
    if not isinstance(protocol, dict):
        rejection_codes.append("protocol_missing")
        protocol = {}
    else:
        _audit_protocol(protocol, rejection_codes)
    prediction = pair.get("prediction")
    measurement = pair.get("measurement")
    predicted_effect = _audit_observation(
        prediction,
        "prediction",
        rejection_codes,
        artifact_root,
        prediction_scope,
    )
    measured_effect = _audit_observation(
        measurement,
        "measurement",
        rejection_codes,
        artifact_root,
        measurement_scope,
    )
    higher_is_better = (
        measurement_scope.get("higher_is_better")
        if isinstance(measurement_scope, dict)
        else None
    )
    if predicted_effect is None or measured_effect is None or higher_is_better is None:
        predicted_benefit = None
        measured_benefit = None
        relative_error = None
        direction_correct = False
    else:
        orientation = 1.0 if higher_is_better else -1.0
        predicted_benefit = orientation * predicted_effect
        measured_benefit = orientation * measured_effect
        if measured_benefit == 0.0:
            rejection_codes.append("measured_effect_is_zero")
            relative_error = None
        else:
            relative_error = abs(predicted_benefit - measured_benefit) / abs(
                measured_benefit
            )
        direction_correct = _direction(predicted_benefit) == _direction(
            measured_benefit
        )
    exact_cost_evidence = False
    if _valid_scope(measurement_scope) and _nonempty_string(pair_id):
        exact_cost_evidence = _has_exact_cost_evidence(
            pair.get("cost_evidence"),
            str(pair_id),
            measurement_scope,
            artifact_root,
        )
    return {
        "pair_id": str(pair_id),
        "admission_status": "REJECTED",
        "rejection_codes": rejection_codes,
        "predicted_benefit_effect": predicted_benefit,
        "measured_benefit_effect": measured_benefit,
        "relative_effect_size_error": relative_error,
        "direction_correct": direction_correct,
        "exact_quality_slo_evidence": exact_cost_evidence,
        "protocol": protocol,
        "prediction_scope": prediction_scope,
        "measurement_scope": measurement_scope,
    }


def _empty_audit(rejection_codes: list[str]) -> dict[str, Any]:
    return {
        "pair_id": "",
        "admission_status": "REJECTED",
        "rejection_codes": rejection_codes,
        "predicted_benefit_effect": None,
        "measured_benefit_effect": None,
        "relative_effect_size_error": None,
        "direction_correct": False,
        "exact_quality_slo_evidence": False,
        "protocol": {},
        "prediction_scope": None,
        "measurement_scope": None,
    }


def _valid_scope(scope: Any) -> bool:
    if not isinstance(scope, dict) or set(scope) != set(SCOPE_FIELDS):
        return False
    for field in SCOPE_FIELDS[:-1]:
        if not _nonempty_string(scope[field]):
            return False
    return isinstance(scope["higher_is_better"], bool)


def _audit_protocol(protocol: dict[str, Any], rejection_codes: list[str]) -> None:
    if set(protocol) != PROTOCOL_FIELDS:
        rejection_codes.append("protocol_fields_invalid")
    locked = protocol.get("prediction_locked_at_unix_ms")
    started = protocol.get("measurement_started_at_unix_ms")
    if (
        not isinstance(locked, int)
        or isinstance(locked, bool)
        or not isinstance(started, int)
        or isinstance(started, bool)
        or locked >= started
    ):
        rejection_codes.append("prediction_not_locked_before_measurement")
    if not _hex_identifier(protocol.get("prediction_commit_id"), {40, 64}):
        rejection_codes.append("prediction_commit_id_missing")
    if protocol.get("blinded_holdout") is not True:
        rejection_codes.append("holdout_not_blinded")
    calibration_ids = protocol.get("calibration_case_ids")
    holdout_id = protocol.get("holdout_case_id")
    if (
        not isinstance(calibration_ids, list)
        or not calibration_ids
        or any(not _nonempty_string(case_id) for case_id in calibration_ids)
        or len(calibration_ids) != len(set(calibration_ids))
        or not _nonempty_string(holdout_id)
    ):
        rejection_codes.append("calibration_holdout_identity_incomplete")
    elif holdout_id in calibration_ids:
        rejection_codes.append("calibration_holdout_overlap")


def _audit_observation(
    observation: Any,
    label: str,
    rejection_codes: list[str],
    artifact_root: Path,
    expected_scope: Any,
) -> float | None:
    if not isinstance(observation, dict):
        rejection_codes.append(f"{label}_observation_missing")
        return None
    if set(observation) != OBSERVATION_FIELDS:
        rejection_codes.append(f"{label}_fields_invalid")
    if not _hex_identifier(observation.get("artifact_sha256"), {64}):
        rejection_codes.append(f"{label}_artifact_hash_missing")
    if not _hex_identifier(observation.get("artifact_content_id"), {64}):
        rejection_codes.append(f"{label}_content_id_missing")
    artifact_document = _verified_artifact_document(observation, artifact_root)
    if artifact_document is None or not _observation_binding_matches(
        observation,
        artifact_document,
        expected_scope,
    ):
        rejection_codes.append(f"{label}_artifact_binding_invalid")
    baseline = observation.get("baseline")
    candidate = observation.get("candidate")
    if not _finite_number(baseline) or not _finite_number(candidate) or baseline == 0:
        rejection_codes.append(f"{label}_effect_values_invalid")
        return None
    return (float(candidate) - float(baseline)) / abs(float(baseline))


def _global_overlap_ids(audits: list[dict[str, Any]]) -> set[str]:
    calibration_ids: set[str] = set()
    holdout_ids: set[str] = set()
    for audit in audits:
        if audit["rejection_codes"]:
            continue
        protocol = audit["protocol"]
        calibration_ids.update(protocol["calibration_case_ids"])
        holdout_ids.add(protocol["holdout_case_id"])
    return calibration_ids.intersection(holdout_ids)


def _has_exact_cost_evidence(
    cost_evidence: Any,
    pair_id: str,
    scope: dict[str, Any],
    artifact_root: Path,
) -> bool:
    if not isinstance(cost_evidence, dict) or set(cost_evidence) != {
        "quality",
        "slo",
    }:
        return False
    expected_scope = {field: scope[field] for field in EXECUTION_SCOPE_FIELDS}
    for evidence_kind in ("quality", "slo"):
        evidence = cost_evidence[evidence_kind]
        if not isinstance(evidence, dict) or set(evidence) != COST_EVIDENCE_FIELDS:
            return False
        if evidence.get("bound_pair_id") != pair_id:
            return False
        if evidence.get("execution_scope") != expected_scope:
            return False
        if not _hex_identifier(evidence.get("artifact_sha256"), {64}):
            return False
        if not _hex_identifier(evidence.get("artifact_content_id"), {64}):
            return False
        artifact_document = _verified_artifact_document(evidence, artifact_root)
        if artifact_document is None or not _cost_binding_matches(
            evidence,
            artifact_document,
            expected_scope,
        ):
            return False
        if not _nonempty_string(evidence.get("criterion_id")):
            return False
        if not _nonempty_string(evidence.get("criterion_revision")):
            return False
        if evidence.get("passed") is not True:
            return False
    return True


def _verified_artifact_document(
    binding: dict[str, Any], artifact_root: Path
) -> Any | None:
    relative_path = binding.get("artifact_path")
    if not _nonempty_string(relative_path):
        return None
    candidate_path = Path(relative_path)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        return None
    resolved_path = (artifact_root / candidate_path).resolve()
    try:
        resolved_path.relative_to(artifact_root)
    except ValueError:
        return None
    if not resolved_path.is_file():
        return None
    try:
        payload = resolved_path.read_bytes()
    except OSError:
        return None
    expected_hash = binding.get("artifact_sha256")
    if not _hex_identifier(expected_hash, {64}):
        return None
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        return None
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    content_id = binding.get("artifact_content_id")
    json_path = binding.get("artifact_content_id_json_path")
    if not _hex_identifier(content_id, {64}) or not _nonempty_string(json_path):
        return None
    if _resolve_json_path(document, json_path) != content_id:
        return None
    return document


def _observation_binding_matches(
    binding: dict[str, Any],
    document: Any,
    expected_scope: Any,
) -> bool:
    scope_path = binding.get("artifact_scope_json_path")
    baseline_path = binding.get("baseline_json_path")
    candidate_path = binding.get("candidate_json_path")
    if not all(
        _nonempty_string(path) for path in (scope_path, baseline_path, candidate_path)
    ):
        return False
    return (
        _resolve_json_path(document, scope_path) == expected_scope
        and _resolve_json_path(document, baseline_path) == binding.get("baseline")
        and _resolve_json_path(document, candidate_path) == binding.get("candidate")
    )


def _cost_binding_matches(
    binding: dict[str, Any],
    document: Any,
    expected_scope: dict[str, Any],
) -> bool:
    paths = (
        binding.get("artifact_scope_json_path"),
        binding.get("criterion_id_json_path"),
        binding.get("criterion_revision_json_path"),
        binding.get("passed_json_path"),
    )
    if not all(_nonempty_string(path) for path in paths):
        return False
    return (
        _resolve_json_path(document, paths[0]) == expected_scope
        and _resolve_json_path(document, paths[1]) == binding.get("criterion_id")
        and _resolve_json_path(document, paths[2]) == binding.get("criterion_revision")
        and _resolve_json_path(document, paths[3]) is binding.get("passed")
    )


def _resolve_json_path(document: Any, json_path: str) -> Any:
    current = document
    for part in json_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _gate_reasons(
    *,
    admitted_count: int,
    intervention_count: int,
    context_count: int,
    maximum_error: float | None,
    rank_correlation: float | None,
    all_directions_correct: bool,
    predicted_regression_count: int,
    overlap_ids: set[str],
) -> list[str]:
    reasons = []
    if admitted_count < GATE_SPEC["required_distinct_interventions"]:
        reasons.append("insufficient_admitted_pairs")
    if intervention_count < GATE_SPEC["required_distinct_interventions"]:
        reasons.append("insufficient_distinct_interventions")
    if context_count < GATE_SPEC["required_context_regimes"]:
        reasons.append("insufficient_context_regimes")
    if maximum_error is None:
        reasons.append("effect_size_error_unavailable")
    elif maximum_error > GATE_SPEC["maximum_relative_effect_size_error"]:
        reasons.append("effect_size_error_above_limit")
    if rank_correlation is None:
        reasons.append("rank_correlation_unavailable")
    elif rank_correlation < GATE_SPEC["minimum_spearman_rank_correlation"]:
        reasons.append("rank_correlation_below_limit")
    if not all_directions_correct:
        reasons.append("direction_validation_failed")
    if predicted_regression_count < 1:
        reasons.append("predicted_regression_missing")
    if overlap_ids:
        reasons.append("calibration_holdout_overlap")
    return reasons


def _spearman(first: list[float], second: list[float]) -> float | None:
    if len(first) != len(second) or len(first) < 2:
        return None
    first_ranks = _average_ranks(first)
    second_ranks = _average_ranks(second)
    first_mean = sum(first_ranks) / len(first_ranks)
    second_mean = sum(second_ranks) / len(second_ranks)
    covariance = sum(
        (left - first_mean) * (right - second_mean)
        for left, right in zip(first_ranks, second_ranks, strict=True)
    )
    first_variance = sum((rank - first_mean) ** 2 for rank in first_ranks)
    second_variance = sum((rank - second_mean) ** 2 for rank in second_ranks)
    if first_variance == 0.0 or second_variance == 0.0:
        return None
    return covariance / math.sqrt(first_variance * second_variance)


def _average_ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(indexed):
        end = start + 1
        while end < len(indexed) and indexed[end][1] == indexed[start][1]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[indexed[position][0]] = average_rank
        start = end
    return ranks


def _direction(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _reject(audit: dict[str, Any], code: str) -> None:
    if code not in audit["rejection_codes"]:
        audit["rejection_codes"].append(code)


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _hex_identifier(value: Any, lengths: set[int]) -> bool:
    if not isinstance(value, str) or len(value) not in lengths:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
