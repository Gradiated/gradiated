import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN / "phase_b"))

from orchestrator import ControlError, PhaseBOrchestrator, ProviderNotFound


class FakeProvider:
    def __init__(self, harvest_error=False):
        self.calls = []
        self.pods = {}
        self.harvest_error = harvest_error

    def inventory(self):
        self.calls.append("inventory")
        return list(self.pods.values())

    def create(self, request):
        self.calls.append("create")
        self.pods["pod-1"] = {"id": "pod-1", "status": "RUNNING"}
        return dict(self.pods["pod-1"])

    def harvest(self, pod_id, destination):
        self.calls.append("harvest")
        if self.harvest_error:
            raise RuntimeError("harvest failed")
        Path(destination).mkdir(parents=True)
        return Path(destination)

    def delete(self, pod_id):
        self.calls.append("delete")
        self.pods.pop(pod_id, None)
        return 204

    def get(self, pod_id):
        self.calls.append("get")
        if pod_id not in self.pods:
            raise ProviderNotFound(pod_id)
        return self.pods[pod_id]


class FakeWatchdog:
    def __init__(self, events):
        self.events = events

    def start(self, pod_id):
        self.events.append("watchdog_start")

    def cancel(self):
        self.events.append("watchdog_cancel")


class PhaseBOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gate = self.root / "gate.json"
        self.gate.write_text('{"gate":"A","status":"passed"}\n')
        self.gate_hash = hashlib.sha256(self.gate.read_bytes()).hexdigest()
        self.baseline = self.root / "baseline.json"
        self.baseline.write_text(json.dumps({
            "schema_version": 1,
            "signed_off": True,
            "campaign_additional_spend_usd": 0.0,
            "campaign_cap_usd": 100.0,
            "reconciliation_status": "authoritative",
        }))
        self.watchdog_contract = {
            "schema_version": "1.0.0",
            "independent_process": True,
            "absolute_deadline_utc": "2026-07-13T12:15:00Z",
            "maximum_deadline_seconds": 900,
            "delete_on_deadline": True,
            "delete_on_orchestrator_exit": True,
            "delete_if_harvest_fails": True,
            "verify_deleted_via_api": True,
            "poll_interval_seconds": 10,
            "watchdog_log_path": "watchdog.jsonl",
        }
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps({
            "schema_version": 1,
            "active_campaign_pods": [],
        }))
        self.watchdog_path = self.root / "watchdog-contract.json"
        self.watchdog_path.write_text(json.dumps(self.watchdog_contract))
        self.admission = {
            "schema_version": "1.0.0",
            "baseline_sha256": hashlib.sha256(self.baseline.read_bytes()).hexdigest(),
            "baseline_signed_off": True,
            "reconciliation_status": "authoritative",
            "campaign_cap_usd": "100.00",
            "campaign_additional_spend_usd": "0.00",
            "phase": "B",
            "phase_cumulative_cap_usd": "20.00",
            "hourly_price_usd": "2.99",
            "maximum_deadline_seconds": 900,
            "recorded_maximum_deadline_cost_usd": "0.7475",
            "active_campaign_pod_count": 0,
            "inventory_snapshot_sha256": hashlib.sha256(self.inventory.read_bytes()).hexdigest(),
            "watchdog_contract_sha256": hashlib.sha256(self.watchdog_path.read_bytes()).hexdigest(),
        }

    def build(self, provider, events=None):
        return PhaseBOrchestrator(
            provider=provider,
            baseline_path=self.baseline,
            inventory_snapshot_path=self.inventory,
            watchdog_contract_path=self.watchdog_path,
            gate_a_manifest_path=self.gate,
            expected_gate_a_manifest_sha256=self.gate_hash,
            watchdog_factory=lambda _contract: FakeWatchdog(events if events is not None else []),
        )

    def test_requires_coordinator_invocation_before_provider_access(self):
        provider = FakeProvider()
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ControlError):
            self.build(provider).run({}, self.admission, self.watchdog_contract, self.root / "out")
        self.assertEqual(provider.calls, [])

    def test_rejects_unsigned_baseline_and_tampered_gate(self):
        provider = FakeProvider()
        with patch.dict(os.environ, {"CAMPAIGN_100_COORDINATOR": "1"}):
            self.baseline.write_text('{"signed_off":false}\n')
            with self.assertRaises(ControlError):
                self.build(provider).run({}, self.admission, self.watchdog_contract, self.root / "out")
        self.assertEqual(provider.calls, [])

    def test_success_queries_around_mutations_and_harvests_before_delete(self):
        provider = FakeProvider()
        events = []
        with patch.dict(os.environ, {"CAMPAIGN_100_COORDINATOR": "1"}):
            result = self.build(provider, events).run(
                {"name": "stock"}, self.admission, self.watchdog_contract, self.root / "out"
            )
        self.assertEqual(
            provider.calls,
            ["inventory", "create", "inventory", "harvest", "inventory", "delete", "inventory", "get"],
        )
        self.assertEqual(events, ["watchdog_start", "watchdog_cancel"])
        self.assertEqual(result["teardown_verification"], "http_404")

    def test_harvest_failure_still_deletes_and_verifies(self):
        provider = FakeProvider(harvest_error=True)
        with patch.dict(os.environ, {"CAMPAIGN_100_COORDINATOR": "1"}):
            result = self.build(provider).run(
                {"name": "stock"}, self.admission, self.watchdog_contract, self.root / "out"
            )
        self.assertLess(provider.calls.index("harvest"), provider.calls.index("delete"))
        self.assertIn("get", provider.calls)
        self.assertEqual(result["harvest_status"], "failed")
        self.assertEqual(result["teardown_verification"], "http_404")


if __name__ == "__main__":
    unittest.main()
