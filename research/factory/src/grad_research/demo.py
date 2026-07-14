from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .artifacts import package_run_directory
from .director import ResearchDirector
from .labd import LabDatabase
from .telemetry import build_complete_telemetry_summary, build_telemetry_contract
from .util import content_hash


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _baseline() -> dict:
    return {
        "schema_version": 1,
        "id": "glm47-demo-stock",
        "model_revision": "glm-4.7-flash-complete",
        "checkpoint_manifest_sha256": HASH_A,
        "tokenizer_manifest_sha256": HASH_B,
        "runtime_manifest_sha256": HASH_C,
        "workload_manifest_sha256": HASH_A,
        "quality_policy_sha256": HASH_B,
        "slo_policy_sha256": HASH_C,
        "cost_denominator": "quality_and_slo_eligible_output_tokens",
    }


def _observation(cycle: int, summary: str, metric: str, artifact_ref: str) -> dict:
    return {
        "schema_version": 1,
        "id": f"obs-{cycle}",
        "cycle": cycle,
        "evidence_class": "synthetic",
        "summary": summary,
        "scope": {
            "model": "glm-4.7-flash",
            "revision": "complete",
            "workload": "fixed-8k-c8",
            "phase": "decode",
            "concurrency": "8",
            "software": "vllm",
            "hardware": "l40s",
        },
        "metrics": [{
            "name": metric,
            "value": 0.35,
            "unit": "fraction",
            "time_semantics": "proxy",
            "coverage": 1.0,
        }],
        "instrumentation_gaps": [],
        "artifact_refs": [artifact_ref],
    }


def _scout(identifier: str, cycle: int, slot: str, family: str, origin: str) -> dict:
    return {
        "schema_version": 1,
        "id": identifier,
        "cycle": cycle,
        "observation_ids": [f"obs-{cycle}"],
        "slot": slot,
        "family": family,
        "origin": origin,
        "mechanism": f"{family} mechanism",
        "change": f"change {identifier}",
        "competing_explanations": ["device work", "host or dependency overlap"],
        "falsifier": "matched bracket below the materiality gate",
        "next_fidelity": "matched_server" if cycle == 1 else "simulation",
        "plausible_end_to_end_ceiling_fraction": 0.12,
        "estimated_cost_usd": 0.05,
        "estimated_minutes": 10,
        "decision_impact": 0.8,
        "uncertainty": 0.9,
        "discrimination_power": 0.9,
        "readiness": 0.9,
        "transfer_penalty": 0.1,
        "setup_key": "l40s:vllm:glm47",
        "novelty_key": identifier,
        "quality_risks": ["numerical parity"],
    }


def _paid_spec(now: datetime) -> dict:
    deadline = now + timedelta(seconds=300)
    telemetry_contract = build_telemetry_contract("scoreable")
    return {
        "schema_version": 1,
        "run_id": "demo-server-transfer",
        "program_id": "glm47-demo",
        "campaign_id": "demo-campaign",
        "scout_id": "attention-local",
        "baseline_id": "glm47-demo-stock",
        "baseline_sha256": content_hash(_baseline()),
        "arm_role": "candidate",
        "fidelity": "matched_server",
        "control_id": "stock",
        "candidate_id": "attention-candidate",
        "changed_variable": "attention partition",
        "changed_identity_fields": ["configuration_sha256"],
        "setup_key": "l40s:vllm:glm47",
        "identities": {
            "model_revision": "glm-4.7-flash-complete",
            "checkpoint_manifest_sha256": HASH_A,
            "tokenizer_manifest_sha256": HASH_B,
            "runtime_manifest_sha256": HASH_C,
            "workload_manifest_sha256": HASH_A,
            "harness_sha256": HASH_B,
            "configuration_sha256": HASH_A,
            "hardware_scope": "synthetic L40S",
        },
        "candidate_identity_overrides": {"configuration_sha256": HASH_B},
        "claim_scope": {
            "model": "glm-4.7-flash",
            "workload": "fixed-8k-c8",
            "hardware": "synthetic-l40s",
        },
        "gates": {
            "correctness": {"policy_sha256": HASH_A, "required": True},
            "quality": {"policy_sha256": HASH_B, "required": True},
            "slo": {"policy_sha256": HASH_C, "required": True},
        },
        "prediction": {
            "metric": "output_tokens_per_second",
            "expected_direction": "increase",
            "point_estimate_fraction": 0.4,
            "minimum_effect_fraction": 0.05,
            "plausible_ceiling_fraction": 0.4,
            "falsifier": "bracketed effect below five percent",
        },
        "measurement_contract": {
            "protocol": "bracketed",
            "effect_formula": "candidate_over_control_minus_one",
            "minimum_candidate_repetitions": 2,
            "statistic": "median",
        },
        "budget": {
            "hourly_rate_usd": 0.86,
            "timeout_seconds": 300,
            "cleanup_reserve_usd": 0.1,
            "max_spend_usd": 0.2,
        },
        "watchdog": {
            "independent": True,
            "absolute_deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "delete_on_deadline": True,
            "verify_absent": True,
        },
        "provider_contract": {
            "provider": "fake",
            "idempotency_key": "demo-server-transfer",
            "resource_tags": {
                "program_id": "glm47-demo",
                "campaign_id": "demo-campaign",
                "run_id": "demo-server-transfer",
            },
            "inventory_reconcile": True,
        },
        "preflight": {
            name: {
                "pass": True,
                "evidence_sha256": HASH_A,
                "bound_sha256": {
                    "provider_fixture": HASH_B,
                    "checkpoint_closure": HASH_A,
                    "tokenizer_identity": HASH_B,
                    "runtime_probe": HASH_C,
                    "configuration_identity": HASH_B,
                    "protocol_fixture": HASH_B,
                    "parser_fixture": HASH_B,
                    "artifact_paths": HASH_B,
                    "local_tests": HASH_B,
                }[name],
            }
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
        },
        "telemetry_contract": telemetry_contract,
        "artifact_contract": {
            "root": "runs/demo-server-transfer",
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
    }


def _result(
    run_id: str,
    scout_id: str,
    outcome: str,
    *,
    artifact_refs: list[str],
    effect: float | None = None,
    residual: str | None = None,
    cost: float = 0.0,
    artifact_bundle_sha256: str | None = None,
    telemetry_summary: dict | None = None,
    spec: dict,
) -> dict:
    value = {
        "schema_version": 1,
        "id": f"result-{run_id}",
        "run_id": run_id,
        "scout_id": scout_id,
        "control_id": spec["control_id"],
        "candidate_id": spec["candidate_id"],
        "changed_variable": spec["changed_variable"],
        "baseline_sha256": spec["baseline_sha256"],
        "prediction_sha256": content_hash(spec["prediction"]),
        "outcome_class": outcome,
        "fidelity": spec["fidelity"],
        "scope": spec["claim_scope"],
        "cost_usd": cost,
        "artifact_refs": artifact_refs,
        "next_action": "attack the measured residual",
    }
    if artifact_bundle_sha256 is not None:
        value["artifact_bundle_sha256"] = artifact_bundle_sha256
    if telemetry_summary is not None:
        value["telemetry_summary"] = telemetry_summary
    if outcome.startswith("scientific_"):
        value.update({
            "gates": {"correctness": True, "quality": True, "slo": True},
            "primary_metric": spec["prediction"]["metric"],
            "observed_effect_fraction": effect,
            "predicted_effect_fraction": spec["prediction"]["point_estimate_fraction"],
            "residual_bottleneck": residual,
        })
    else:
        value["failure_class"] = "recorded tokenizer fixture mismatch"
    return value


def _local_spec(
    run_id: str,
    scout_id: str,
    *,
    fidelity: str,
    point_estimate_fraction: float,
    artifact_refs: list[str],
) -> dict:
    return {
        "schema_version": 1,
        "execution_kind": "local",
        "run_id": run_id,
        "program_id": "glm47-demo",
        "scout_id": scout_id,
        "fidelity": fidelity,
        "baseline_id": "glm47-demo-stock",
        "baseline_sha256": content_hash(_baseline()),
        "control_id": "local-control",
        "candidate_id": f"local-candidate-{run_id}",
        "changed_variable": f"local change for {run_id}",
        "claim_scope": {
            "model": "glm-4.7-flash",
            "workload": "fixed-8k-c8",
            "hardware": "synthetic-l40s",
        },
        "prediction": {
            "metric": "output_tokens_per_second",
            "expected_direction": "increase",
            "point_estimate_fraction": point_estimate_fraction,
            "minimum_effect_fraction": 0.05,
            "plausible_ceiling_fraction": max(0.1, point_estimate_fraction),
            "falsifier": "measured effect is below the materiality gate",
        },
        "measurement_contract": {
            "protocol": "deterministic",
            "effect_formula": "candidate_over_control_minus_one",
            "minimum_candidate_repetitions": 1,
            "statistic": "median",
        },
        "gates": {
            "correctness": {"policy_sha256": HASH_A, "required": True},
            "quality": {"policy_sha256": HASH_B, "required": True},
            "slo": {"policy_sha256": HASH_C, "required": True},
        },
        "command": f"synthetic-local-run {run_id}",
        "seed": 1,
        "timeout_seconds": 60,
        "max_cost_usd": 0.0,
        "artifact_refs": artifact_refs,
    }


def run_demo(root: Path) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    director = ResearchDirector(root, "glm47-demo")
    director.freeze_baseline(_baseline())
    observation_one_ref = director.artifacts.put_json(
        {"cycle": 1, "source": "synthetic trace", "attention_proxy_fraction": 0.35}
    )
    director.record_observation(
        _observation(1, "attention proxy appears dominant", "attention_proxy_fraction", observation_one_ref)
    )
    director.propose_scouts([
        _scout("attention-local", 1, "bottleneck_adjacent", "attention", "trace_local"),
        _scout("attention-inversion", 1, "bottleneck_adjacent", "attention", "first_principles"),
        _scout("runtime-cross", 1, "cross_stack", "runtime", "literature_recombination"),
        _scout("model-layout", 1, "model_architecture", "representation", "cross_model_analogy"),
        _scout("measurement-skeptic", 1, "adversarial", "measurement", "adversarial"),
    ])
    director.select_portfolio(1)

    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    lab = LabDatabase(root / "labd.sqlite3")
    lease = lab.acquire_coordinator("glm47-demo", "codex-demo", ttl_seconds=900, now=now.timestamp())
    lab.ensure_budget("demo-campaign", authorized_usd=1.0)
    paid_spec = _paid_spec(now)
    for name, check in paid_spec["preflight"].items():
        check["evidence_sha256"] = director.artifacts.put_json(
            {
                "schema_version": 1,
                "check": name,
                "pass": True,
                "bound_sha256": check["bound_sha256"],
            }
        )
    admission = director.admit_paid_run(paid_spec, lab=lab, owner="codex-demo", epoch=lease["epoch"], now=now)
    lab.register_allocation(
        allocation_id="demo-allocation",
        reservation_id=admission["reservation_id"],
        provider="fake",
        provider_resource_id="fake-gpu-1",
        setup_key="l40s:vllm:glm47",
        owner="codex-demo",
        epoch=lease["epoch"],
        absolute_deadline=(now + timedelta(seconds=290)).timestamp(),
        now=now.timestamp() + 1,
    )
    lab.mark_retained(
        "demo-allocation",
        owner="codex-demo",
        epoch=lease["epoch"],
        resident_manifest_sha256=HASH_A,
        now=now.timestamp() + 2,
    )
    invalid_ref = director.artifacts.put_json(
        {"run_id": "observer-invalid", "failure": "recorded tokenizer fixture mismatch"}
    )
    invalid_input_ref = director.artifacts.put_json({"fixture": "observer-invalid-preregistration"})
    invalid_spec = _local_spec(
        "observer-invalid",
        "attention-local",
        fidelity="reduced_replay",
        point_estimate_fraction=0.0,
        artifact_refs=[invalid_input_ref],
    )
    director.register_local_run(invalid_spec)
    director.complete_run(
        _result(
            "observer-invalid",
            "attention-local",
            "harness_invalid",
            artifact_refs=[invalid_ref],
            spec=invalid_spec,
        )
    )

    run_directory = root / "demo-server-transfer-output"
    run_directory.mkdir(parents=True, exist_ok=True)
    spec_path = root / "demo-server-transfer-spec.json"
    spec_path.write_text(json.dumps(paid_spec, indent=2, sort_keys=True) + "\n")
    telemetry_summary = build_complete_telemetry_summary(
        paid_spec["telemetry_contract"], attribution_coverage="not_applicable"
    )
    candidate_identities = {**paid_spec["identities"], **paid_spec["candidate_identity_overrides"]}
    outputs = {
        "identities.json": {
            "schema_version": 1,
            "run_id": paid_spec["run_id"],
            "baseline_sha256": paid_spec["baseline_sha256"],
            "control": paid_spec["identities"],
            "candidate": candidate_identities,
            "changed_identity_fields": paid_spec["changed_identity_fields"],
            "telemetry_records": [
                {
                    "signal": "identity_and_environment",
                    "run_id": paid_spec["run_id"],
                    "model": "glm-4.7-flash",
                    "revision": "complete",
                    "code": "synthetic-demo",
                    "runtime": "synthetic-vllm",
                    "hardware": "synthetic-l40s",
                    "configuration": "candidate",
                    "operator_shape_dictionary": {"attention": [1, 1]},
                },
                {
                    "signal": "model_structure",
                    "run_id": paid_spec["run_id"],
                    "module_dictionary": {"0": "attention"},
                    "shape_dictionary": {"0": [1, 1]},
                    "dtype": "bf16",
                    "layout": "row_major",
                    "architecture_aggregates": {"layers": 1},
                },
            ],
        },
        "measurement.json": {
            "schema_version": 1,
            "run_id": paid_spec["run_id"],
            "scout_id": paid_spec["scout_id"],
            "fidelity": paid_spec["fidelity"],
            "control_id": paid_spec["control_id"],
            "candidate_id": paid_spec["candidate_id"],
            "changed_variable": paid_spec["changed_variable"],
            "scope": paid_spec["claim_scope"],
            "primary_metric": paid_spec["prediction"]["metric"],
            "predicted_effect_fraction": paid_spec["prediction"]["point_estimate_fraction"],
            "effect_formula": paid_spec["measurement_contract"]["effect_formula"],
            "protocol": paid_spec["measurement_contract"]["protocol"],
            "brackets": [
                {"control_before": 100.0, "candidate": 101.0, "control_after": 100.0},
                {"control_before": 100.0, "candidate": 101.0, "control_after": 100.0},
            ],
            "observed_effect_fraction": 0.01,
        },
        "telemetry.json": telemetry_summary,
        "quality.json": {
            "schema_version": 1,
            "run_id": paid_spec["run_id"],
            "policy_sha256s": {
                name: paid_spec["gates"][name]["policy_sha256"]
                for name in ("correctness", "quality", "slo")
            },
            "gates": {"correctness": True, "quality": True, "slo": True},
            "telemetry_records": [
                {
                    "signal": "quality_and_correctness",
                    "run_id": paid_spec["run_id"],
                    "sample_id": "quality-1",
                    "policy_sha256": paid_spec["gates"]["quality"]["policy_sha256"],
                    "score": 1.0,
                    "pass": True,
                    "error": "none",
                }
            ],
        },
        "cost.json": {
            "schema_version": 1,
            "run_id": paid_spec["run_id"],
            "currency": "USD",
            "line_items": [
                {"name": "candidate arm", "quantity": 1.0, "unit_rate_usd": 0.05, "cost_usd": 0.05}
            ],
            "result_cost_usd": 0.05,
            "telemetry_records": [
                {
                    "signal": "resource_and_cost_ledger",
                    "run_id": paid_spec["run_id"],
                    "allocation_id": "demo-allocation",
                    "start_ns": 1,
                    "end_ns": 2,
                    "gpu_seconds": 120,
                    "rate": 0.05,
                    "currency": "USD",
                    "total_cost": 0.05,
                }
            ],
        },
        "run.log": "synthetic matched server run completed\n",
        "events.jsonl": [
            {
                "signal": "request_timeline",
                "run_id": paid_spec["run_id"],
                "monotonic_ns": 1,
                "request_id": "request-1",
                "iteration_id": "iteration-1",
                "arrival_ns": 1,
                "prompt_tokens": 8192,
                "output_tokens": 128,
                "queue_ns": 1,
                "ttft_ns": 2,
                "tpot_ns": 3,
                "end_to_end_ns": 4,
                "status": "success",
            },
            {
                "signal": "scheduler_timeline",
                "run_id": paid_spec["run_id"],
                "monotonic_ns": 1,
                "request_id": "request-1",
                "iteration_id": "iteration-1",
                "iterations": 128,
                "scheduled_prefill_tokens": 8192,
                "scheduled_decode_tokens": 128,
                "mean_batch_size": 8.0,
                "max_waiting_requests": 0,
                "preemptions": 0,
                "kv_occupancy_summary": {"mean": 0.5},
            },
        ],
        "system.jsonl": [
            {
                "signal": "accelerator_health",
                "run_id": paid_spec["run_id"],
                "monotonic_ns": 1,
                "utilization": 0.8,
                "vram_bytes": 1,
                "clock_hz": 1,
                "power_w": 1,
                "temperature_c": 40,
            },
            {
                "signal": "host_and_transfer_health",
                "run_id": paid_spec["run_id"],
                "monotonic_ns": 1,
                "cpu_utilization": 0.4,
                "rss_bytes": 1,
                "io_bytes": 1,
                "network_bytes": 1,
            },
        ],
    }
    for name, value in outputs.items():
        path = run_directory / name
        if isinstance(value, str):
            path.write_text(value)
        elif isinstance(value, list):
            path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in value))
        else:
            path.write_text(json.dumps(value, sort_keys=True) + "\n")
    bundle = package_run_directory(director.artifacts, paid_spec, spec_path, run_directory)
    director.complete_run(
        _result(
            "demo-server-transfer",
            "attention-local",
            "scientific_negative",
            artifact_refs=[bundle["manifest_sha256"]],
            effect=0.01,
            residual="dense compute or host dependency",
            cost=0.05,
            artifact_bundle_sha256=bundle["manifest_sha256"],
            telemetry_summary=bundle["telemetry_summary"],
            spec=paid_spec,
        )
    )

    observation_two_ref = director.artifacts.put_json(
        {"cycle": 2, "source": "synthetic trace", "dense_proxy_fraction": 0.35}
    )
    director.record_observation(
        _observation(2, "dense work is now the largest residual", "dense_proxy_fraction", observation_two_ref)
    )
    director.propose_scouts([
        _scout("dense-local", 2, "bottleneck_adjacent", "dense", "trace_local"),
        _scout("dense-inversion", 2, "bottleneck_adjacent", "dense", "first_principles"),
        _scout("scheduler-cross", 2, "cross_stack", "scheduler", "literature_recombination"),
        _scout("representation-change", 2, "model_architecture", "representation", "cross_model_analogy"),
        _scout("dense-skeptic", 2, "adversarial", "measurement", "adversarial"),
    ])
    director.select_portfolio(2)
    simulation_ref = director.artifacts.put_json(
        {"run_id": "representation-simulation", "predicted": 0.1, "observed": 0.08}
    )
    simulation_input_ref = director.artifacts.put_json({"simulation": "representation-v1", "seed": 1})
    simulation_spec = _local_spec(
        "representation-simulation",
        "representation-change",
        fidelity="simulation",
        point_estimate_fraction=0.1,
        artifact_refs=[simulation_input_ref],
    )
    director.register_local_run(simulation_spec)
    director.complete_run(
        _result(
            "representation-simulation",
            "representation-change",
            "scientific_positive",
            artifact_refs=[simulation_ref],
            effect=0.08,
            residual="scheduler launch gaps",
            cost=0.0,
            spec=simulation_spec,
        )
    )
    class DemoCleanupAdapter:
        def delete(self, resource_id: str) -> None:
            self.deleted = resource_id

        def exists(self, resource_id: str) -> bool:
            return False

        def inventory_contains(self, resource_id: str) -> bool:
            return False

    lab.request_cleanup(
        "demo-allocation", owner="codex-demo", epoch=lease["epoch"], now=now.timestamp() + 99
    )
    cleanup = lab.sweep_due({"fake": DemoCleanupAdapter()}, now=now.timestamp() + 100)
    if cleanup != [{"allocation_id": "demo-allocation", "status": "cleaned"}]:
        raise RuntimeError(f"synthetic cleanup failed: {cleanup}")
    manifest = director.artifacts.verify_bundle(bundle["manifest_sha256"])
    cost_evidence_sha256 = next(entry["sha256"] for entry in manifest["entries"] if entry["role"] == "cost")
    lab.settle_session(
        admission["reservation_id"],
        actual_cost_usd=0.12,
        cost_evidence_sha256=cost_evidence_sha256,
    )
    lab_snapshot = lab.snapshot()
    lab.close()
    director.write_state()
    director.write_coordinator_context()
    return {
        "state": director.state(),
        "lab_snapshot": lab_snapshot,
        "coordinator_context": director.coordinator_context(),
    }
