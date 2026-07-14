from __future__ import annotations

import statistics
from typing import Any, Iterable

from .records import FIDELITIES, OUTCOME_CLASSES
from .util import ValidationError, require_number, require_probability


FIDELITY_ORDER = [
    "bound",
    "analytical",
    "simulation",
    "reference",
    "reduced_replay",
    "exact_shape",
    "target_gpu_component",
    "matched_server",
    "workload_frontier",
]
WALL_TIME_SEMANTICS = {"exclusive_wall_time", "critical_path_union"}


def analyze_metric_semantics(metrics: Iterable[dict[str, Any]], *, minimum_coverage: float = 0.95) -> dict[str, Any]:
    require_probability("minimum_coverage", minimum_coverage)
    admissible = []
    diagnostic = []
    for original in metrics:
        metric = dict(original)
        coverage = require_probability(f"{metric.get('name', 'metric')}.coverage", metric.get("coverage"))
        value = metric.get("value")
        if value != "unknown":
            require_number(f"{metric.get('name', 'metric')}.value", value)
        if metric.get("time_semantics") in WALL_TIME_SEMANTICS and coverage >= minimum_coverage:
            admissible.append(metric)
        else:
            diagnostic.append(metric)
    fractions = [
        float(row["value"])
        for row in admissible
        if row.get("unit") == "fraction" and row.get("value") != "unknown"
    ]
    return {
        "schema_version": 1,
        "wall_time_admissible": admissible,
        "diagnostic_only": diagnostic,
        "largest_admissible_fraction": max(fractions) if fractions else None,
        "claim_rule": "only exclusive wall time or dependency-union critical-path metrics with sufficient coverage may be used as wall-time shares",
    }


def score_prediction(prediction: dict[str, Any], *, observed_effect_fraction: float) -> dict[str, Any]:
    observed = require_number("observed_effect_fraction", observed_effect_fraction)
    direction = prediction.get("expected_direction")
    if direction not in {"increase", "decrease", "neutral"}:
        raise ValidationError("prediction.expected_direction is unsupported")
    gate = require_number("prediction.minimum_effect_fraction", prediction.get("minimum_effect_fraction"), nonnegative=True)
    if direction == "increase":
        direction_pass = observed > 0
        materiality_pass = observed >= gate
    elif direction == "decrease":
        direction_pass = observed < 0
        materiality_pass = observed <= -gate
    else:
        direction_pass = abs(observed) <= gate
        materiality_pass = direction_pass
    estimate = prediction.get("point_estimate_fraction")
    magnitude_error = None if estimate is None else observed - require_number("prediction.point_estimate_fraction", estimate)
    return {
        "schema_version": 1,
        "observed_effect_fraction": observed,
        "direction_pass": direction_pass,
        "materiality_gate_pass": materiality_pass,
        "magnitude_error_fraction": magnitude_error,
        "calibration_class": (
            "direction_miss"
            if not direction_pass
            else "right_direction_below_gate"
            if not materiality_pass
            else "material_effect"
        ),
    }


def evaluate_proxy_transfer(
    *,
    component_effect_fraction: float,
    server_effects: Iterable[float],
    materiality_gate: float,
    independent_candidate_repetitions: int,
) -> dict[str, Any]:
    component = require_number("component_effect_fraction", component_effect_fraction)
    effects = [require_number("server_effect", value) for value in server_effects]
    if not effects:
        raise ValidationError("server_effects must be nonempty")
    gate = require_number("materiality_gate", materiality_gate, nonnegative=True)
    if independent_candidate_repetitions != len(effects):
        raise ValidationError("independent_candidate_repetitions must match server effects")
    median = statistics.median(effects)
    component_positive = component >= gate
    server_pass = median >= gate
    if component_positive and not server_pass:
        outcome = "scientific_mixed"
        action = "stop_proxy_lineage"
    elif server_pass:
        outcome = "scientific_positive"
        action = "replicate_or_expand_frontier"
    else:
        outcome = "scientific_negative"
        action = "stop_lineage"
    return {
        "schema_version": 1,
        "outcome_class": outcome,
        "lineage_decision": action,
        "component_effect_fraction": component,
        "server_effects": effects,
        "median_server_effect_fraction": median,
        "materiality_gate_fraction": gate,
        "component_gate_pass": component_positive,
        "server_gate_pass": server_pass,
        "transfer_gap_fraction": median - component,
        "independent_candidate_repetitions": independent_candidate_repetitions,
        "confidence_interval_permitted": independent_candidate_repetitions >= 3,
        "claim_limit": "component and server effects retain separate scopes; fewer than three candidate repetitions are descriptive only",
    }


def promotion_decision(
    *,
    fidelity: str,
    outcome_class: str,
    plausible_end_to_end_ceiling_fraction: float | None,
    campaign_gate_fraction: float,
) -> dict[str, Any]:
    if fidelity not in FIDELITIES:
        raise ValidationError("fidelity is unsupported")
    if outcome_class not in OUTCOME_CLASSES:
        raise ValidationError("outcome_class is unsupported")
    gate = require_number("campaign_gate_fraction", campaign_gate_fraction, nonnegative=True)
    ceiling = None if plausible_end_to_end_ceiling_fraction is None else require_number(
        "plausible_end_to_end_ceiling_fraction", plausible_end_to_end_ceiling_fraction, nonnegative=True
    )
    if outcome_class in {"harness_invalid", "operational_failure"}:
        return {"action": "repair_or_change_operational_path", "claim_permitted": False}
    if outcome_class == "scientific_negative":
        return {"action": "stop_lineage", "claim_permitted": False}
    if outcome_class == "scientific_mixed":
        return {"action": "measure_competing_explanations", "claim_permitted": False}
    if ceiling is not None and ceiling < gate:
        return {"action": "stop_below_end_to_end_ceiling", "claim_permitted": False}
    index = FIDELITY_ORDER.index(fidelity)
    if index < FIDELITY_ORDER.index("matched_server"):
        return {
            "action": "measure_next_fidelity",
            "next_fidelity": FIDELITY_ORDER[index + 1],
            "claim_permitted": False,
        }
    if fidelity == "matched_server":
        return {"action": "replicate_then_measure_workload_frontier", "claim_permitted": False}
    return {"action": "eligible_for_scope_matched_claim_audit", "claim_permitted": True}
