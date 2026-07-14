from __future__ import annotations

from typing import Any

from .util import (
    ValidationError,
    require_id,
    require_number,
    require_probability,
    require_sha256,
    require_string_list,
    require_text,
)


EVIDENCE_CLASSES = {
    "measured",
    "analytical",
    "vendor_reported",
    "derived",
    "inferred",
    "synthetic",
}
OUTCOME_CLASSES = {
    "diagnostic_valid",
    "scientific_positive",
    "scientific_negative",
    "scientific_mixed",
    "harness_invalid",
    "operational_failure",
}
SCIENTIFIC_OUTCOMES = {
    "scientific_positive",
    "scientific_negative",
    "scientific_mixed",
}
DIAGNOSTIC_OUTCOMES = {"diagnostic_valid"}
SUCCESSFUL_OUTCOMES = SCIENTIFIC_OUTCOMES | DIAGNOSTIC_OUTCOMES
FIDELITIES = {
    "bound",
    "analytical",
    "simulation",
    "reference",
    "reduced_replay",
    "exact_shape",
    "target_gpu_component",
    "matched_server",
    "workload_frontier",
}
TIME_SEMANTICS = {
    "exclusive_wall_time",
    "critical_path_union",
    "inclusive_duration",
    "summed_component_duration",
    "counter",
    "derived_bound",
    "proxy",
}


def _required(value: dict[str, Any], names: set[str], record: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError(f"{record} must be an object")
    missing = sorted(names - value.keys())
    if missing:
        raise ValidationError(f"{record} missing required fields: {', '.join(missing)}")


def validate_baseline(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "id",
        "model_revision",
        "checkpoint_manifest_sha256",
        "tokenizer_manifest_sha256",
        "runtime_manifest_sha256",
        "workload_manifest_sha256",
        "quality_policy_sha256",
        "slo_policy_sha256",
        "cost_denominator",
    }
    _required(value, required, "baseline")
    if value["schema_version"] != 1:
        raise ValidationError("baseline schema_version must be 1")
    require_id("baseline.id", value["id"])
    require_text("baseline.model_revision", value["model_revision"])
    for name in required:
        if name.endswith("_sha256"):
            require_sha256(f"baseline.{name}", value[name])
    require_text("baseline.cost_denominator", value["cost_denominator"])
    return value


def validate_observation(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "id",
        "cycle",
        "evidence_class",
        "summary",
        "scope",
        "metrics",
        "instrumentation_gaps",
        "artifact_refs",
    }
    _required(value, required, "observation")
    if value["schema_version"] != 1:
        raise ValidationError("observation schema_version must be 1")
    require_id("observation.id", value["id"])
    if type(value["cycle"]) is not int or value["cycle"] < 1:
        raise ValidationError("observation.cycle must be a positive integer")
    if value["evidence_class"] not in EVIDENCE_CLASSES:
        raise ValidationError("observation.evidence_class is unsupported")
    require_text("observation.summary", value["summary"])
    scope = value["scope"]
    scope_fields = {"model", "revision", "workload", "phase", "concurrency", "software", "hardware"}
    _required(scope, scope_fields, "observation.scope")
    for field in scope_fields:
        require_text(f"observation.scope.{field}", scope[field])
    metrics = value["metrics"]
    if not isinstance(metrics, list) or not metrics:
        raise ValidationError("observation.metrics must be a nonempty list")
    for index, metric in enumerate(metrics):
        _required(metric, {"name", "value", "unit", "time_semantics", "coverage"}, f"observation.metrics[{index}]")
        require_text(f"observation.metrics[{index}].name", metric["name"])
        if metric["value"] != "unknown":
            require_number(f"observation.metrics[{index}].value", metric["value"])
        require_text(f"observation.metrics[{index}].unit", metric["unit"])
        if metric["time_semantics"] not in TIME_SEMANTICS:
            raise ValidationError(f"observation.metrics[{index}].time_semantics is unsupported")
        require_probability(f"observation.metrics[{index}].coverage", metric["coverage"])
    gaps = value["instrumentation_gaps"]
    if not isinstance(gaps, list):
        raise ValidationError("observation.instrumentation_gaps must be a list")
    for index, gap in enumerate(gaps):
        _required(
            gap,
            {"signal", "decision_blocked", "next_probe"},
            f"observation.instrumentation_gaps[{index}]",
        )
        require_id(f"observation.instrumentation_gaps[{index}].signal", gap["signal"])
        require_text(
            f"observation.instrumentation_gaps[{index}].decision_blocked", gap["decision_blocked"]
        )
        require_text(f"observation.instrumentation_gaps[{index}].next_probe", gap["next_probe"])
    for index, artifact in enumerate(require_string_list("observation.artifact_refs", value["artifact_refs"])):
        require_sha256(f"observation.artifact_refs[{index}]", artifact)
    return value


def validate_result(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "id",
        "run_id",
        "scout_id",
        "control_id",
        "candidate_id",
        "changed_variable",
        "baseline_sha256",
        "prediction_sha256",
        "outcome_class",
        "fidelity",
        "scope",
        "cost_usd",
        "artifact_refs",
        "next_action",
    }
    _required(value, required, "result")
    if value["schema_version"] != 1:
        raise ValidationError("result schema_version must be 1")
    for name in ("id", "run_id", "scout_id"):
        require_id(f"result.{name}", value[name])
    for name in ("control_id", "candidate_id", "changed_variable"):
        require_text(f"result.{name}", value[name])
    require_sha256("result.baseline_sha256", value["baseline_sha256"])
    require_sha256("result.prediction_sha256", value["prediction_sha256"])
    outcome = value["outcome_class"]
    if outcome not in OUTCOME_CLASSES:
        raise ValidationError("result.outcome_class is unsupported")
    if value["fidelity"] not in FIDELITIES:
        raise ValidationError("result.fidelity is unsupported")
    if not isinstance(value["scope"], dict) or not value["scope"]:
        raise ValidationError("result.scope must be a nonempty object")
    for name, item in value["scope"].items():
        require_text(f"result.scope.{name}", item)
    require_number("result.cost_usd", value["cost_usd"], nonnegative=True)
    for index, artifact in enumerate(require_string_list("result.artifact_refs", value["artifact_refs"])):
        require_sha256(f"result.artifact_refs[{index}]", artifact)
    require_text("result.next_action", value["next_action"])

    if outcome in SCIENTIFIC_OUTCOMES:
        _required(
            value,
            {
                "gates",
                "primary_metric",
                "observed_effect_fraction",
                "predicted_effect_fraction",
                "residual_bottleneck",
            },
            "scientific result",
        )
        require_text("result.primary_metric", value["primary_metric"])
        gates = value["gates"]
        _required(gates, {"correctness", "quality", "slo"}, "result.gates")
        if gates["correctness"] is not True:
            raise ValidationError("scientific results require correctness")
        if value["fidelity"] in {"matched_server", "workload_frontier"}:
            if outcome in {"scientific_positive", "scientific_negative"} and not all(
                gates[name] is True for name in ("correctness", "quality", "slo")
            ):
                raise ValidationError("matched server and frontier results require all gates")
        elif any(gates[name] not in {True, "not_applicable"} for name in ("quality", "slo")):
            raise ValidationError("lower-fidelity quality and SLO gates must pass or be not_applicable")
        if outcome == "scientific_mixed" and not any(gates.get(name) is True for name in ("correctness", "quality", "slo")):
            raise ValidationError("scientific_mixed requires at least one valid subclaim")
        require_number("result.observed_effect_fraction", value["observed_effect_fraction"])
        require_number("result.predicted_effect_fraction", value["predicted_effect_fraction"])
        require_text("result.residual_bottleneck", value["residual_bottleneck"])
    elif outcome in DIAGNOSTIC_OUTCOMES:
        _required(
            value,
            {"gates", "diagnostic_summary", "residual_bottleneck"},
            "diagnostic result",
        )
        gates = value["gates"]
        _required(gates, {"correctness", "quality", "slo"}, "result.gates")
        if any(gates[name] is not True for name in ("correctness", "quality", "slo")):
            raise ValidationError("diagnostic_valid requires every preregistered gate")
        require_text("result.diagnostic_summary", value["diagnostic_summary"])
        require_text("result.residual_bottleneck", value["residual_bottleneck"])
    else:
        require_text("result.failure_class", value.get("failure_class"))
    return value
