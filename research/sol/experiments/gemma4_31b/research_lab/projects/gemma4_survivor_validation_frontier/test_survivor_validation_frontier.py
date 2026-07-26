import importlib.util
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "survivor_frontier", PROJECT_DIR / "run_survivor_validation_frontier.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SurvivorValidationFrontierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frontier = MODULE.build_frontier()

    def test_selects_exactly_one_finite_lifecycle(self):
        lifecycle = self.frontier["recommended_next_lifecycle"]
        self.assertEqual(
            lifecycle["lifecycle_id"],
            "mi355x_exact_shape_compile_and_component_falsifier",
        )
        self.assertGreater(
            lifecycle["resource_envelope"]["provider_spend_usd_max"], 0
        )
        self.assertIsNone(self.frontier["offline_prerequisite"])

    def test_keeps_survivor_classes_disjoint_and_unstacked(self):
        direct = {
            row["survivor"] for row in self.frontier["direct_placement_ledger"]
        }
        model = {
            row["survivor"]
            for row in self.frontier["model_runtime_change_ledger"]
        }
        self.assertFalse(direct & model)
        self.assertTrue(self.frontier["accounting_rules"]["stacked_gains_forbidden"])
        self.assertTrue(
            all(
                not row["own_price_normalized_accounting"]["stacked_gain_credit"]
                for row in self.frontier["direct_placement_ledger"]
            )
        )
        self.assertTrue(
            all(
                not row["target_accounting"]["stacked_gain_credit"]
                for row in self.frontier["model_runtime_change_ledger"]
            )
        )

    def test_verifies_all_bound_artifacts_and_excludes_trainium2(self):
        bindings = self.frontier["binding_verification"]["artifacts"]
        self.assertEqual(len(bindings), 9)
        self.assertTrue(all(row["verified"] for row in bindings.values()))
        self.assertFalse(
            self.frontier["excluded_evidence"]["trainium2"]["ranking_eligible"]
        )

    def test_turn_is_zero_spend_and_offline(self):
        use = self.frontier["resource_use_this_turn"]
        self.assertEqual(use["actual_spend_usd"], 0.0)
        self.assertFalse(use["provider_contacted"])
        self.assertFalse(use["provider_resources_created"])
        self.assertFalse(use["gpu_or_accelerator_claimed"])
        self.assertFalse(use["checkpoint_downloaded"])
        self.assertFalse(use["prices_browsed"])
        self.assertFalse(use["benchmarks_rerun"])


if __name__ == "__main__":
    unittest.main()
