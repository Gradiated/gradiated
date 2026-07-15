from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from grad_research.admission import (
    IDENTITY_FIELDS,
    PREFLIGHT_BINDINGS,
    PREFLIGHT_CHECKS,
    validate_paid_run,
)
from grad_research.artifacts import ArtifactStore
from grad_research.director import ResearchDirector
from grad_research.telemetry import build_telemetry_contract
from grad_research.util import (
    ValidationError,
    content_hash,
    parse_utc,
    require_sha256,
)

from launcher_retention import launcher_record
from observer_dependency_contract import binding as dependency_contract_binding


HERE = Path(__file__).resolve().parent
NSYS_LAUNCH_FIXTURE = HERE / "fixtures" / "nsys-launch-help-2026.3.1.157.txt"


COMBINED_HOURLY_RATE_USD = 0.8581222
SCIENCE_AND_WATCHDOG_TIMEOUT_SECONDS = 2000
CLEANUP_RESERVE_USD = 0.07
MAX_SPEND_USD = 0.55
PRIMARY_SCOUT_ID = "glm47-dense-resource-signature"
SECONDARY_PACKET = "glm47-host-scheduler-critical-path"
SETUP_KEY = "l40s:vllm:glm47:observer"
EXPECTED_GEOMETRY = {
    "arm_sequence": ["A1_observer_off", "B1_observer_on", "A2_observer_off"],
    "prompt_tokens_per_request": 8192,
    "output_tokens_per_request": 32,
    "concurrency": 8,
    "requests": 8,
    "synchronized_barrier": True,
    "temperature": 0,
    "ignore_eos": True,
    "prefix_cache": False,
}
EXPECTED_OPERATIONAL_STARTUP_ISOLATION = {
    "stage_id": "STOCK_STARTUP",
    "patch_state": "unpatched",
    "server_configuration": "exact_same_command_checkpoint_and_runtime_as_A1",
    "readiness_attempts": 180,
    "readiness_interval_seconds": 2,
    "requests": 0,
    "excluded_from_measurement": True,
    "success_gate": "healthy_then_stopped_and_process_absent_before_patch",
    "term_timeout_seconds": 30,
    "kill_fallback": True,
    "failure_classification": "operational_only_no_scientific_update",
}


def _load_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{name} is not readable JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must be a JSON object")
    return value


def _require_schema_one(value: dict[str, Any], name: str) -> None:
    if value.get("schema_version") != 1:
        raise ValidationError(f"{name}.schema_version must be 1")


def _validate_preregistration(preregistration: dict[str, Any], state: dict[str, Any]) -> tuple[dict, dict]:
    _require_schema_one(preregistration, "preregistration")
    program_id = preregistration.get("program_id")
    if program_id != state.get("program_id"):
        raise ValidationError("preregistration program_id differs from factory state")
    if preregistration.get("setup_key") != SETUP_KEY:
        raise ValidationError("preregistration setup_key differs from the selected factory setup")
    recording = preregistration.get("factory_recording_plan")
    if not isinstance(recording, dict):
        raise ValidationError("preregistration.factory_recording_plan must be an object")
    if recording.get("primary_paid_scout_id") != PRIMARY_SCOUT_ID:
        raise ValidationError("observer run must be assigned to the dense-resource scout")
    if recording.get("secondary_packet") != SECONDARY_PACKET:
        raise ValidationError("host/scheduler packet must share the diagnostic evidence bundle")
    scouts = state.get("scouts")
    if not isinstance(scouts, dict) or PRIMARY_SCOUT_ID not in scouts:
        raise ValidationError("factory state does not contain the selected dense-resource scout")
    if scouts[PRIMARY_SCOUT_ID].get("setup_key") != SETUP_KEY:
        raise ValidationError("factory scout setup_key differs from the observer allocation")
    geometry = preregistration.get("workload_geometry")
    if not isinstance(geometry, dict) or any(geometry.get(name) != value for name, value in EXPECTED_GEOMETRY.items()):
        raise ValidationError("preregistration workload_geometry differs from exact A1/B1/A2 8x8192/32 geometry")
    quality_gate = preregistration.get("quality_gate")
    if not isinstance(quality_gate, dict) or quality_gate.get("diagnostic_only") is not True:
        raise ValidationError("observer run must remain diagnostic_only")
    if preregistration.get("operational_startup_isolation") != EXPECTED_OPERATIONAL_STARTUP_ISOLATION:
        raise ValidationError(
            "preregistration operational_startup_isolation must bind the exact excluded "
            "unpatched startup, bounded stop, and process-absence gate"
        )
    stock = preregistration.get("stock_control")
    if not isinstance(stock, dict) or str(stock.get("provider", "")).lower() != "nebius":
        raise ValidationError("observer stock control must use Nebius")
    hypotheses = preregistration.get("causal_hypotheses")
    if not isinstance(hypotheses, list):
        raise ValidationError("preregistration.causal_hypotheses must be a list")
    dense = next(
        (
            row
            for row in hypotheses
            if isinstance(row, dict) and row.get("id") == "dense_dependency_resource_signature"
        ),
        None,
    )
    if dense is None or not isinstance(dense.get("falsifier"), str) or not dense["falsifier"].strip():
        raise ValidationError("dense dependency hypothesis requires a falsifier")
    baseline = state.get("baseline")
    if not isinstance(baseline, dict):
        raise ValidationError("factory state has no frozen baseline")
    return baseline, dense


def _validate_identities(value: dict[str, Any], baseline: dict[str, Any]) -> tuple[dict, dict]:
    _require_schema_one(value, "identities")
    control = value.get("control")
    overrides = value.get("candidate_overrides")
    if not isinstance(control, dict) or set(control) != IDENTITY_FIELDS:
        raise ValidationError("identities.control must contain exactly the paid-run identity fields")
    expected_override_fields = {"harness_sha256", "configuration_sha256"}
    if not isinstance(overrides, dict) or set(overrides) != expected_override_fields:
        raise ValidationError("candidate_overrides may change only observer harness and configuration identities")
    for name, field_value in control.items():
        if name.endswith("_sha256"):
            require_sha256(f"identities.control.{name}", field_value)
        elif not isinstance(field_value, str) or not field_value.strip():
            raise ValidationError(f"identities.control.{name} must be nonempty text")
    for name, field_value in overrides.items():
        require_sha256(f"identities.candidate_overrides.{name}", field_value)
        if field_value == control[name]:
            raise ValidationError(f"candidate observer identity does not change {name}")
    baseline_bindings = {
        "model_revision": "model_revision",
        "checkpoint_manifest_sha256": "checkpoint_manifest_sha256",
        "tokenizer_manifest_sha256": "tokenizer_manifest_sha256",
        "runtime_manifest_sha256": "runtime_manifest_sha256",
        "workload_manifest_sha256": "workload_manifest_sha256",
    }
    mismatched = sorted(
        identity_field
        for identity_field, baseline_field in baseline_bindings.items()
        if control[identity_field] != baseline.get(baseline_field)
    )
    if mismatched:
        raise ValidationError(
            "control identities differ from frozen factory baseline: " + ", ".join(mismatched)
        )
    return control, overrides


def _load_preflight(
    value: dict[str, Any],
    *,
    store: ArtifactStore,
    candidate_identities: dict[str, Any],
) -> dict[str, Any]:
    _require_schema_one(value, "preflight manifest")
    references = value.get("checks")
    if not isinstance(references, dict) or set(references) != PREFLIGHT_CHECKS:
        raise ValidationError("preflight manifest must reference every paid-run preflight check exactly once")
    checks = {}
    for name in sorted(PREFLIGHT_CHECKS):
        evidence_sha256 = require_sha256(f"preflight manifest.checks.{name}", references[name])
        store.verify_reference(evidence_sha256, deep=True)
        expected = {
            "schema_version": 1,
            "check": name,
            "pass": True,
            "bound_sha256": candidate_identities[PREFLIGHT_BINDINGS[name]],
        }
        if store.load_json_reference(evidence_sha256) != expected:
            raise ValidationError(f"preflight evidence for {name} is not exactly content-bound")
        checks[name] = {
            "pass": True,
            "evidence_sha256": evidence_sha256,
            "bound_sha256": expected["bound_sha256"],
        }
    return checks


def _normalize_artifact_contract(value: dict[str, Any], run_id: str) -> dict[str, Any]:
    _require_schema_one(value, "artifact contract")
    if value.get("run_id") != run_id or value.get("root") != f"runs/{run_id}":
        raise ValidationError("artifact contract is not bound to the observer run")
    if value.get("hash_manifest") is not True:
        raise ValidationError("artifact contract must require a hash manifest")
    required = value.get("required")
    if not isinstance(required, list):
        raise ValidationError("artifact contract.required must be a list")
    normalized = []
    for index, row in enumerate(required):
        if not isinstance(row, dict):
            raise ValidationError(f"artifact contract.required[{index}] must be an object")
        try:
            normalized.append({name: row[name] for name in ("role", "path", "media_type")})
        except KeyError as error:
            raise ValidationError(f"artifact contract.required[{index}] is incomplete") from error
    normalized.sort(key=lambda row: row["role"])
    return {"root": f"runs/{run_id}", "required": normalized, "hash_manifest": True}


def prepare_observer_paid_run(
    *,
    lab_root: str | Path,
    preregistration_path: str | Path,
    artifact_contract_path: str | Path,
    identities_path: str | Path,
    preflight_path: str | Path,
    now: datetime,
) -> dict[str, Any]:
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise ValidationError("generation clock must be UTC")
    preregistration = _load_json(Path(preregistration_path), "preregistration")
    program_id = preregistration.get("program_id")
    if not isinstance(program_id, str) or not program_id:
        raise ValidationError("preregistration.program_id must be nonempty text")
    director = ResearchDirector(lab_root, program_id)
    state = director.state()
    baseline, dense_hypothesis = _validate_preregistration(preregistration, state)
    control, candidate_overrides = _validate_identities(
        _load_json(Path(identities_path), "identities"), baseline
    )
    candidate_identities = {**control, **candidate_overrides}
    preflight = _load_preflight(
        _load_json(Path(preflight_path), "preflight manifest"),
        store=director.artifacts,
        candidate_identities=candidate_identities,
    )
    run_id = preregistration.get("run_id")
    campaign_id = preregistration.get("campaign_id")
    if not isinstance(run_id, str) or not run_id or not isinstance(campaign_id, str) or not campaign_id:
        raise ValidationError("preregistration run_id and campaign_id must be nonempty text")
    artifacts = _normalize_artifact_contract(
        _load_json(Path(artifact_contract_path), "artifact contract"), run_id
    )
    telemetry = build_telemetry_contract("diagnostic_only")
    correctness_policy = content_hash(
        {
            "quality_gate": preregistration["quality_gate"],
            "workload_geometry": {name: preregistration["workload_geometry"][name] for name in EXPECTED_GEOMETRY},
        }
    )
    deadline = now + timedelta(seconds=SCIENCE_AND_WATCHDOG_TIMEOUT_SECONDS)
    # Generate once during immutable preparation. Admission and later recovery
    # must consume these bytes, never reconstruct them from the working tree.
    from observer_diagnostic_control import build_host_bootstrap

    host_bootstrap_launcher = launcher_record(build_host_bootstrap().encode("utf-8"))
    spec = {
        "schema_version": 1,
        "run_id": run_id,
        "program_id": program_id,
        "campaign_id": campaign_id,
        "scout_id": PRIMARY_SCOUT_ID,
        "baseline_id": baseline["id"],
        "baseline_sha256": content_hash(baseline),
        "arm_role": "diagnostic",
        "fidelity": "matched_server",
        "control_id": "glm47-stock-observer-off",
        "candidate_id": "glm47-stock-observer-on",
        "changed_variable": "observer state and its harness/configuration identity only",
        "setup_key": SETUP_KEY,
        "identities": control,
        "candidate_identity_overrides": candidate_overrides,
        "changed_identity_fields": sorted(candidate_overrides),
        "claim_scope": {
            "model": f"GLM-4.7-Flash revision {baseline['model_revision']}",
            "workload": "A1 observer-off / B1 observer-on / A2 observer-off; 8 requests; c8; 8192 input + 32 output tokens",
            "hardware": control["hardware_scope"],
            "claim": "diagnostic localization only; no quality, economics, provider, or candidate-performance claim",
        },
        "gates": {
            "correctness": {"policy_sha256": correctness_policy, "required": True},
            "quality": {"policy_sha256": baseline["quality_policy_sha256"], "required": True},
            "slo": {"policy_sha256": baseline["slo_policy_sha256"], "required": True},
        },
        "prediction": {
            "metric": "dense_decode_dependency_union_fraction",
            "expected_direction": "increase",
            "point_estimate_fraction": 0.20,
            "minimum_effect_fraction": 0.20,
            "plausible_ceiling_fraction": 1.0,
            "falsifier": dense_hypothesis["falsifier"],
        },
        "measurement_contract": {
            "protocol": "bracketed",
            "effect_formula": "candidate_over_control_minus_one",
            "minimum_candidate_repetitions": 1,
            "statistic": "median",
        },
        "budget": {
            "hourly_rate_usd": COMBINED_HOURLY_RATE_USD,
            "timeout_seconds": SCIENCE_AND_WATCHDOG_TIMEOUT_SECONDS,
            "cleanup_reserve_usd": CLEANUP_RESERVE_USD,
            "max_spend_usd": MAX_SPEND_USD,
        },
        "watchdog": {
            "independent": True,
            "absolute_deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "delete_on_deadline": True,
            "verify_absent": True,
        },
        "provider_contract": {
            "provider": "nebius",
            "idempotency_key": run_id,
            "resource_tags": {
                "program_id": program_id,
                "campaign_id": campaign_id,
                "run_id": run_id,
            },
            "inventory_reconcile": True,
            "operational_startup_isolation": EXPECTED_OPERATIONAL_STARTUP_ISOLATION,
            "nsys_launch_capability": {
                "package_version": "2026.3.1.157",
                "command": "nsys launch --help",
                "before_model_transfer": True,
                "fixture_sha256": hashlib.sha256(NSYS_LAUNCH_FIXTURE.read_bytes()).hexdigest(),
                "required_flags": [
                    "--session-new", "--trace", "--cuda-graph-trace", "--cuda-event-trace",
                    "--sample", "--cpuctxsw",
                ],
                "forbidden_flags": ["--force-overwrite"],
            },
        },
        "operational_startup_isolation": EXPECTED_OPERATIONAL_STARTUP_ISOLATION,
        "preflight": preflight,
        "host_bootstrap_launcher": host_bootstrap_launcher,
        "telemetry_contract": telemetry,
        "artifact_contract": artifacts,
        "cleanup": {
            "delete_compute": True,
            "delete_attached_storage": True,
            "verify_get_not_found": True,
            "verify_inventory_absent": True,
        },
        "post_run_recording": {
            "primary": {"scout_id": PRIMARY_SCOUT_ID, "record_type": "paid_result"},
            "secondary": {
                "packet": SECONDARY_PACKET,
                "record_type": "typed_observation",
                "disposition": "typed_observation_same_evidence_bundle",
                "additional_paid_run": False,
                "additional_reservation": False,
            },
        },
        "observer_dependency_attribution_contract": dependency_contract_binding(),
    }
    validate_paid_run(spec, now=now)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the factory-admissible GLM observer paid run")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--artifact-contract", required=True, type=Path)
    parser.add_argument("--identities", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--now", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    now = parse_utc(arguments.now, "--now")
    spec = prepare_observer_paid_run(
        lab_root=arguments.root,
        preregistration_path=arguments.preregistration,
        artifact_contract_path=arguments.artifact_contract,
        identities_path=arguments.identities,
        preflight_path=arguments.preflight,
        now=now,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(arguments.output.suffix + ".tmp")
    temporary.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, arguments.output)
    print(json.dumps({"output": str(arguments.output), "run_id": spec["run_id"], "sha256": content_hash(spec)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
