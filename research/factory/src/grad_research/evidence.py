from __future__ import annotations

import json
import statistics
from typing import Any

from .telemetry import validate_telemetry_contract, validate_telemetry_summary
from .util import ValidationError, content_hash, require_number, require_text


def _role_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    roles: dict[str, dict[str, Any]] = {}
    for entry in manifest["entries"]:
        role = entry["role"]
        if role in roles:
            raise ValidationError(f"evidence bundle contains duplicate role {role}")
        roles[role] = entry
    return roles


def _json_object(store: Any, entry: dict[str, Any], role: str) -> dict[str, Any]:
    value = store.load_json_reference(entry["sha256"])
    if not isinstance(value, dict):
        raise ValidationError(f"{role} evidence must be a JSON object")
    return value


def _telemetry_rows(store: Any, entry: dict[str, Any]) -> list[dict[str, Any]]:
    path = store.verify_reference(entry["sha256"], deep=True)
    if entry["media_type"] == "application/x-ndjson":
        rows = []
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValidationError(
                    f"telemetry role {entry['role']} has invalid JSON on line {line_number}"
                ) from error
            if not isinstance(row, dict):
                raise ValidationError(f"telemetry role {entry['role']} line {line_number} is not an object")
            rows.append(row)
        return rows
    value = _json_object(store, entry, entry["role"])
    records = value.get("telemetry_records")
    if records is None:
        return [value]
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValidationError(f"telemetry role {entry['role']} has malformed telemetry_records")
    return records


def _close(name: str, actual: float, expected: float, *, tolerance: float = 1e-9) -> None:
    if abs(actual - expected) > tolerance * max(1.0, abs(actual), abs(expected)):
        raise ValidationError(f"{name} differs from raw evidence")


def _derive_measurement(measurement: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    exact = {
        "schema_version": 1,
        "run_id": spec["run_id"],
        "scout_id": spec["scout_id"],
        "fidelity": spec["fidelity"],
        "control_id": spec["control_id"],
        "candidate_id": spec["candidate_id"],
        "changed_variable": spec["changed_variable"],
        "scope": spec["claim_scope"],
        "primary_metric": spec["prediction"]["metric"],
        "predicted_effect_fraction": spec["prediction"]["point_estimate_fraction"],
        "effect_formula": spec["measurement_contract"]["effect_formula"],
        "protocol": spec["measurement_contract"]["protocol"],
    }
    changed = sorted(name for name, expected in exact.items() if measurement.get(name) != expected)
    if changed:
        raise ValidationError("measurement summary differs from the run spec: " + ", ".join(changed))
    brackets = measurement.get("brackets")
    minimum = spec["measurement_contract"]["minimum_candidate_repetitions"]
    if not isinstance(brackets, list) or len(brackets) < minimum:
        raise ValidationError("measurement summary has too few candidate repetitions")
    effects = []
    for index, bracket in enumerate(brackets):
        if not isinstance(bracket, dict):
            raise ValidationError(f"measurement bracket {index} must be an object")
        before = require_number(f"measurement.brackets[{index}].control_before", bracket.get("control_before"))
        candidate = require_number(f"measurement.brackets[{index}].candidate", bracket.get("candidate"))
        after = require_number(f"measurement.brackets[{index}].control_after", bracket.get("control_after"))
        control = (before + after) / 2.0
        if control == 0 or candidate == 0:
            raise ValidationError("measurement effect denominator cannot be zero")
        if spec["measurement_contract"]["effect_formula"] == "candidate_over_control_minus_one":
            effects.append(candidate / control - 1.0)
        else:
            effects.append(control / candidate - 1.0)
    observed = statistics.median(effects)
    _close(
        "measurement observed_effect_fraction",
        require_number("measurement.observed_effect_fraction", measurement.get("observed_effect_fraction")),
        observed,
    )
    return {"observed_effect_fraction": observed, "effects": effects}


def _validate_identities(identities: dict[str, Any], spec: dict[str, Any]) -> None:
    candidate = {**spec["identities"], **spec["candidate_identity_overrides"]}
    expected = {
        "schema_version": 1,
        "run_id": spec["run_id"],
        "baseline_sha256": spec["baseline_sha256"],
        "control": spec["identities"],
        "candidate": candidate,
        "changed_identity_fields": spec["changed_identity_fields"],
    }
    for name, value in expected.items():
        if identities.get(name) != value:
            raise ValidationError(f"identity evidence differs from the run spec: {name}")


def _validate_quality(quality: dict[str, Any], spec: dict[str, Any]) -> dict[str, bool]:
    if quality.get("schema_version") != 1 or quality.get("run_id") != spec["run_id"]:
        raise ValidationError("quality evidence belongs to another run")
    expected_policies = {
        name: spec["gates"][name]["policy_sha256"] for name in ("correctness", "quality", "slo")
    }
    if quality.get("policy_sha256s") != expected_policies:
        raise ValidationError("quality evidence is bound to different policies")
    gates = quality.get("gates")
    if not isinstance(gates, dict) or any(gates.get(name) is not True for name in expected_policies):
        raise ValidationError("quality evidence does not pass every preregistered gate")
    return {name: True for name in expected_policies}


def _validate_cost(cost: dict[str, Any], spec: dict[str, Any]) -> float:
    if cost.get("schema_version") != 1 or cost.get("run_id") != spec["run_id"]:
        raise ValidationError("cost evidence belongs to another run")
    if cost.get("currency") != "USD":
        raise ValidationError("cost evidence currency must be USD")
    line_items = cost.get("line_items")
    if not isinstance(line_items, list) or not line_items:
        raise ValidationError("cost evidence requires line items")
    total = 0.0
    for index, item in enumerate(line_items):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValidationError(f"cost line item {index} is malformed")
        quantity = require_number(f"cost.line_items[{index}].quantity", item.get("quantity"), nonnegative=True)
        rate = require_number(f"cost.line_items[{index}].unit_rate_usd", item.get("unit_rate_usd"), nonnegative=True)
        recorded = require_number(f"cost.line_items[{index}].cost_usd", item.get("cost_usd"), nonnegative=True)
        derived = quantity * rate
        _close(f"cost line item {index}", recorded, derived, tolerance=1e-8)
        total += recorded
    _close(
        "cost result_cost_usd",
        require_number("cost.result_cost_usd", cost.get("result_cost_usd"), nonnegative=True),
        total,
        tolerance=1e-8,
    )
    if total > float(spec["budget"]["max_spend_usd"]):
        raise ValidationError("cost evidence exceeds the admitted spend cap")
    return total


def _derive_telemetry(
    store: Any,
    roles: dict[str, dict[str, Any]],
    spec: dict[str, Any],
    stored_summary: dict[str, Any],
) -> dict[str, Any]:
    contract = spec["telemetry_contract"]
    report = validate_telemetry_contract(contract)
    rows_by_signal: dict[str, list[dict[str, Any]]] = {}
    for entry in roles.values():
        if not entry.get("telemetry_categories"):
            continue
        for row in _telemetry_rows(store, entry):
            signal = row.get("signal")
            if isinstance(signal, str):
                rows_by_signal.setdefault(signal, []).append(row)
    captured = []
    missing = []
    for signal in contract["signals"]:
        if signal["status"] != "capture":
            continue
        rows = rows_by_signal.get(signal["name"], [])
        valid_rows = [
            row
            for row in rows
            if row.get("run_id") == spec["run_id"]
            and all(field in row for field in signal["fields"])
        ]
        if valid_rows:
            captured.append(signal["name"])
        else:
            missing.append(signal["name"])

    request_rows = rows_by_signal.get("request_timeline", [])
    scheduler_rows = rows_by_signal.get("scheduler_timeline", [])
    request_ids = {row.get("request_id") for row in request_rows if row.get("request_id") is not None}
    scheduler_ids = {row.get("request_id") for row in scheduler_rows if row.get("request_id") is not None}
    correlation_status = "pass" if request_ids and request_ids <= scheduler_ids else "failed"
    if contract["critical_path_method"] == "not_applicable":
        attribution_coverage: float | str = "not_applicable"
    else:
        attribution_coverage = len(request_ids & scheduler_ids) / len(request_ids) if request_ids else 0.0

    observer_contract = contract["observer_effect"]
    if observer_contract["required"]:
        observer = stored_summary.get("observer_effect", {})
        measured = {
            name: require_number(f"telemetry observer {name}", observer.get(name))
            for name in (
                "throughput_change_fraction",
                "median_latency_change_fraction",
                "tail_latency_change_fraction",
            )
        }
        thresholds = {
            "throughput_change_fraction": observer_contract["max_throughput_change_fraction"],
            "median_latency_change_fraction": observer_contract["max_median_latency_change_fraction"],
            "tail_latency_change_fraction": observer_contract["max_tail_latency_change_fraction"],
        }
        observer_status = (
            "failed"
            if any(abs(measured[name]) > thresholds[name] for name in measured)
            else "pass"
        )
    else:
        measured = {
            "throughput_change_fraction": "not_applicable",
            "median_latency_change_fraction": "not_applicable",
            "tail_latency_change_fraction": "not_applicable",
        }
        observer_status = "not_applicable"
    derived = {
        "schema_version": 1,
        "contract_sha256": report["contract_sha256"],
        "captured_signals": sorted(captured),
        "missing_signals": sorted(missing),
        "unavailable_signals": report["unavailable_signal_names"],
        "correlation_status": correlation_status,
        "attribution_coverage": attribution_coverage,
        "observer_effect": {"status": observer_status, **measured},
    }
    validate_telemetry_summary(derived, contract)
    if validate_telemetry_summary(stored_summary, contract) != derived:
        raise ValidationError("stored telemetry summary differs from raw telemetry")
    return derived


def validate_run_evidence(store: Any, manifest: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    roles = _role_entries(manifest)
    stored_spec = _json_object(store, roles["run_spec"], "run_spec")
    if stored_spec != spec or content_hash(stored_spec) != content_hash(spec):
        raise ValidationError("stored run specification differs from the admitted specification")
    identities = _json_object(store, roles["identities"], "identities")
    _validate_identities(identities, spec)
    measurement = _derive_measurement(
        _json_object(store, roles["measurement_summary"], "measurement_summary"), spec
    )
    gates = _validate_quality(_json_object(store, roles["quality"], "quality"), spec)
    cost = _validate_cost(_json_object(store, roles["cost"], "cost"), spec)
    telemetry_summary = _derive_telemetry(
        store,
        roles,
        spec,
        _json_object(store, roles["telemetry_summary"], "telemetry_summary"),
    )
    return {
        "observed_effect_fraction": measurement["observed_effect_fraction"],
        "gates": gates,
        "result_cost_usd": cost,
        "telemetry_summary": telemetry_summary,
    }


def validate_failure_evidence(
    store: Any,
    manifest: dict[str, Any],
    spec: dict[str, Any],
    *,
    failure_class: str,
) -> dict[str, Any]:
    roles = _role_entries(manifest)
    expected_roles = {"run_spec", "identities", "telemetry_summary", "cost", "logs", "failure_summary"}
    if set(roles) != expected_roles:
        raise ValidationError("failure evidence bundle has the wrong roles")
    stored_spec = _json_object(store, roles["run_spec"], "run_spec")
    if stored_spec != spec:
        raise ValidationError("stored failure run specification differs from the admitted specification")
    _validate_identities(_json_object(store, roles["identities"], "identities"), spec)
    failure = _json_object(store, roles["failure_summary"], "failure_summary")
    if failure.get("schema_version") != 1 or failure.get("run_id") != spec["run_id"]:
        raise ValidationError("failure summary belongs to another run")
    if failure.get("failure_class") != failure_class:
        raise ValidationError("failure summary class differs from the result")
    require_text("failure_summary.stage", failure.get("stage"))
    require_text("failure_summary.message", failure.get("message"))
    telemetry = _json_object(store, roles["telemetry_summary"], "telemetry_summary")
    if telemetry.get("schema_version") != 1 or telemetry.get("run_id") != spec["run_id"]:
        raise ValidationError("failure telemetry belongs to another run")
    planned = {
        signal["name"] for signal in spec["telemetry_contract"]["signals"] if signal["status"] == "capture"
    }
    captured = telemetry.get("captured_signals")
    missing = telemetry.get("missing_signals")
    if not isinstance(captured, list) or not isinstance(missing, list):
        raise ValidationError("failure telemetry must list captured_signals and missing_signals")
    if set(captured) & set(missing) or set(captured) | set(missing) != planned:
        raise ValidationError("failure telemetry must account for every planned signal exactly once")
    require_text("failure telemetry failure_stage", telemetry.get("failure_stage"))
    cost = _validate_cost(_json_object(store, roles["cost"], "cost"), spec)
    store.verify_reference(roles["logs"]["sha256"], deep=True)
    return {"result_cost_usd": cost, "telemetry_summary": telemetry, "failure": failure}
