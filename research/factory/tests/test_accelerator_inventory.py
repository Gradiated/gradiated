from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from grad_research.accelerator_inventory import AcceleratorInventoryError, load_accelerator_inventory


INVENTORY = Path(__file__).parents[1] / "data" / "accelerator_inventory.json"


class AcceleratorInventoryTests(unittest.TestCase):
    def test_shared_inventory_covers_major_vendors_and_microarchitecture(self) -> None:
        report = load_accelerator_inventory(
            INVENTORY,
            now=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )

        self.assertTrue(report["current"])
        self.assertEqual(report["review_interval_days"], 7)
        self.assertGreaterEqual(len(report["accelerators"]), 37)
        self.assertEqual({"NVIDIA", "AMD", "Intel", "Google", "AWS"}, set(report["vendors"]))
        l40s = report["accelerators"]["nvidia-l40s"]
        self.assertEqual(l40s["execution"]["compute_units"], 142)
        self.assertEqual(l40s["memory"]["bandwidth_gb_s"], 864)
        self.assertEqual(l40s["cache"]["last_level_mb"], 96)
        self.assertEqual(l40s["architecture_profile"]["local_memory_per_unit_kib"], 100)
        self.assertEqual(l40s["price_inventory_id"], "nvidia-l40s")
        self.assertEqual(report["accelerators"]["amd-mi355x"]["memory"]["capacity_gb"], 288)
        self.assertEqual(report["accelerators"]["nvidia-b300-sxm"]["memory"]["capacity_gb"], 288)
        self.assertEqual(report["accelerators"]["nvidia-gh200-hbm3e"]["memory"]["cpu_memory_gb"], 480)
        self.assertEqual(report["accelerators"]["amd-mi300a"]["execution"]["cpu_cores"], 24)
        self.assertEqual(report["accelerators"]["nvidia-rubin"]["memory"]["bandwidth_gb_s"], 22000)
        self.assertEqual(report["accelerators"]["amd-mi455x"]["memory"]["capacity_gb"], 432)
        self.assertEqual(report["accelerators"]["google-tpu7x"]["execution"]["sparse_cores"], 4)
        self.assertEqual(report["accelerators"]["aws-trainium3"]["memory"]["capacity_gb"], 144)

    def test_filters_select_candidate_hardware(self) -> None:
        report = load_accelerator_inventory(
            INVENTORY,
            now=datetime(2026, 8, 1, tzinfo=timezone.utc),
            vendor="AMD",
            min_memory_gb=250,
            required_format="fp4",
        )

        self.assertEqual(set(report["accelerators"]), {"amd-mi350x", "amd-mi355x"})

    def test_unknown_source_and_profile_fail_closed(self) -> None:
        value = json.loads(INVENTORY.read_text())
        value["accelerators"][0]["source_ids"] = ["missing"]
        value["accelerators"][1]["architecture_profile_id"] = "missing"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accelerators.json"
            path.write_text(json.dumps(value))
            with self.assertRaises(AcceleratorInventoryError):
                load_accelerator_inventory(path, now=datetime(2026, 8, 1, tzinfo=timezone.utc))

    def test_inventory_becomes_stale_after_weekly_window(self) -> None:
        value = json.loads(INVENTORY.read_text())
        reviewed_at = datetime.fromisoformat(value["reviewed_at_utc"].replace("Z", "+00:00"))
        report = load_accelerator_inventory(INVENTORY, now=reviewed_at.replace(tzinfo=timezone.utc))
        self.assertTrue(report["current"])

        report = load_accelerator_inventory(
            INVENTORY,
            now=reviewed_at.replace(tzinfo=timezone.utc) + timedelta(days=8),
        )
        self.assertFalse(report["current"])


if __name__ == "__main__":
    unittest.main()
