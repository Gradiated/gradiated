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

from orchestrator import ProviderNotFound
from runpod_graphql_placement_control import (
    PlacementControlError,
    build_placement_request,
    run_control,
)


def preregistration():
    return {
        "experiment_id": "phase-b-stock-h100-sxm-secure-ap-in-v5",
        "provider_request": {
            "cloud_class": "SECURE",
            "gpu_type_id": "NVIDIA H100 80GB HBM3",
            "gpu_count": 1,
            "data_center_ids": ["AP-IN-1"],
            "allowed_cuda_versions": ["13.0"],
            "interruptible": False,
            "admission_hourly_price_ceiling_usd": 2.99,
        },
        "placement_control_watchdog": {
            "independent_process": True,
            "maximum_deadline_seconds": 300,
            "watchdog_log_path": "allocations/phase_b_stock_h100_sxm_secure_ap_in_v5/placement-control-watchdog.jsonl",
            "watchdog_cancel_path": "allocations/phase_b_stock_h100_sxm_secure_ap_in_v5/placement-control-watchdog.cancel",
        },
    }


class FakeClock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class FakeProvider:
    def __init__(self, fail_get=False, events=None, never_404=False, hourly_rate=2.99):
        self.calls = []
        self.events = events
        self.fail_get = fail_get
        self.never_404 = never_404
        self.hourly_rate = hourly_rate
        self.deleted = False

    def create(self, request):
        self.calls.append(("create", request))
        if self.events is not None:
            self.events.append("create")
        return {
            "id": "pod-control-1",
            "costPerHr": self.hourly_rate,
            "createdAt": "2026-07-13T15:00:00Z",
            "desiredStatus": "RUNNING",
            "machineId": "machine-1",
            "imageName": "runpod/pytorch",
        }

    def get(self, pod_id):
        self.calls.append(("get", pod_id))
        if self.events is not None:
            self.events.append("get")
        if self.deleted and not self.never_404:
            raise ProviderNotFound(pod_id)
        if self.fail_get:
            raise RuntimeError("reflected credential-must-not-leak")
        return {"id": pod_id, "desiredStatus": "RUNNING", "machineId": "machine-1"}

    def delete(self, pod_id):
        self.calls.append(("delete", pod_id))
        if self.events is not None:
            self.events.append("delete")
        self.deleted = True
        return 204


class FakeWatchdog:
    def __init__(self, contract, events):
        self.contract = contract
        self.events = events

    def start(self, pod_id):
        self.events.append("watchdog_start")

    def cancel(self):
        self.events.append("watchdog_cancel")


class GraphqlPlacementControlTests(unittest.TestCase):
    def test_builds_deterministic_isolated_h100_request(self):
        request = build_placement_request(preregistration())

        self.assertEqual(request["api_surface"], "graphql_podFindAndDeployOnDemand")
        graphql_input = request["variables"]["input"]
        self.assertEqual(graphql_input, {
            "cloudType": "SECURE",
            "computeType": "GPU",
            "gpuCount": 1,
            "gpuTypeId": "NVIDIA H100 80GB HBM3",
            "dataCenterId": "AP-IN-1",
            "allowedCudaVersions": ["13.0"],
            "containerDiskInGb": 20,
            "volumeInGb": 20,
            "imageName": "runpod/pytorch",
            "name": "glm47flash-h100-ap-in-placement-control",
        })
        for forbidden in ("env", "dockerArgs", "ports", "RUNPOD_API_KEY"):
            self.assertNotIn(forbidden, json.dumps(graphql_input))

    def test_rejects_any_drift_from_exact_placement_contract(self):
        for field, value in (
            ("cloud_class", "COMMUNITY"),
            ("gpu_type_id", "NVIDIA A100-SXM4-80GB"),
            ("data_center_ids", ["US-KS-2"]),
            ("allowed_cuda_versions", ["12.8"]),
            ("interruptible", True),
        ):
            contract = preregistration()
            contract["provider_request"][field] = value
            with self.subTest(field=field), self.assertRaises(PlacementControlError):
                build_placement_request(contract)

    def test_requires_coordinator_before_provider_access(self):
        provider = FakeProvider()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(PlacementControlError, "coordinator"):
                run_control(
                    preregistration(),
                    Path(directory) / "result.json",
                    provider=provider,
                    monotonic=FakeClock([10.0]),
                    sleep=lambda _seconds: None,
                )
        self.assertEqual(provider.calls, [])

    def test_records_state_deletes_immediately_verifies_404_and_computes_exposure(self):
        events = []
        provider = FakeProvider(events=events)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CAMPAIGN_100_COORDINATOR": "1"}
        ):
            output = Path(directory) / "result.json"
            result = run_control(
                preregistration(),
                output,
                provider=provider,
                watchdog_factory=lambda contract: FakeWatchdog(contract, events),
                monotonic=FakeClock([10.0, 12.0]),
                sleep=lambda _seconds: None,
            )
            persisted = json.loads(output.read_text())

        self.assertEqual([call[0] for call in provider.calls], ["create", "get", "delete", "get"])
        self.assertEqual(
            events,
            ["create", "watchdog_start", "get", "delete", "get", "watchdog_cancel"],
        )
        self.assertEqual(result["teardown_verification"], "http_404")
        self.assertEqual(result["delete_http_status"], 204)
        self.assertEqual(result["allocation_seconds"], 2.0)
        self.assertAlmostEqual(result["conservative_allocation_exposure_usd"], 2.99 * 2 / 3600)
        self.assertEqual(result["provider_state"]["desiredStatus"], "RUNNING")
        self.assertEqual(persisted, result)

    def test_failure_after_creation_still_deletes_and_records_only_hashed_error(self):
        provider = FakeProvider(fail_get=True)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CAMPAIGN_100_COORDINATOR": "1"}
        ):
            output = Path(directory) / "result.json"
            result = run_control(
                preregistration(),
                output,
                provider=provider,
                watchdog_factory=lambda contract: FakeWatchdog(contract, []),
                monotonic=FakeClock([10.0, 13.0]),
                sleep=lambda _seconds: None,
            )

            serialized = output.read_text()
        self.assertIn("delete", [call[0] for call in provider.calls])
        self.assertEqual(result["error"]["type"], "RuntimeError")
        self.assertEqual(
            result["error"]["sha256"],
            hashlib.sha256(b"RuntimeError:reflected credential-must-not-leak").hexdigest(),
        )
        self.assertNotIn("credential-must-not-leak", serialized)

    def test_watchdog_is_not_cancelled_before_verified_404(self):
        events = []
        provider = FakeProvider(events=events, never_404=True)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CAMPAIGN_100_COORDINATOR": "1"}
        ):
            result = run_control(
                preregistration(),
                Path(directory) / "result.json",
                provider=provider,
                watchdog_factory=lambda contract: FakeWatchdog(contract, events),
                monotonic=FakeClock([10.0, 13.0]),
                sleep=lambda _seconds: None,
            )

        self.assertIn("watchdog_start", events)
        self.assertNotIn("watchdog_cancel", events)
        self.assertEqual(result["teardown_verification"], "pending")
        self.assertFalse(result["watchdog"]["cancelled_after_404"])

    def test_over_ceiling_create_is_deleted_and_verified_before_any_state_get(self):
        events = []
        provider = FakeProvider(events=events, hourly_rate=3.00)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CAMPAIGN_100_COORDINATOR": "1"}
        ):
            result = run_control(
                preregistration(),
                Path(directory) / "result.json",
                provider=provider,
                watchdog_factory=lambda contract: FakeWatchdog(contract, events),
                monotonic=FakeClock([10.0, 11.0]),
                sleep=lambda _seconds: None,
            )

        self.assertEqual(
            events,
            ["create", "watchdog_start", "delete", "get", "watchdog_cancel"],
        )
        self.assertEqual(result["teardown_verification"], "http_404")
        self.assertEqual(result["delete_http_status"], 204)
        self.assertEqual(result["error"]["type"], "PlacementControlError")
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
