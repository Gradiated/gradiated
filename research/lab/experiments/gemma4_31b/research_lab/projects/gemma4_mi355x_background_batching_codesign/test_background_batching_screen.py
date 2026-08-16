import importlib.util
import json
import math
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "background_screen", PROJECT_DIR / "run_background_batching_screen.py"
)
assert SPEC is not None and SPEC.loader is not None
SCREEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCREEN)


class BackgroundBatchingScreenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        parent = json.loads(SCREEN.PARENT_SCREEN.read_text())
        cls.rows = {
            row["name"]: row
            for row in parent["physical_cost_screen"]["line_items"]
        }

    def test_c32_reproduces_parent_and_only_c96_passes(self) -> None:
        parent = json.loads(SCREEN.PARENT_SCREEN.read_text())
        c32 = SCREEN.width_screen(32, self.rows)
        c64 = SCREEN.width_screen(64, self.rows)
        c96 = SCREEN.width_screen(96, self.rows)
        self.assertTrue(
            math.isclose(
                c32["full_width_service_seconds_per_request"],
                parent["physical_cost_screen"][
                    "conservative_screen_seconds_per_request"
                ],
                rel_tol=0,
                abs_tol=1e-15,
            )
        )
        self.assertFalse(c64["pass_economic_service_gate"])
        self.assertTrue(c96["pass_economic_service_gate"])

    def test_timeout_policy_preserves_work_and_fails_queue_gate(self) -> None:
        service = {
            width: SCREEN.width_screen(width, self.rows)[
                "full_width_service_seconds_per_request"
            ]
            for width in (32, 96)
        }
        result = SCREEN.simulate_timeout_policy(
            service,
            offered_requests_per_second=2.0,
            cohorts=3_000,
            burn_cohorts=300,
        )
        self.assertTrue(result["all_requests_and_tokens_preserved"])
        self.assertFalse(result["queue_p95_gate_pass"])
        self.assertTrue(result["completion_p95_gate_pass"])
        self.assertGreater(result["fallback_request_fraction"], 0)

    def test_fill_rate_required_by_queue_gate_exceeds_capacity(self) -> None:
        c96 = SCREEN.width_screen(96, self.rows)
        capacity = 1 / c96["full_width_service_seconds_per_request"]
        required = (
            SCREEN.SELECTED_WIDTH - SCREEN.COHORT_WIDTH
        ) / SCREEN.QUEUE_P95_GATE_SECONDS
        self.assertGreater(required, capacity)


if __name__ == "__main__":
    unittest.main()
