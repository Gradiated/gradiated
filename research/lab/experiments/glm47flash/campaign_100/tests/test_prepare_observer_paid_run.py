from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from grad_research.admission import PREFLIGHT_BINDINGS, PREFLIGHT_CHECKS, validate_paid_run
from grad_research.artifacts import ArtifactStore
from grad_research.events import EventStore
from grad_research.telemetry import build_telemetry_contract
from grad_research.util import ValidationError, content_hash


ROOT = Path(__file__).resolve().parents[1]
NEBIUS = ROOT / "nebius"
sys.path.insert(0, str(NEBIUS))

from prepare_observer_paid_run import (  # noqa: E402
    EXPECTED_OPERATIONAL_STARTUP_ISOLATION,
    prepare_observer_paid_run,
)


HASHES = {name: f"{index:064x}" for index, name in enumerate(
    (
        "checkpoint",
        "tokenizer",
        "runtime",
        "workload",
        "quality",
        "slo",
        "control_harness",
        "control_configuration",
        "candidate_harness",
        "candidate_configuration",
    ),
    start=1,
)}
PROGRAM_ID = "glm-4.7-flash"
RUN_ID = "glm47-observer-diagnostic-l40s-v17"
SCOUT_ID = "glm47-dense-resource-signature"
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def baseline() -> dict:
    return {
        "schema_version": 1,
        "id": "glm47-l40s-vllm-awq-split4-v28",
        "model_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
        "checkpoint_manifest_sha256": HASHES["checkpoint"],
        "tokenizer_manifest_sha256": HASHES["tokenizer"],
        "runtime_manifest_sha256": HASHES["runtime"],
        "workload_manifest_sha256": HASHES["workload"],
        "quality_policy_sha256": HASHES["quality"],
        "slo_policy_sha256": HASHES["slo"],
        "cost_denominator": "paired diagnostic eligible output tokens",
    }


def preregistration() -> dict:
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "program_id": PROGRAM_ID,
        "campaign_id": "glm47-nebius-25",
        "setup_key": "l40s:vllm:glm47:observer",
        "factory_recording_plan": {
            "primary_paid_scout_id": SCOUT_ID,
            "secondary_packet": "glm47-host-scheduler-critical-path",
            "secondary_evidence_disposition": (
                "Record host and scheduler findings as a typed observation over the same bundle."
            ),
        },
        "stock_control": {
            "provider": "Nebius",
            "platform": "gpu-l40s-a",
            "preset": "1gpu-16vcpu-64gb",
            "changed_variable": "Observer state only",
        },
        "causal_hypotheses": [
            {
                "id": "dense_dependency_resource_signature",
                "hypothesis": "Dense work lies on at least 20% of the covered dependency union.",
                "falsifier": "Dense work is below 20% or dependency coverage is below 95%.",
            }
        ],
        "workload_geometry": {
            "arm_sequence": ["A1_observer_off", "B1_observer_on", "A2_observer_off"],
            "prompt_tokens_per_request": 8192,
            "output_tokens_per_request": 32,
            "concurrency": 8,
            "requests": 8,
            "synchronized_barrier": True,
            "temperature": 0,
            "ignore_eos": True,
            "prefix_cache": False,
        },
        "quality_gate": {"diagnostic_only": True},
        "operational_startup_isolation": dict(EXPECTED_OPERATIONAL_STARTUP_ISOLATION),
        "claim_limit": "Diagnostic localization only.",
    }


def artifact_contract() -> dict:
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "root": f"runs/{RUN_ID}",
        "hash_manifest": True,
        "required": [
            {"role": "identities", "path": "identities.json", "media_type": "application/json"},
            {"role": "events", "path": "events.jsonl", "media_type": "application/x-ndjson"},
            {
                "role": "system_samples",
                "path": "system-samples.jsonl",
                "media_type": "application/x-ndjson",
            },
            {
                "role": "quality",
                "path": "quality-and-correctness.json",
                "media_type": "application/json",
            },
            {
                "role": "measurement_summary",
                "path": "measurement.json",
                "media_type": "application/json",
            },
            {"role": "deep_trace", "path": "deep-trace.tar.zst", "media_type": "application/zstd"},
            {"role": "telemetry_summary", "path": "telemetry.json", "media_type": "application/json"},
            {"role": "cost", "path": "cost.json", "media_type": "application/json"},
            {"role": "logs", "path": "logs.tar.zst", "media_type": "application/zstd"},
        ],
    }


def identities() -> dict:
    frozen = baseline()
    return {
        "schema_version": 1,
        "control": {
            "model_revision": frozen["model_revision"],
            "checkpoint_manifest_sha256": frozen["checkpoint_manifest_sha256"],
            "tokenizer_manifest_sha256": frozen["tokenizer_manifest_sha256"],
            "runtime_manifest_sha256": frozen["runtime_manifest_sha256"],
            "workload_manifest_sha256": frozen["workload_manifest_sha256"],
            "harness_sha256": HASHES["control_harness"],
            "configuration_sha256": HASHES["control_configuration"],
            "hardware_scope": "Nebius L40S 48GB; gpu-l40s-a; 1gpu-16vcpu-64gb",
        },
        "candidate_overrides": {
            "harness_sha256": HASHES["candidate_harness"],
            "configuration_sha256": HASHES["candidate_configuration"],
        },
    }


class ObserverPaidRunPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.lab_root = Path(self.temporary.name) / "lab"
        events = EventStore(self.lab_root, PROGRAM_ID)
        events.append("baseline_frozen", baseline())
        events.append(
            "scout_proposed",
            {
                "schema_version": 1,
                "id": SCOUT_ID,
                "cycle": 1,
                "setup_key": "l40s:vllm:glm47:observer",
            },
        )
        self.store = ArtifactStore(self.lab_root, PROGRAM_ID)
        self.preregistration_path = Path(self.temporary.name) / "PREREGISTRATION.json"
        self.artifact_contract_path = Path(self.temporary.name) / "ARTIFACT_CONTRACT.json"
        self.identities_path = Path(self.temporary.name) / "IDENTITIES.json"
        self.preflight_path = Path(self.temporary.name) / "PREFLIGHT.json"
        self.preregistration_path.write_text(json.dumps(preregistration()))
        self.artifact_contract_path.write_text(json.dumps(artifact_contract()))
        self.identities_path.write_text(json.dumps(identities()))
        self._write_preflight()

    def _write_preflight(self) -> None:
        identity = identities()
        candidate = {**identity["control"], **identity["candidate_overrides"]}
        references = {}
        for check in sorted(PREFLIGHT_CHECKS):
            bound_sha256 = candidate[PREFLIGHT_BINDINGS[check]]
            references[check] = self.store.put_json(
                {
                    "schema_version": 1,
                    "check": check,
                    "pass": True,
                    "bound_sha256": bound_sha256,
                }
            )
        self.preflight_path.write_text(json.dumps({"schema_version": 1, "checks": references}))

    def _prepare(self) -> dict:
        return prepare_observer_paid_run(
            lab_root=self.lab_root,
            preregistration_path=self.preregistration_path,
            artifact_contract_path=self.artifact_contract_path,
            identities_path=self.identities_path,
            preflight_path=self.preflight_path,
            now=NOW,
        )

    def test_emits_one_factory_admissible_diagnostic_run(self):
        spec = self._prepare()
        admission = validate_paid_run(spec, now=NOW)

        self.assertEqual("admit", admission["decision"])
        self.assertEqual(SCOUT_ID, spec["scout_id"])
        self.assertEqual(content_hash(baseline()), spec["baseline_sha256"])
        self.assertEqual("diagnostic", spec["arm_role"])
        self.assertEqual("diagnostic_only", spec["telemetry_contract"]["scoring_mode"])
        self.assertEqual(build_telemetry_contract("diagnostic_only"), spec["telemetry_contract"])
        self.assertEqual(
            ["observer_off", "observer_on", "observer_off"],
            spec["telemetry_contract"]["observer_effect"]["bracket"],
        )
        self.assertEqual(
            ["configuration_sha256", "harness_sha256"],
            spec["changed_identity_fields"],
        )
        self.assertEqual(
            set(spec["candidate_identity_overrides"]),
            {"configuration_sha256", "harness_sha256"},
        )
        self.assertEqual(2000, spec["budget"]["timeout_seconds"])
        self.assertEqual(0.8581222, spec["budget"]["hourly_rate_usd"])
        self.assertEqual(0.07, spec["budget"]["cleanup_reserve_usd"])
        self.assertEqual(0.55, spec["budget"]["max_spend_usd"])
        self.assertEqual("2026-07-14T12:33:20Z", spec["watchdog"]["absolute_deadline_utc"])
        self.assertEqual("nebius", spec["provider_contract"]["provider"])
        self.assertEqual(RUN_ID, spec["provider_contract"]["idempotency_key"])
        capability = spec["provider_contract"]["nsys_launch_capability"]
        fixture = NEBIUS / "fixtures" / "nsys-launch-help-2026.3.1.157.txt"
        self.assertEqual("2026.3.1.157", capability["package_version"])
        self.assertEqual("nsys launch --help", capability["command"])
        self.assertTrue(capability["before_model_transfer"])
        self.assertEqual(
            {
                "--session-new",
                "--trace",
                "--cuda-graph-trace",
                "--cuda-event-trace",
                "--sample",
                "--cpuctxsw",
            },
            set(capability["required_flags"]),
        )
        self.assertEqual(["--force-overwrite"], capability["forbidden_flags"])
        self.assertTrue(fixture.is_file())
        self.assertEqual(
            hashlib.sha256(fixture.read_bytes()).hexdigest(),
            capability["fixture_sha256"],
        )
        self.assertEqual(
            "A1 observer-off / B1 observer-on / A2 observer-off; 8 requests; c8; 8192 input + 32 output tokens",
            spec["claim_scope"]["workload"],
        )
        self.assertEqual(
            EXPECTED_OPERATIONAL_STARTUP_ISOLATION,
            spec["operational_startup_isolation"],
        )
        self.assertEqual(
            EXPECTED_OPERATIONAL_STARTUP_ISOLATION,
            spec["provider_contract"]["operational_startup_isolation"],
        )
        self.assertTrue(all(spec["cleanup"].values()))
        self.assertEqual(
            "typed_observation_same_evidence_bundle",
            spec["post_run_recording"]["secondary"]["disposition"],
        )
        self.assertFalse(spec["post_run_recording"]["secondary"]["additional_paid_run"])
        contract = spec["observer_dependency_attribution_contract"]
        self.assertEqual(contract["contract_id"], "observer-dependency-attribution-v1")
        self.assertEqual(len(contract["input_artifact_refs"]), 6)
        self.assertTrue(contract["fail_closed"])

    def test_preflight_references_are_deeply_verified_and_identity_bound(self):
        manifest = json.loads(self.preflight_path.read_text())
        reference = manifest["checks"]["runtime_probe"]
        object_path = self.store.object_path(reference)
        object_path.chmod(0o644)
        object_path.write_text("corrupt")

        with self.assertRaisesRegex(Exception, "failed its hash"):
            self._prepare()

    def test_rejects_control_identity_drift_from_frozen_factory_baseline(self):
        value = identities()
        value["control"]["checkpoint_manifest_sha256"] = "f" * 64
        self.identities_path.write_text(json.dumps(value))

        with self.assertRaisesRegex(ValidationError, "checkpoint_manifest_sha256"):
            self._prepare()

    def test_rejects_geometry_drift_before_emitting_paid_spec(self):
        value = preregistration()
        value["workload_geometry"]["requests"] = 7
        self.preregistration_path.write_text(json.dumps(value))

        with self.assertRaisesRegex(ValidationError, "workload_geometry"):
            self._prepare()

    def test_rejects_startup_isolation_drift_before_emitting_paid_spec(self):
        value = preregistration()
        value["operational_startup_isolation"]["requests"] = 1
        self.preregistration_path.write_text(json.dumps(value))

        with self.assertRaisesRegex(ValidationError, "operational_startup_isolation"):
            self._prepare()


if __name__ == "__main__":
    unittest.main()
