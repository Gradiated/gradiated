from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .records import FIDELITIES
from .run_specs import validate_common_run_spec
from .telemetry import required_artifact_roles, validate_telemetry_contract
from .util import (
    ValidationError,
    content_hash,
    parse_utc,
    require_id,
    require_sha256,
    require_string_list,
    require_text,
    safe_relative_path,
)


class AdmissionError(ValidationError):
    """A paid run is incomplete or exceeds its authority."""


PREFLIGHT_CHECKS = {
    "provider_fixture",
    "checkpoint_closure",
    "tokenizer_identity",
    "runtime_probe",
    "configuration_identity",
    "protocol_fixture",
    "parser_fixture",
    "artifact_paths",
    "local_tests",
}
PREFLIGHT_BINDINGS = {
    "provider_fixture": "harness_sha256",
    "checkpoint_closure": "checkpoint_manifest_sha256",
    "tokenizer_identity": "tokenizer_manifest_sha256",
    "runtime_probe": "runtime_manifest_sha256",
    "configuration_identity": "configuration_sha256",
    "protocol_fixture": "harness_sha256",
    "parser_fixture": "harness_sha256",
    "artifact_paths": "harness_sha256",
    "local_tests": "harness_sha256",
}
IDENTITY_FIELDS = {
    "model_revision",
    "checkpoint_manifest_sha256",
    "tokenizer_manifest_sha256",
    "runtime_manifest_sha256",
    "workload_manifest_sha256",
    "harness_sha256",
    "configuration_sha256",
    "hardware_scope",
}


def _required(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AdmissionError(f"{path} must be an object")
    missing = sorted(fields - value.keys())
    if missing:
        raise AdmissionError(f"{path} missing required fields: {', '.join(missing)}")
    return value


def _decimal(name: str, value: Any, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise AdmissionError(f"{name} must be decimal-compatible")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise AdmissionError(f"{name} must be decimal-compatible") from error
    if not number.is_finite():
        raise AdmissionError(f"{name} must be finite")
    if positive and number <= 0:
        raise AdmissionError(f"{name} must be positive")
    if nonnegative and number < 0:
        raise AdmissionError(f"{name} must be nonnegative")
    return number


def validate_paid_run(spec: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    required = {
        "schema_version",
        "run_id",
        "program_id",
        "campaign_id",
        "scout_id",
        "baseline_id",
        "baseline_sha256",
        "arm_role",
        "fidelity",
        "control_id",
        "candidate_id",
        "changed_variable",
        "setup_key",
        "identities",
        "candidate_identity_overrides",
        "changed_identity_fields",
        "claim_scope",
        "gates",
        "prediction",
        "budget",
        "watchdog",
        "provider_contract",
        "preflight",
        "telemetry_contract",
        "artifact_contract",
        "cleanup",
    }
    _required(spec, required, "paid run")
    try:
        validate_common_run_spec(spec)
    except ValidationError as error:
        raise AdmissionError(str(error)) from error
    if spec["schema_version"] != 1:
        raise AdmissionError("paid run schema_version must be 1")
    for name in ("run_id", "program_id", "campaign_id", "scout_id"):
        require_id(f"paid run.{name}", spec[name])
    if spec["arm_role"] not in {"control", "candidate", "diagnostic", "repair"}:
        raise AdmissionError("paid run.arm_role is unsupported")
    if spec["fidelity"] not in FIDELITIES:
        raise AdmissionError("paid run.fidelity is unsupported")
    for name in ("control_id", "candidate_id", "changed_variable", "setup_key"):
        require_text(f"paid run.{name}", spec[name])
    if spec["arm_role"] == "candidate" and spec["candidate_id"] == spec["control_id"]:
        raise AdmissionError("candidate arm must differ from the control")

    identities = _required(spec["identities"], IDENTITY_FIELDS, "paid run.identities")
    require_text("paid run.identities.model_revision", identities["model_revision"])
    require_text("paid run.identities.hardware_scope", identities["hardware_scope"])
    for name in IDENTITY_FIELDS:
        if name.endswith("_sha256"):
            require_sha256(f"paid run.identities.{name}", identities[name])

    overrides = spec["candidate_identity_overrides"]
    if not isinstance(overrides, dict) or not overrides:
        raise AdmissionError("paid run.candidate_identity_overrides must be a nonempty object")
    invalid_override_fields = sorted(set(overrides) - IDENTITY_FIELDS)
    if invalid_override_fields:
        raise AdmissionError(
            "candidate identity overrides unsupported fields: " + ", ".join(invalid_override_fields)
        )
    for name, value in overrides.items():
        if name.endswith("_sha256"):
            require_sha256(f"paid run.candidate_identity_overrides.{name}", value)
        else:
            require_text(f"paid run.candidate_identity_overrides.{name}", value)
    changed_identity_fields = set(
        require_string_list("paid run.changed_identity_fields", spec["changed_identity_fields"])
    )
    actual_changed_fields = {name for name, value in overrides.items() if identities[name] != value}
    if changed_identity_fields != actual_changed_fields:
        raise AdmissionError("changed_identity_fields does not match the exact control/candidate identity diff")
    candidate_identities = {**identities, **overrides}

    gates = _required(spec["gates"], {"correctness", "quality", "slo"}, "paid run.gates")
    for name in ("correctness", "quality", "slo"):
        gate = _required(gates[name], {"policy_sha256", "required"}, f"paid run.gates.{name}")
        require_sha256(f"paid run.gates.{name}.policy_sha256", gate["policy_sha256"])
        if gate["required"] is not True:
            raise AdmissionError(f"paid run.gates.{name}.required must be true")

    prediction = _required(
        spec["prediction"],
        {"metric", "expected_direction", "minimum_effect_fraction", "plausible_ceiling_fraction", "falsifier"},
        "paid run.prediction",
    )
    require_text("paid run.prediction.metric", prediction["metric"])
    if prediction["expected_direction"] not in {"increase", "decrease", "neutral"}:
        raise AdmissionError("paid run.prediction.expected_direction is unsupported")
    minimum_effect = _decimal("paid run.prediction.minimum_effect_fraction", prediction["minimum_effect_fraction"], nonnegative=True)
    plausible_ceiling = _decimal("paid run.prediction.plausible_ceiling_fraction", prediction["plausible_ceiling_fraction"], nonnegative=True)
    if plausible_ceiling < minimum_effect:
        raise AdmissionError("plausible ceiling is below the promotion gate")
    require_text("paid run.prediction.falsifier", prediction["falsifier"])

    budget = _required(
        spec["budget"],
        {"hourly_rate_usd", "timeout_seconds", "cleanup_reserve_usd", "max_spend_usd"},
        "paid run.budget",
    )
    hourly = _decimal("paid run.budget.hourly_rate_usd", budget["hourly_rate_usd"], positive=True)
    if type(budget["timeout_seconds"]) is not int or budget["timeout_seconds"] <= 0:
        raise AdmissionError("paid run.budget.timeout_seconds must be a positive integer")
    cleanup_reserve = _decimal("paid run.budget.cleanup_reserve_usd", budget["cleanup_reserve_usd"], positive=True)
    maximum_spend = _decimal("paid run.budget.max_spend_usd", budget["max_spend_usd"], positive=True)
    maximum_exposure = hourly * Decimal(budget["timeout_seconds"]) / Decimal(3600) + cleanup_reserve
    if maximum_spend < maximum_exposure:
        raise AdmissionError("max_spend_usd is below maximum exposure plus cleanup reserve")

    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() != timezone.utc.utcoffset(clock):
        raise AdmissionError("admission clock must be authoritative UTC")
    watchdog = _required(
        spec["watchdog"],
        {"independent", "absolute_deadline_utc", "delete_on_deadline", "verify_absent"},
        "paid run.watchdog",
    )
    for name in ("independent", "delete_on_deadline", "verify_absent"):
        if watchdog[name] is not True:
            raise AdmissionError(f"paid run.watchdog.{name} must be true")
    deadline = parse_utc(watchdog["absolute_deadline_utc"], "paid run.watchdog.absolute_deadline_utc")
    if deadline <= clock:
        raise AdmissionError("watchdog deadline must be in the future")
    if deadline > clock + timedelta(seconds=budget["timeout_seconds"]):
        raise AdmissionError("watchdog deadline exceeds the paid-run timeout")

    provider = _required(
        spec["provider_contract"],
        {"provider", "idempotency_key", "resource_tags", "inventory_reconcile"},
        "paid run.provider_contract",
    )
    require_id("paid run.provider_contract.provider", provider["provider"])
    require_id("paid run.provider_contract.idempotency_key", provider["idempotency_key"])
    tags = _required(
        provider["resource_tags"],
        {"program_id", "campaign_id", "run_id"},
        "paid run.provider_contract.resource_tags",
    )
    expected_tags = {
        "program_id": spec["program_id"],
        "campaign_id": spec["campaign_id"],
        "run_id": spec["run_id"],
    }
    if any(tags[name] != value for name, value in expected_tags.items()):
        raise AdmissionError("provider resource tags are not bound to this run")
    if provider["inventory_reconcile"] is not True:
        raise AdmissionError("paid run provider contract must support inventory reconciliation")

    preflight = _required(spec["preflight"], PREFLIGHT_CHECKS, "paid run.preflight")
    for name in sorted(PREFLIGHT_CHECKS):
        check = _required(
            preflight[name],
            {"pass", "evidence_sha256", "bound_sha256"},
            f"paid run.preflight.{name}",
        )
        if check["pass"] is not True:
            raise AdmissionError(f"paid run.preflight.{name} did not pass")
        require_sha256(f"paid run.preflight.{name}.evidence_sha256", check["evidence_sha256"])
        require_sha256(f"paid run.preflight.{name}.bound_sha256", check["bound_sha256"])
        expected_binding = candidate_identities[PREFLIGHT_BINDINGS[name]]
        if check["bound_sha256"] != expected_binding:
            raise AdmissionError(f"paid run.preflight.{name} is bound to the wrong identity")

    try:
        telemetry = validate_telemetry_contract(spec["telemetry_contract"])
    except ValidationError as error:
        raise AdmissionError(str(error)) from error
    telemetry_contract = spec["telemetry_contract"]
    if telemetry_contract["scoring_mode"] == "diagnostic_only" and spec["arm_role"] not in {
        "diagnostic",
        "repair",
    }:
        raise AdmissionError("diagnostic-only telemetry requires a diagnostic or repair arm")
    artifacts = _required(
        spec["artifact_contract"], {"root", "required", "hash_manifest"}, "paid run.artifact_contract"
    )
    artifact_root = safe_relative_path("paid run.artifact_contract.root", artifacts["root"])
    if artifact_root != f"runs/{spec['run_id']}":
        raise AdmissionError("paid run.artifact_contract.root must be runs/<run_id>")
    if not isinstance(artifacts["required"], list) or not artifacts["required"]:
        raise AdmissionError("paid run.artifact_contract.required must be a nonempty list")
    artifact_roles: set[str] = {"run_spec"}
    artifact_paths: set[str] = set()
    for index, artifact in enumerate(artifacts["required"]):
        row = _required(
            artifact,
            {"role", "path", "media_type"},
            f"paid run.artifact_contract.required[{index}]",
        )
        role = require_id(f"paid run.artifact_contract.required[{index}].role", row["role"])
        path = safe_relative_path(f"paid run.artifact_contract.required[{index}].path", row["path"])
        require_text(f"paid run.artifact_contract.required[{index}].media_type", row["media_type"])
        if role in artifact_roles:
            raise AdmissionError(f"paid run artifact role {role} is duplicated")
        if path in artifact_paths:
            raise AdmissionError(f"paid run artifact path {path} is duplicated")
        artifact_roles.add(role)
        artifact_paths.add(path)
    expected_roles = required_artifact_roles(telemetry_contract)
    if artifact_roles != expected_roles:
        missing = sorted(expected_roles - artifact_roles)
        extra = sorted(artifact_roles - expected_roles)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unregistered " + ", ".join(extra))
        raise AdmissionError("paid run artifact roles do not match telemetry: " + "; ".join(details))
    if artifacts["hash_manifest"] is not True:
        raise AdmissionError("paid run.artifact_contract.hash_manifest must be true")

    cleanup = _required(
        spec["cleanup"],
        {"delete_compute", "delete_attached_storage", "verify_get_not_found", "verify_inventory_absent"},
        "paid run.cleanup",
    )
    for name in sorted(cleanup):
        if cleanup[name] is not True:
            raise AdmissionError(f"paid run.cleanup.{name} must be true")

    return {
        "schema_version": 1,
        "decision": "admit",
        "admission_sha256": content_hash(spec),
        "reserved_usd": float(maximum_spend),
        "maximum_exposure_usd": float(maximum_exposure),
        "cleanup_reserve_usd": float(cleanup_reserve),
        "absolute_deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
        "telemetry_contract_sha256": telemetry["contract_sha256"],
        "telemetry_capture_categories": telemetry["capture_categories"],
        "telemetry_unavailable_signals": telemetry["unavailable_signal_names"],
        "control_identity_sha256": content_hash(identities),
        "candidate_identity_sha256": content_hash(candidate_identities),
        "provider_mutation_permitted": True,
        "provider_idempotency_key": provider["idempotency_key"],
        "provider_resource_tags": tags,
    }
