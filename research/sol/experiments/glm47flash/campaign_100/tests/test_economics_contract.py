import hashlib
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


SPECS = Path(__file__).resolve().parents[1] / "specs"
sys.path.insert(0, str(SPECS))

from validate_contracts import ContractError, admit_budget, calculate_economics, validate_watchdog


class EconomicsTests(unittest.TestCase):
    def test_conservative_cost_and_token_costs(self):
        result = calculate_economics(
            hourly_price_usd="2.99",
            allocation_seconds=600,
            provider_reported_cost_usd="0.49",
            input_tokens=800000,
            output_tokens=200000,
            slo_input_tokens=720000,
            slo_output_tokens=180000,
            input_token_weight="0.25",
            non_gpu_sensitivity_fraction="0.20",
        )
        self.assertEqual(result["gpu_cost_usd"], "0.4983333333333333333333333333")
        self.assertEqual(result["gpu_usd_per_million_input_tokens"], "0.6229166666666666666666666666")
        self.assertEqual(result["gpu_usd_per_million_output_tokens"], "2.491666666666666666666666666")
        self.assertEqual(result["gpu_usd_per_million_blended_tokens"], "0.4983333333333333333333333333")
        self.assertEqual(result["gpu_usd_per_million_output_equivalent_tokens"], "1.245833333333333333333333333")
        self.assertEqual(result["slo_gpu_usd_per_million_blended_tokens"], "0.5537037037037037037037037037")
        self.assertEqual(result["sensitivity_reserved_usd"], "0.09966666666666666666666666666")

    def test_zero_denominator_fails(self):
        with self.assertRaises(ContractError):
            calculate_economics("1", 1, "0", 0, 1, 0, 1, "0.25", "0.1")

    def test_negative_inputs_fail(self):
        with self.assertRaises(ContractError):
            calculate_economics("-1", 1, "0", 1, 1, 1, 1, "0.25", "0.1")


class BudgetAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "baseline.json"
        self.baseline.write_text(json.dumps({
            "schema_version": 1,
            "signed_off": True,
            "campaign_additional_spend_usd": 0.0,
            "campaign_cap_usd": 100.0,
            "reconciliation_status": "authoritative",
        }, sort_keys=True))
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps({
            "schema_version": 1,
            "active_campaign_pods": [],
        }, sort_keys=True))
        self.watchdog = self.root / "watchdog.json"
        self.watchdog.write_text(json.dumps({
            "schema_version": "1.0.0",
            "independent_process": True,
            "absolute_deadline_utc": "2026-07-13T00:15:00Z",
            "maximum_deadline_seconds": 900,
            "delete_on_deadline": True,
            "delete_on_orchestrator_exit": True,
            "delete_if_harvest_fails": True,
            "verify_deleted_via_api": True,
            "poll_interval_seconds": 10,
            "watchdog_log_path": "watchdog.jsonl",
        }, sort_keys=True))
        self.request = {
            "schema_version": "1.0.0",
            "baseline_sha256": hashlib.sha256(self.baseline.read_bytes()).hexdigest(),
            "baseline_signed_off": True,
            "reconciliation_status": "conservative",
            "campaign_cap_usd": "100.00",
            "campaign_additional_spend_usd": "19.00",
            "phase": "B",
            "phase_cumulative_cap_usd": "20.00",
            "hourly_price_usd": "2.99",
            "maximum_deadline_seconds": 900,
            "recorded_maximum_deadline_cost_usd": "0.7475",
            "active_campaign_pod_count": 0,
            "inventory_snapshot_sha256": hashlib.sha256(self.inventory.read_bytes()).hexdigest(),
            "watchdog_contract_sha256": hashlib.sha256(self.watchdog.read_bytes()).hexdigest(),
        }

    def admit(self, request=None):
        return admit_budget(
            request or self.request,
            baseline_path=self.baseline,
            inventory_snapshot_path=self.inventory,
            watchdog_contract_path=self.watchdog,
        )

    def test_admits_at_or_below_both_caps(self):
        result = self.admit()
        self.assertEqual(result["decision"], "admit")
        self.assertEqual(result["projected_campaign_spend_usd"], "19.7475")

    def test_rejects_phase_overspend_even_below_campaign_cap(self):
        request = dict(self.request, campaign_additional_spend_usd="19.50")
        with self.assertRaises(ContractError):
            self.admit(request)

    def test_rejects_unsigned_or_uncertain_baseline(self):
        for changes in (
            {"baseline_signed_off": False},
            {"reconciliation_status": "uncertain"},
            {"baseline_sha256": ""},
        ):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                self.admit(dict(self.request, **changes))

    def test_rejects_rounding_down_recorded_max_cost(self):
        with self.assertRaises(ContractError):
            self.admit(dict(self.request, recorded_maximum_deadline_cost_usd="0.74"))

    def test_rejects_existing_active_campaign_pod(self):
        with self.assertRaises(ContractError):
            self.admit(dict(self.request, active_campaign_pod_count=1))

    def test_rejects_phase_cap_that_does_not_match_plan(self):
        with self.assertRaises(ContractError):
            self.admit(dict(self.request, phase_cumulative_cap_usd="100.00"))

    def test_rejects_missing_dereferenced_identity_files(self):
        with self.assertRaises(ContractError):
            admit_budget(self.request)

    def test_rejects_tampered_baseline_inventory_and_watchdog_identities(self):
        targets = [self.baseline, self.inventory, self.watchdog]
        originals = {path: path.read_bytes() for path in targets}
        for target in targets:
            with self.subTest(target=target.name):
                target.write_bytes(originals[target] + b"\n")
                with self.assertRaises(ContractError):
                    self.admit()
                target.write_bytes(originals[target])

    def test_rejects_identity_content_that_disagrees_with_admission(self):
        baseline = json.loads(self.baseline.read_text())
        baseline["signed_off"] = False
        self.baseline.write_text(json.dumps(baseline, sort_keys=True))
        request = dict(
            self.request,
            baseline_sha256=hashlib.sha256(self.baseline.read_bytes()).hexdigest(),
        )
        with self.assertRaises(ContractError):
            self.admit(request)

    def test_rejects_bound_inventory_or_watchdog_that_disagrees(self):
        inventory = json.loads(self.inventory.read_text())
        inventory["active_campaign_pods"] = [{"id": "pod-1"}]
        self.inventory.write_text(json.dumps(inventory, sort_keys=True))
        request = dict(
            self.request,
            inventory_snapshot_sha256=hashlib.sha256(self.inventory.read_bytes()).hexdigest(),
        )
        with self.assertRaises(ContractError):
            self.admit(request)

        self.inventory.write_text(json.dumps({
            "schema_version": 1,
            "active_campaign_pods": [],
        }, sort_keys=True))
        watchdog = json.loads(self.watchdog.read_text())
        watchdog["maximum_deadline_seconds"] = 800
        self.watchdog.write_text(json.dumps(watchdog, sort_keys=True))
        request = dict(
            self.request,
            inventory_snapshot_sha256=hashlib.sha256(self.inventory.read_bytes()).hexdigest(),
            watchdog_contract_sha256=hashlib.sha256(self.watchdog.read_bytes()).hexdigest(),
        )
        with self.assertRaises(ContractError):
            self.admit(request)


class WatchdogContractTests(unittest.TestCase):
    def test_valid_watchdog_contract(self):
        validate_watchdog({
            "schema_version": "1.0.0",
            "independent_process": True,
            "absolute_deadline_utc": "2026-07-13T00:15:00Z",
            "maximum_deadline_seconds": 900,
            "delete_on_deadline": True,
            "delete_on_orchestrator_exit": True,
            "delete_if_harvest_fails": True,
            "verify_deleted_via_api": True,
            "poll_interval_seconds": 10,
            "watchdog_log_path": "watchdog.jsonl",
        })

    def test_missing_cleanup_guarantee_fails(self):
        with self.assertRaises(ContractError):
            validate_watchdog({
                "schema_version": "1.0.0",
                "independent_process": True,
                "absolute_deadline_utc": "2026-07-13T00:15:00Z",
                "maximum_deadline_seconds": 900,
                "delete_on_deadline": True,
                "delete_on_orchestrator_exit": True,
                "delete_if_harvest_fails": False,
                "verify_deleted_via_api": True,
                "poll_interval_seconds": 10,
                "watchdog_log_path": "watchdog.jsonl",
            })


if __name__ == "__main__":
    unittest.main()
