from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import simulate_placements


class PlacementSimulationTest(unittest.TestCase):
    def test_exact_combinatorics(self) -> None:
        self.assertEqual(simulate_placements.tree_mask_true_elements(12), 38)
        self.assertEqual(simulate_placements.causal_pairs(4214, None), 8_881_005)
        self.assertEqual(simulate_placements.causal_pairs(4214, 1024), 3_791_360)

    def test_bound_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            simulate_placements.main(output)
            result = json.loads(output.read_text())

        self.assertTrue(all(row["match"] for row in result["bindings"].values()))
        selected = next(
            row
            for row in result["placements"]
            if row["name"] == "half_global_keep_early_in_each_pair"
        )
        self.assertEqual(selected["full_layer_indices"], [5, 17, 29, 41, 53])
        self.assertEqual(selected["local_layers"], 55)
        self.assertEqual(selected["global_layers"], 5)
        self.assertEqual(selected["kv_residency"]["bytes_saved_vs_baseline"], 1_419_509_760)
        self.assertAlmostEqual(
            selected["target_verification"]["savings_ms_per_cycle_vs_tuned_50_10"],
            12.053362723312375,
        )
        self.assertGreater(
            min(
                selected["predicted_whole_request"]["reduction_fraction_range"]
            ),
            0.05,
        )
        self.assertFalse(result["decision"]["campaign_objective_met"])


if __name__ == "__main__":
    unittest.main()
