from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from grad_research.gpu_prices import PriceInventoryError, load_gpu_price_inventory


INVENTORY = Path(__file__).parents[1] / "data" / "gpu_prices.json"


class GpuPriceInventoryTests(unittest.TestCase):
    def inventory_refreshed_at(self) -> datetime:
        value = json.loads(INVENTORY.read_text())
        return datetime.fromisoformat(value["refreshed_at_utc"].replace("Z", "+00:00"))

    def test_shared_inventory_is_fresh_and_uses_committed_production_rates(self) -> None:
        report = load_gpu_price_inventory(
            INVENTORY,
            now=self.inventory_refreshed_at() + timedelta(days=6),
        )

        self.assertTrue(report["fresh"])
        self.assertEqual(report["refresh_interval_days"], 7)
        self.assertEqual(report["production_pricing_policy"]["term_months"], [12, 24])
        self.assertEqual(report["production_pricing_policy"]["capacity_type"], "committed_non_preemptible")
        self.assertEqual(report["accelerators"]["amd-mi355x"]["production_planning_usd_per_gpu_hour"], 2.6)
        self.assertEqual(report["accelerators"]["nvidia-h200-sxm"]["production_planning_usd_per_gpu_hour"], 3.25)

    def test_inventory_becomes_stale_after_weekly_window(self) -> None:
        report = load_gpu_price_inventory(
            INVENTORY,
            now=self.inventory_refreshed_at() + timedelta(days=8),
        )

        self.assertFalse(report["fresh"])
        self.assertGreater(report["age_days"], 7)

    def test_planning_rate_must_be_inside_evidence_range(self) -> None:
        value = json.loads(INVENTORY.read_text())
        value["accelerators"][0]["production_planning_usd_per_gpu_hour"] = 99
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gpu_prices.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(PriceInventoryError, "production planning rate"):
                load_gpu_price_inventory(path, now=datetime(2026, 7, 20, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
