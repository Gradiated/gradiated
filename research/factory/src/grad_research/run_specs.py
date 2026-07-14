from __future__ import annotations

from typing import Any

from .records import FIDELITIES, SCIENTIFIC_OUTCOMES
from .util import (
    ValidationError,
    content_hash,
    require_id,
    require_number,
    require_sha256,
    require_string_list,
    require_text,
)


def _required(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{path} must be an object")
    missing = sorted(fields - value.keys())
    if missing:
        raise ValidationError(f"{path} missing required fields: {', '.join(missing)}")
    return value


COMMON_RUN_FIELDS = {
    "schema_version",
    "run_id",
    "program_id",
    "scout_id",
    "fidelity",
    "baseline_id",
    "baseline_sha256",
    "control_id",
    "candidate_id",
    "changed_variable",
    "claim_scope",
    "prediction",
    "measurement_contract",
    "gates",
}


def validate_common_run_spec(spec: dict[str, Any]) -> dict[str, Any]:
    _required(spec, COMMON_RUN_FIELDS, "run spec")
    if spec["schema_version"] != 1:
        raise ValidationError("run spec schema_version must be 1")
    for name in ("run_id", "program_id", "scout_id", "baseline_id"):
        require_id(f"run spec.{name}", spec[name])
    require_sha256("run spec.baseline_sha256", spec["baseline_sha256"])
    if spec["fidelity"] not in FIDELITIES:
        raise ValidationError("run spec.fidelity is unsupported")
    for name in ("control_id", "candidate_id", "changed_variable"):
        require_text(f"run spec.{name}", spec[name])
    if spec["control_id"] == spec["candidate_id"]:
        raise ValidationError("run spec candidate must differ from control")
    scope = spec["claim_scope"]
    if not isinstance(scope, dict) or not scope:
        raise ValidationError("run spec.claim_scope must be a nonempty object")
    for name, value in scope.items():
        require_text(f"run spec.claim_scope.{name}", value)
    prediction = _required(
        spec["prediction"],
        {
            "metric",
            "expected_direction",
            "point_estimate_fraction",
            "minimum_effect_fraction",
            "plausible_ceiling_fraction",
            "falsifier",
        },
        "run spec.prediction",
    )
    require_text("run spec.prediction.metric", prediction["metric"])
    if prediction["expected_direction"] not in {"increase", "decrease", "neutral"}:
        raise ValidationError("run spec.prediction.expected_direction is unsupported")
    require_number("run spec.prediction.point_estimate_fraction", prediction["point_estimate_fraction"])
    minimum = require_number(
        "run spec.prediction.minimum_effect_fraction",
        prediction["minimum_effect_fraction"],
        nonnegative=True,
    )
    ceiling = require_number(
        "run spec.prediction.plausible_ceiling_fraction",
        prediction["plausible_ceiling_fraction"],
        nonnegative=True,
    )
    if ceiling < minimum:
        raise ValidationError("run spec prediction ceiling is below its materiality gate")
    require_text("run spec.prediction.falsifier", prediction["falsifier"])
    measurement = _required(
        spec["measurement_contract"],
        {"protocol", "effect_formula", "minimum_candidate_repetitions", "statistic"},
        "run spec.measurement_contract",
    )
    if measurement["protocol"] not in {"bracketed", "randomized_paired", "deterministic"}:
        raise ValidationError("run spec.measurement_contract.protocol is unsupported")
    if measurement["effect_formula"] not in {
        "candidate_over_control_minus_one",
        "control_over_candidate_minus_one",
    }:
        raise ValidationError("run spec.measurement_contract.effect_formula is unsupported")
    if (
        type(measurement["minimum_candidate_repetitions"]) is not int
        or measurement["minimum_candidate_repetitions"] <= 0
    ):
        raise ValidationError(
            "run spec.measurement_contract.minimum_candidate_repetitions must be a positive integer"
        )
    if measurement["statistic"] != "median":
        raise ValidationError("run spec.measurement_contract.statistic must be median")
    gates = _required(spec["gates"], {"correctness", "quality", "slo"}, "run spec.gates")
    for name in ("correctness", "quality", "slo"):
        gate = _required(gates[name], {"policy_sha256", "required"}, f"run spec.gates.{name}")
        require_sha256(f"run spec.gates.{name}.policy_sha256", gate["policy_sha256"])
        if gate["required"] is not True:
            raise ValidationError(f"run spec.gates.{name}.required must be true")
    return spec


def validate_local_run(spec: dict[str, Any]) -> dict[str, Any]:
    validate_common_run_spec(spec)
    _required(
        spec,
        COMMON_RUN_FIELDS
        | {
            "execution_kind",
            "command",
            "seed",
            "timeout_seconds",
            "max_cost_usd",
            "artifact_refs",
        },
        "local run spec",
    )
    if spec["execution_kind"] != "local":
        raise ValidationError("local run spec.execution_kind must be local")
    if spec["fidelity"] in {"matched_server", "workload_frontier"}:
        raise ValidationError("server and workload-frontier results require paid admission")
    require_text("local run spec.command", spec["command"])
    if not isinstance(spec["seed"], (str, int)) or isinstance(spec["seed"], bool):
        raise ValidationError("local run spec.seed must be a string or integer")
    if type(spec["timeout_seconds"]) is not int or spec["timeout_seconds"] <= 0:
        raise ValidationError("local run spec.timeout_seconds must be a positive integer")
    if require_number("local run spec.max_cost_usd", spec["max_cost_usd"], nonnegative=True) != 0:
        raise ValidationError("local run specs are zero-paid-cost; use paid admission otherwise")
    for index, reference in enumerate(require_string_list("local run spec.artifact_refs", spec["artifact_refs"])):
        require_sha256(f"local run spec.artifact_refs[{index}]", reference)
    return spec


def validate_result_binding(result: dict[str, Any], spec: dict[str, Any]) -> None:
    validate_common_run_spec(spec)
    exact = {
        "run_id": spec["run_id"],
        "scout_id": spec["scout_id"],
        "fidelity": spec["fidelity"],
        "scope": spec["claim_scope"],
        "control_id": spec["control_id"],
        "candidate_id": spec["candidate_id"],
        "changed_variable": spec["changed_variable"],
        "baseline_sha256": spec["baseline_sha256"],
        "prediction_sha256": content_hash(spec["prediction"]),
    }
    changed = sorted(name for name, expected in exact.items() if result.get(name) != expected)
    if changed:
        raise ValidationError("result differs from its immutable run spec: " + ", ".join(changed))
    if result["outcome_class"] in SCIENTIFIC_OUTCOMES:
        if result.get("primary_metric") != spec["prediction"]["metric"]:
            raise ValidationError("result primary metric differs from its prediction")
        if float(result["predicted_effect_fraction"]) != float(
            spec["prediction"]["point_estimate_fraction"]
        ):
            raise ValidationError("result predicted effect differs from its preregistration")
    maximum_cost = (
        spec["budget"]["max_spend_usd"] if "budget" in spec else spec.get("max_cost_usd", 0)
    )
    if float(result["cost_usd"]) > float(maximum_cost):
        raise ValidationError("result cost exceeds its run specification")
