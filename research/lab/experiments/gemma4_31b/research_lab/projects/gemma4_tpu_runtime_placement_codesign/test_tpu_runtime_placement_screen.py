import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("run_tpu_runtime_placement_screen.py")
SPEC = importlib.util.spec_from_file_location("tpu_runtime_placement_screen", MODULE_PATH)
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


class PlacementScreenTest(unittest.TestCase):
    def test_exact_capacity_and_one_year_hurdle(self):
        result = screen.build_screen("2026-07-26T12:45:00Z")

        self.assertEqual(result["decision"], "typed_none")
        self.assertEqual(
            result["typed_none"]["code"],
            "missing_scope_matched_target_tpu_performance_measurement",
        )
        self.assertEqual(
            result["capacity"]["c32_bf16_kv_cache_bytes"], 38_828_769_280
        )
        one_year = result["economics"]["slice_rate_scenarios"][
            "one_year_fleet_amortized"
        ]
        self.assertAlmostEqual(one_year["max_service_seconds_at_c32"], 2.976630496858937)
        self.assertAlmostEqual(
            one_year["required_total_tokens_per_second"], 49_150.877192982465
        )

    def test_adjacent_measurement_is_not_promoted(self):
        result = screen.build_screen("2026-07-26T12:45:00Z")

        sensitivity = result["non_qualifying_adjacent_measurement"]
        self.assertFalse(sensitivity["used_for_candidate"])
        self.assertGreater(
            sensitivity["planning_all_in_cost_usd_per_m_total_tokens"],
            result["economic_target_usd_per_m_total_tokens"],
        )


if __name__ == "__main__":
    unittest.main()
