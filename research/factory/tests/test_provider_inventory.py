from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from grad_research.provider_inventory import ProviderInventoryError, load_provider_inventory
from grad_research.gcore_inventory import load_cached_gcore_inventory, load_or_refresh_gcore_inventory
from grad_research.runpod_inventory import load_runpod_inventory


INVENTORY = Path(__file__).parents[1] / "data" / "providers.json"


class ProviderInventoryTests(unittest.TestCase):
    def test_inventory_names_initial_profiling_providers_without_secrets(self) -> None:
        with patch.dict("os.environ", {"RUNPOD_API_KEY": "test-only"}, clear=True):
            report = load_provider_inventory(INVENTORY)

        self.assertEqual({"runpod", "scaleway", "gcore"}, set(report["providers"]))
        self.assertEqual("configured", report["providers"]["runpod"]["credential_status"])
        self.assertEqual("unverified", report["providers"]["scaleway"]["profiling"]["hardware_counters"])
        serialized = json.dumps(report)
        self.assertNotIn("Bearer ", serialized)
        self.assertNotIn("api_key_value", serialized)

    def test_inventory_rejects_credential_values(self) -> None:
        value = json.loads(INVENTORY.read_text())
        value["providers"][0]["credentials"][0]["value"] = "secret"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "providers.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ProviderInventoryError, "credential"):
                load_provider_inventory(path)

    def test_runpod_inventory_exposes_live_mi300x_as_default_amd_route(self) -> None:
        def fake_graphql(_: str) -> dict:
            return {
                "data": {
                    "gpuTypes": [
                        {
                            "id": "AMD Instinct MI300X OAM",
                            "displayName": "MI300X",
                            "memoryInGb": 192,
                            "s1": {
                                "stockStatus": "Low",
                                "uninterruptablePrice": 2.39,
                                "minimumBidPrice": 1.99,
                                "availableGpuCounts": None,
                            },
                            "s2": None,
                            "s4": None,
                            "s8": None,
                            "c1": None,
                        },
                        {
                            "id": "NVIDIA H100 80GB HBM3",
                            "displayName": "H100 SXM",
                            "memoryInGb": 80,
                            "s1": {
                                "stockStatus": "High",
                                "uninterruptablePrice": 2.99,
                                "minimumBidPrice": 2.99,
                                "availableGpuCounts": None,
                            },
                            "s2": {
                                "stockStatus": "High",
                                "uninterruptablePrice": 5.98,
                                "minimumBidPrice": 5.98,
                                "availableGpuCounts": None,
                            },
                            "s4": None,
                            "s8": None,
                            "c1": None,
                        },
                    ]
                }
            }

        report = load_runpod_inventory(
            "test-only-secret",
            now=datetime(2026, 7, 28, 14, 28, 24, tzinfo=timezone.utc),
            request_graphql=fake_graphql,
        )

        self.assertEqual("measured_authenticated_provider_api", report["evidence_type"])
        self.assertEqual("2026-07-28T14:28:24Z", report["retrieved_at_utc"])
        route = report["default_amd_experiment_route"]
        self.assertTrue(route["available"])
        self.assertEqual("AMD Instinct MI300X OAM", route["accelerator_id"])
        self.assertEqual("Low", route["stock_status"])
        self.assertEqual(2.39, route["on_demand_usd_per_gpu_hour"])
        self.assertEqual([1], route["available_secure_gpu_counts"])
        self.assertNotIn("test-only-secret", json.dumps(report))

    def test_gcore_markdown_snapshot_refreshes_once_per_day(self) -> None:
        class FakeGcore:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def __call__(self, method: str, url: str, payload: dict | None = None) -> dict:
                self.calls.append((method, url))
                if url.endswith("/cloud/v1/ai/regions"):
                    return {"regions": [{"id": 14, "display_name": "Manassas", "has_baremetal": True}]}
                if "/flavors?" in url:
                    return {
                        "flavors": [
                            {
                                "flavor_id": "g2-l40s-1",
                                "flavor_name": "L40S",
                                "capacity": 3,
                                "disabled": False,
                                "price_per_hour": 1.25,
                                "price_per_month": 900,
                                "hardware_description": "1x NVIDIA L40S",
                            }
                        ]
                    }
                if url.endswith("/images"):
                    return {"images": [{"id": "img-1", "name": "Ubuntu", "status": "active"}]}
                if "/clusters?" in url:
                    return {"clusters": []}
                if url.endswith("/check_limits"):
                    return {"allowed": True, "available": 3}
                raise AssertionError(f"unexpected Gcore request: {method} {url}")

        fake = FakeGcore()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GCORE.md"
            path.write_text("# Guide\n\n<!-- gcore-inventory-start -->\nold\n<!-- gcore-inventory-end -->\n")
            first = load_or_refresh_gcore_inventory(
                path,
                api_key="test-api-key",
                project_id="123",
                now=datetime(2026, 7, 16, tzinfo=timezone.utc),
                request_json=fake,
            )
            self.assertTrue(first["refreshed"])
            self.assertTrue(first["fresh"])
            self.assertIn("L40S", path.read_text())
            self.assertIn("# Guide", path.read_text())
            self.assertEqual(first["retrieved_at_utc"], load_cached_gcore_inventory(path)["retrieved_at_utc"])
            calls_after_first = len(fake.calls)

            second = load_or_refresh_gcore_inventory(
                path,
                api_key="test-api-key",
                project_id="123",
                now=datetime(2026, 7, 16, 12, tzinfo=timezone.utc),
                request_json=fake,
            )
            self.assertFalse(second["refreshed"])
            self.assertEqual(calls_after_first, len(fake.calls))

            third = load_or_refresh_gcore_inventory(
                path,
                api_key="test-api-key",
                project_id="123",
                now=datetime(2026, 7, 17, 2, tzinfo=timezone.utc),
                request_json=fake,
            )
            self.assertTrue(third["refreshed"])
            self.assertGreater(len(fake.calls), calls_after_first)


if __name__ == "__main__":
    unittest.main()
