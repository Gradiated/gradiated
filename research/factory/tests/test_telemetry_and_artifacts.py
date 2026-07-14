from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from grad_research.artifacts import ArtifactIntegrityError, ArtifactStore, package_run_directory
from grad_research.director import ResearchDirector
from grad_research.labd import LabDatabase
from grad_research.telemetry import (
    TELEMETRY_CATEGORIES,
    build_complete_telemetry_summary,
    build_telemetry_contract,
    required_artifact_roles,
    validate_telemetry_contract,
)
from grad_research.util import ValidationError
from grad_research.util import content_hash

from helpers import HASH_A, paid_run_spec, scout


def write_run_files(
    directory: Path,
    spec: dict,
    *,
    claimed_attribution_coverage: float | str = "not_applicable",
) -> tuple[Path, Path]:
    spec_path = directory / "spec.json"
    run_directory = directory / "output"
    run_directory.mkdir()
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    diagnostic = spec["telemetry_contract"]["scoring_mode"] == "diagnostic_only"
    summary = build_complete_telemetry_summary(
        spec["telemetry_contract"],
        attribution_coverage=1.0 if diagnostic else claimed_attribution_coverage,
        observer_status="pass" if diagnostic else "not_applicable",
        throughput_change_fraction=0.01 if diagnostic else "not_applicable",
        median_latency_change_fraction=0.01 if diagnostic else "not_applicable",
        tail_latency_change_fraction=0.01 if diagnostic else "not_applicable",
    )
    candidate_identities = {**spec["identities"], **spec["candidate_identity_overrides"]}
    outputs = {
        "identities.json": {
            "schema_version": 1,
            "run_id": spec["run_id"],
            "baseline_sha256": spec["baseline_sha256"],
            "control": spec["identities"],
            "candidate": candidate_identities,
            "changed_identity_fields": spec["changed_identity_fields"],
            "telemetry_records": [
                {
                    "signal": "identity_and_environment",
                    "run_id": spec["run_id"],
                    "model": "glm-4.7-flash",
                    "revision": "complete",
                    "code": "test-code",
                    "runtime": "vllm",
                    "hardware": "l40s",
                    "configuration": "candidate",
                    "operator_shape_dictionary": {"dense": [1, 1]},
                },
                {
                    "signal": "model_structure",
                    "run_id": spec["run_id"],
                    "module_dictionary": {"0": "dense"},
                    "shape_dictionary": {"0": [1, 1]},
                    "dtype": "bf16",
                    "layout": "row_major",
                    "architecture_aggregates": {"layers": 1},
                },
            ],
        },
        "measurement.json": {
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
            "brackets": [
                {"control_before": 100.0, "candidate": 101.0, "control_after": 100.0},
                {"control_before": 100.0, "candidate": 101.0, "control_after": 100.0},
            ],
            "observed_effect_fraction": 0.01,
        },
        "telemetry.json": summary,
        "quality.json": {
            "schema_version": 1,
            "run_id": spec["run_id"],
            "policy_sha256s": {
                name: spec["gates"][name]["policy_sha256"]
                for name in ("correctness", "quality", "slo")
            },
            "gates": {"correctness": True, "quality": True, "slo": True},
            "telemetry_records": [
                {
                    "signal": "quality_and_correctness",
                    "run_id": spec["run_id"],
                    "sample_id": "quality-1",
                    "policy_sha256": spec["gates"]["quality"]["policy_sha256"],
                    "score": 1.0,
                    "pass": True,
                    "error": "none",
                }
            ],
        },
        "cost.json": {
            "schema_version": 1,
            "run_id": spec["run_id"],
            "currency": "USD",
            "line_items": [
                {"name": "candidate arm", "quantity": 1.0, "unit_rate_usd": 0.05, "cost_usd": 0.05}
            ],
            "result_cost_usd": 0.05,
            "telemetry_records": [
                {
                    "signal": "resource_and_cost_ledger",
                    "run_id": spec["run_id"],
                    "allocation_id": "allocation-1",
                    "start_ns": 1,
                    "end_ns": 2,
                    "gpu_seconds": 120,
                    "rate": 0.05,
                    "currency": "USD",
                    "total_cost": 0.05,
                }
            ],
        },
        "run.log": "run completed\n",
        "events.jsonl": [
            {
                "signal": "request_timeline",
                "run_id": spec["run_id"],
                "monotonic_ns": 1,
                "request_id": "r1",
                "iteration_id": "i1",
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
                "run_id": spec["run_id"],
                "monotonic_ns": 1,
                "request_id": "r1",
                "iteration_id": "i1",
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
                "run_id": spec["run_id"],
                "monotonic_ns": 1,
                "utilization": 0.8,
                "vram_bytes": 1,
                "clock_hz": 1,
                "power_w": 1,
                "temperature_c": 40,
            },
            {
                "signal": "host_and_transfer_health",
                "run_id": spec["run_id"],
                "monotonic_ns": 1,
                "cpu_utilization": 0.3,
                "rss_bytes": 1,
                "io_bytes": 1,
                "network_bytes": 1,
            },
        ],
    }
    if diagnostic:
        outputs["deep.jsonl"] = [
            {
                "signal": "scheduler_iteration_trace",
                "run_id": spec["run_id"],
                "iteration_id": "i1",
                "phase": "decode",
                "start_ns": 1,
                "end_ns": 2,
                "scheduled_tokens": 8,
                "batch_composition": {"decode": 8},
                "kv_state": {"tokens": 65536},
            },
            {
                "signal": "cpu_gpu_dependency_trace",
                "run_id": spec["run_id"],
                "thread_id": "t1",
                "stream_id": "s1",
                "correlation_id": "c1",
                "start_ns": 1,
                "end_ns": 2,
                "dependency": "launch",
            },
            {
                "signal": "kernel_resource_trace",
                "run_id": spec["run_id"],
                "kernel": "dense",
                "grid": [1, 1, 1],
                "block": [32, 1, 1],
                "registers": 32,
                "shared_memory": 0,
                "start_ns": 1,
                "end_ns": 2,
            },
        ]
    for name, value in outputs.items():
        path = run_directory / name
        if isinstance(value, str):
            path.write_text(value)
        elif isinstance(value, list):
            path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in value))
        else:
            path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return spec_path, run_directory


def prepare_paid_director(
    root: Path, *, diagnostic: bool = False
) -> tuple[ResearchDirector, LabDatabase, dict]:
    director = ResearchDirector(root / "lab", "glm47")
    director.freeze_baseline(
        {
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
    )
    observation_ref = director.artifacts.put_json({"critical_path_fraction": 0.35})
    director.record_observation(
        {
            "schema_version": 1,
            "id": "obs-1",
            "cycle": 1,
            "evidence_class": "measured",
            "summary": "attention work may be dependency critical",
            "scope": {
                "model": "glm-4.7-flash",
                "revision": "complete",
                "workload": "fixed-8k-c8",
                "phase": "decode",
                "concurrency": "8",
                "software": "vllm",
                "hardware": "l40s",
            },
            "metrics": [
                {
                    "name": "critical_path_fraction",
                    "value": 0.35,
                    "unit": "fraction",
                    "time_semantics": "critical_path_union",
                    "coverage": 0.98,
                }
            ],
            "instrumentation_gaps": [],
            "artifact_refs": [observation_ref],
        }
    )
    director.propose_scouts(
        [
            scout("attention-1", slot="bottleneck_adjacent", family="attention", origin="trace_local"),
            scout("attention-2", slot="bottleneck_adjacent", family="attention", origin="first_principles"),
            scout("runtime-1", slot="cross_stack", family="runtime", origin="literature_recombination"),
            scout("model-1", slot="model_architecture", family="representation", origin="cross_model_analogy"),
            scout("skeptic-1", slot="adversarial", family="measurement", origin="adversarial"),
        ]
    )
    director.select_portfolio(1)
    spec, now = paid_run_spec()
    if diagnostic:
        spec["arm_role"] = "diagnostic"
        spec["telemetry_contract"] = build_telemetry_contract("diagnostic_only")
        spec["artifact_contract"]["required"].append(
            {
                "role": "deep_trace",
                "path": "deep.jsonl",
                "media_type": "application/x-ndjson",
            }
        )
    for name, check in spec["preflight"].items():
        check["evidence_sha256"] = director.artifacts.put_json(
            {
                "schema_version": 1,
                "check": name,
                "pass": True,
                "bound_sha256": check["bound_sha256"],
            }
        )
    lab = LabDatabase(root / "labd.sqlite3")
    lease = lab.acquire_coordinator("glm47", "codex-test", ttl_seconds=900, now=now.timestamp())
    lab.ensure_budget("glm47-cost", authorized_usd=1.0)
    director.admit_paid_run(spec, lab=lab, owner="codex-test", epoch=lease["epoch"], now=now)
    return director, lab, spec


def scientific_result(bundle: dict, spec: dict) -> dict:
    return {
        "schema_version": 1,
        "id": "result-run-1",
        "run_id": "run-1",
        "scout_id": "attention-1",
        "control_id": spec["control_id"],
        "candidate_id": spec["candidate_id"],
        "changed_variable": spec["changed_variable"],
        "baseline_sha256": spec["baseline_sha256"],
        "prediction_sha256": content_hash(spec["prediction"]),
        "outcome_class": "scientific_negative",
        "fidelity": "matched_server",
        "scope": spec["claim_scope"],
        "cost_usd": 0.05,
        "artifact_refs": [bundle["manifest_sha256"]],
        "artifact_bundle_sha256": bundle["manifest_sha256"],
        "telemetry_summary": bundle["telemetry_summary"],
        "next_action": "measure the residual dense and host path",
        "gates": {"correctness": True, "quality": True, "slo": True},
        "primary_metric": spec["prediction"]["metric"],
        "observed_effect_fraction": 0.01,
        "predicted_effect_fraction": spec["prediction"]["point_estimate_fraction"],
        "residual_bottleneck": "dense compute or host launch dependency",
    }


class TelemetryContractTests(unittest.TestCase):
    def test_scoreable_template_covers_every_system_layer_without_intrusive_profiling(self):
        contract = build_telemetry_contract("scoreable")
        report = validate_telemetry_contract(contract)
        self.assertEqual(TELEMETRY_CATEGORIES, set(report["capture_categories"]))
        self.assertFalse(report["intrusive"])
        self.assertIn("events", required_artifact_roles(contract))
        self.assertIn("system_samples", required_artifact_roles(contract))

    def test_deep_profiler_is_diagnostic_only_and_bracketed(self):
        contract = build_telemetry_contract("diagnostic_only")
        report = validate_telemetry_contract(contract)
        self.assertTrue(report["intrusive"])
        self.assertTrue(contract["observer_effect"]["required"])
        broken = copy.deepcopy(contract)
        broken["scoring_mode"] = "scoreable"
        broken["collection_budget"]["max_cpu_overhead_fraction"] = 0.01
        with self.assertRaisesRegex(ValidationError, "scoreable"):
            validate_telemetry_contract(broken)

    def test_unsupported_counter_is_explicit_instead_of_silently_substituted(self):
        contract = build_telemetry_contract("scoreable")
        scheduler = next(signal for signal in contract["signals"] if signal["name"] == "scheduler_timeline")
        scheduler.update(
            {
                "status": "unavailable",
                "reason": "runtime has no scheduler hook",
                "next_probe": "add an iteration event hook before scheduler attribution",
            }
        )
        report = validate_telemetry_contract(contract)
        self.assertIn("scheduler_timeline", report["unavailable_signal_names"])
        self.assertIn("scheduler", report["unavailable_categories"])


class ArtifactBundleTests(unittest.TestCase):
    def test_successful_diagnostic_closes_run_without_updating_mechanism_beliefs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            director, lab, spec = prepare_paid_director(root, diagnostic=True)
            try:
                spec_path, run_directory = write_run_files(root, spec)
                bundle = package_run_directory(director.artifacts, spec, spec_path, run_directory)
                result = {
                    "schema_version": 1,
                    "id": "diagnostic-result-run-1",
                    "run_id": spec["run_id"],
                    "scout_id": spec["scout_id"],
                    "control_id": spec["control_id"],
                    "candidate_id": spec["candidate_id"],
                    "changed_variable": spec["changed_variable"],
                    "baseline_sha256": spec["baseline_sha256"],
                    "prediction_sha256": content_hash(spec["prediction"]),
                    "outcome_class": "diagnostic_valid",
                    "fidelity": spec["fidelity"],
                    "scope": spec["claim_scope"],
                    "cost_usd": 0.05,
                    "artifact_refs": [bundle["manifest_sha256"]],
                    "artifact_bundle_sha256": bundle["manifest_sha256"],
                    "telemetry_summary": bundle["telemetry_summary"],
                    "gates": {"correctness": True, "quality": True, "slo": True},
                    "diagnostic_summary": "dense work is dependency critical in the bounded trace",
                    "residual_bottleneck": "dense kernel resource limits remain unresolved",
                    "next_action": "run an exact-shape resource-counter microbenchmark",
                }
                director.complete_run(result)
                state = director.state()
                self.assertEqual(1, state["outcome_counts"]["diagnostic_valid"])
                self.assertEqual(1, state["research_metrics"]["valid_diagnostic_outcomes"])
                self.assertEqual({}, state["mechanism_beliefs"])
                self.assertEqual(result["residual_bottleneck"], state["residual_bottleneck"])
                manifest = director.artifacts.verify_bundle(bundle["manifest_sha256"], deep=True)
                self.assertEqual("run", manifest["kind"])
            finally:
                lab.close()

    def test_early_paid_failure_uses_compact_evidence_without_fake_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            director, lab, spec = prepare_paid_director(root)
            try:
                spec_path, run_directory = write_run_files(root, spec)
                planned = sorted(
                    signal["name"]
                    for signal in spec["telemetry_contract"]["signals"]
                    if signal["status"] == "capture"
                )
                failure_telemetry = {
                    "schema_version": 1,
                    "run_id": spec["run_id"],
                    "captured_signals": ["identity_and_environment"],
                    "missing_signals": [name for name in planned if name != "identity_and_environment"],
                    "failure_stage": "server_start",
                }
                (run_directory / "telemetry.json").write_text(json.dumps(failure_telemetry) + "\n")
                (run_directory / "failure.json").write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "run_id": spec["run_id"],
                            "failure_class": "server_start_failed",
                            "stage": "server_start",
                            "message": "runtime exited before readiness",
                        }
                    )
                    + "\n"
                )
                bundle = package_run_directory(
                    director.artifacts,
                    spec,
                    spec_path,
                    run_directory,
                    failure_class="server_start_failed",
                )
                result = {
                    "schema_version": 1,
                    "id": "result-run-1",
                    "run_id": spec["run_id"],
                    "scout_id": spec["scout_id"],
                    "control_id": spec["control_id"],
                    "candidate_id": spec["candidate_id"],
                    "changed_variable": spec["changed_variable"],
                    "baseline_sha256": spec["baseline_sha256"],
                    "prediction_sha256": content_hash(spec["prediction"]),
                    "outcome_class": "operational_failure",
                    "failure_class": "server_start_failed",
                    "fidelity": spec["fidelity"],
                    "scope": spec["claim_scope"],
                    "cost_usd": 0.05,
                    "artifact_refs": [bundle["manifest_sha256"]],
                    "artifact_bundle_sha256": bundle["manifest_sha256"],
                    "telemetry_summary": failure_telemetry,
                    "next_action": "repair readiness and retry the same immutable setup",
                }
                director.complete_run(result)
                state = director.state()
                self.assertEqual(1, state["research_metrics"]["operational_failures"])
                self.assertEqual({}, state["mechanism_beliefs"])
                manifest = director.artifacts.verify_bundle(bundle["manifest_sha256"], deep=True)
                self.assertEqual("run_failure", manifest["kind"])
                self.assertNotIn("measurement_summary", manifest["required_roles"])
                self.assertNotIn("quality", manifest["required_roles"])
            finally:
                lab.close()

    def test_run_packaging_is_content_addressed_complete_and_deeply_verifiable(self):
        spec, _ = paid_run_spec()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_path, run_directory = write_run_files(root, spec)
            store = ArtifactStore(root / "lab", spec["program_id"])
            first = package_run_directory(store, spec, spec_path, run_directory)
            second = package_run_directory(store, spec, spec_path, run_directory)
            self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
            manifest = store.verify_bundle(first["manifest_sha256"], deep=True)
            self.assertEqual(required_artifact_roles(spec["telemetry_contract"]), set(manifest["required_roles"]))
            self.assertEqual(spec["run_id"], manifest["bundle_id"])
            self.assertEqual([], first["telemetry_summary"]["missing_signals"])

            events = next(entry for entry in manifest["entries"] if entry["role"] == "events")
            events_path = store.object_path(events["sha256"])
            events_path.chmod(0o644)
            events_path.write_text("tampered\n")
            with self.assertRaises(ArtifactIntegrityError):
                store.verify_bundle(first["manifest_sha256"], deep=True)

    def test_missing_declared_output_fails_before_bundle_finalization(self):
        spec, _ = paid_run_spec()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_path, run_directory = write_run_files(root, spec)
            (run_directory / "system.jsonl").unlink()
            store = ArtifactStore(root / "lab", spec["program_id"])
            with self.assertRaisesRegex(ValidationError, "absent or empty"):
                package_run_directory(store, spec, spec_path, run_directory)
            self.assertFalse((store.bundles_dir / f"{spec['run_id']}.json").exists())

    def test_nonempty_but_contradictory_evidence_is_rejected(self):
        mutations = {
            "identities.json": lambda value: value["candidate"].update(
                {"configuration_sha256": "c" * 64}
            ),
            "measurement.json": lambda value: value.update({"observed_effect_fraction": 0.5}),
            "quality.json": lambda value: value["gates"].update({"quality": False}),
            "cost.json": lambda value: value.update({"result_cost_usd": 0.19}),
        }
        for filename, mutate in mutations.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                spec, _ = paid_run_spec()
                spec_path, run_directory = write_run_files(root, spec)
                path = run_directory / filename
                value = json.loads(path.read_text())
                mutate(value)
                path.write_text(json.dumps(value, sort_keys=True) + "\n")
                store = ArtifactStore(root / "lab", spec["program_id"])
                with self.assertRaises(ValidationError):
                    package_run_directory(store, spec, spec_path, run_directory)
                self.assertFalse((store.bundles_dir / f"{spec['run_id']}.json").exists())

    def test_paid_scientific_result_requires_complete_attributable_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            director, lab, spec = prepare_paid_director(root)
            try:
                spec_path, run_directory = write_run_files(root, spec)
                bundle = package_run_directory(director.artifacts, spec, spec_path, run_directory)
                director.complete_run(scientific_result(bundle, spec))
                observability = director.state()["observability"]
                self.assertEqual(1, observability["artifact_complete_runs"])
                self.assertEqual(0, observability["scientific_attribution_gate_passes"])
                self.assertEqual({}, observability["telemetry_gaps"])
            finally:
                lab.close()

    def test_paid_result_cannot_change_preregistered_identity_or_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            director, lab, spec = prepare_paid_director(root)
            try:
                spec_path, run_directory = write_run_files(root, spec)
                bundle = package_run_directory(director.artifacts, spec, spec_path, run_directory)
                valid = scientific_result(bundle, spec)
                mutations = {
                    "scout_id": "model-1",
                    "fidelity": "simulation",
                    "scope": {"model": "another-model"},
                    "prediction_sha256": "f" * 64,
                }
                for field, value in mutations.items():
                    with self.subTest(field=field):
                        candidate = copy.deepcopy(valid)
                        candidate[field] = value
                        with self.assertRaisesRegex(ValidationError, "immutable run spec"):
                            director.complete_run(candidate)
                self.assertEqual(0, director.state()["research_metrics"]["valid_scientific_outcomes"])
            finally:
                lab.close()

    def test_self_reported_trace_coverage_cannot_override_raw_telemetry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            director, lab, spec = prepare_paid_director(root)
            try:
                spec_path, run_directory = write_run_files(
                    root, spec, claimed_attribution_coverage=0.90
                )
                with self.assertRaisesRegex(ValidationError, "differs from raw telemetry"):
                    package_run_directory(director.artifacts, spec, spec_path, run_directory)
                self.assertEqual(0, director.state()["research_metrics"]["valid_scientific_outcomes"])
            finally:
                lab.close()


if __name__ == "__main__":
    unittest.main()
