from __future__ import annotations

from datetime import datetime, timedelta, timezone

from grad_research.telemetry import build_telemetry_contract
from grad_research.util import content_hash


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def baseline_record() -> dict:
    return {
        "schema_version": 1,
        "id": "glm47-stock",
        "model_revision": "glm-4.7-flash-complete",
        "checkpoint_manifest_sha256": HASH_A,
        "tokenizer_manifest_sha256": HASH_A,
        "runtime_manifest_sha256": HASH_A,
        "workload_manifest_sha256": HASH_A,
        "quality_policy_sha256": HASH_A,
        "slo_policy_sha256": HASH_A,
        "cost_denominator": "quality_and_slo_eligible_output_tokens",
    }


def scout(
    scout_id: str,
    *,
    slot: str,
    family: str,
    origin: str,
    novelty_key: str | None = None,
    cost: float = 0.1,
    impact: float = 0.8,
    uncertainty: float = 0.8,
    discrimination: float = 0.9,
    readiness: float = 0.9,
    setup_key: str = "l40s:vllm:glm47",
    cycle: int = 1,
) -> dict:
    return {
        "schema_version": 1,
        "id": scout_id,
        "cycle": cycle,
        "observation_ids": [f"obs-{cycle}"],
        "slot": slot,
        "family": family,
        "origin": origin,
        "mechanism": f"mechanism for {scout_id}",
        "change": f"change for {scout_id}",
        "competing_explanations": ["explanation-a", "explanation-b"],
        "falsifier": f"falsify {scout_id}",
        "next_fidelity": "simulation",
        "plausible_end_to_end_ceiling_fraction": 0.12,
        "estimated_cost_usd": cost,
        "estimated_minutes": 10,
        "decision_impact": impact,
        "uncertainty": uncertainty,
        "discrimination_power": discrimination,
        "readiness": readiness,
        "transfer_penalty": 0.1,
        "setup_key": setup_key,
        "novelty_key": novelty_key or scout_id,
        "quality_risks": ["numerical parity"],
    }


def paid_run_spec(*, deadline_offset_seconds: int = 300) -> tuple[dict, datetime]:
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    deadline = now + timedelta(seconds=deadline_offset_seconds)
    binding = {
        "provider_fixture": HASH_B,
        "checkpoint_closure": HASH_A,
        "tokenizer_identity": HASH_A,
        "runtime_probe": HASH_A,
        "configuration_identity": HASH_B,
        "protocol_fixture": HASH_B,
        "parser_fixture": HASH_B,
        "artifact_paths": HASH_B,
        "local_tests": HASH_B,
    }
    checks = {
        name: {"pass": True, "evidence_sha256": HASH_A, "bound_sha256": binding[name]}
        for name in (
            "provider_fixture",
            "checkpoint_closure",
            "tokenizer_identity",
            "runtime_probe",
            "configuration_identity",
            "protocol_fixture",
            "parser_fixture",
            "artifact_paths",
            "local_tests",
        )
    }
    telemetry_contract = build_telemetry_contract("scoreable")
    return {
        "schema_version": 1,
        "run_id": "run-1",
        "program_id": "glm47",
        "campaign_id": "glm47-cost",
        "scout_id": "attention-1",
        "baseline_id": "glm47-stock",
        "baseline_sha256": content_hash(baseline_record()),
        "arm_role": "candidate",
        "fidelity": "matched_server",
        "control_id": "stock-vllm",
        "candidate_id": "split8-vllm",
        "changed_variable": "num_kv_splits: 4 -> 8",
        "changed_identity_fields": ["configuration_sha256"],
        "setup_key": "l40s:vllm:glm47",
        "identities": {
            "model_revision": "glm-4.7-flash-complete",
            "checkpoint_manifest_sha256": HASH_A,
            "tokenizer_manifest_sha256": HASH_A,
            "runtime_manifest_sha256": HASH_A,
            "workload_manifest_sha256": HASH_A,
            "harness_sha256": HASH_B,
            "configuration_sha256": HASH_A,
            "hardware_scope": "Nebius L40S 48GB",
        },
        "candidate_identity_overrides": {"configuration_sha256": HASH_B},
        "claim_scope": {
            "model": "glm-4.7-flash",
            "workload": "fixed-8k-c8",
            "hardware": "l40s",
        },
        "gates": {
            "correctness": {"policy_sha256": HASH_A, "required": True},
            "quality": {"policy_sha256": HASH_A, "required": True},
            "slo": {"policy_sha256": HASH_A, "required": True},
        },
        "prediction": {
            "metric": "c8_output_tokens_per_second",
            "expected_direction": "increase",
            "point_estimate_fraction": 0.12,
            "minimum_effect_fraction": 0.05,
            "plausible_ceiling_fraction": 0.12,
            "falsifier": "bracketed effect below 0.05",
        },
        "measurement_contract": {
            "protocol": "bracketed",
            "effect_formula": "candidate_over_control_minus_one",
            "minimum_candidate_repetitions": 2,
            "statistic": "median",
        },
        "budget": {
            "hourly_rate_usd": 0.86,
            "timeout_seconds": deadline_offset_seconds,
            "cleanup_reserve_usd": 0.10,
            "max_spend_usd": 0.20,
        },
        "watchdog": {
            "independent": True,
            "absolute_deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "delete_on_deadline": True,
            "verify_absent": True,
        },
        "provider_contract": {
            "provider": "fake",
            "idempotency_key": "glm47-run-1",
            "resource_tags": {
                "program_id": "glm47",
                "campaign_id": "glm47-cost",
                "run_id": "run-1",
            },
            "inventory_reconcile": True,
        },
        "preflight": checks,
        "telemetry_contract": telemetry_contract,
        "artifact_contract": {
            "root": "runs/run-1",
            "required": [
                {"role": "identities", "path": "identities.json", "media_type": "application/json"},
                {"role": "measurement_summary", "path": "measurement.json", "media_type": "application/json"},
                {"role": "telemetry_summary", "path": "telemetry.json", "media_type": "application/json"},
                {"role": "quality", "path": "quality.json", "media_type": "application/json"},
                {"role": "cost", "path": "cost.json", "media_type": "application/json"},
                {"role": "logs", "path": "run.log", "media_type": "text/plain"},
                {"role": "events", "path": "events.jsonl", "media_type": "application/x-ndjson"},
                {"role": "system_samples", "path": "system.jsonl", "media_type": "application/x-ndjson"},
            ],
            "hash_manifest": True,
        },
        "cleanup": {
            "delete_compute": True,
            "delete_attached_storage": True,
            "verify_get_not_found": True,
            "verify_inventory_absent": True,
        },
    }, now
