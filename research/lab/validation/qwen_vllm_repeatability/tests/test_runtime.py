import unittest

from validation.qwen_vllm_repeatability.runtime import estimate_runtime


class RuntimeTests(unittest.TestCase):
    def test_estimate_exposes_exact_component_arithmetic(self) -> None:
        estimate = estimate_runtime(
            durations_by_concurrency={1: 16.0, 2: 14.0, 4: 10.0, 8: 8.0},
            repeats=5,
            startup_seconds=6.0,
            cooldown_seconds=15,
            per_pair_overhead_seconds=2.0,
            per_run_client_setup_seconds=1.0,
        )

        self.assertEqual(estimate.measured_burst_seconds, 480.0)
        self.assertEqual(estimate.client_setup_seconds, 40.0)
        self.assertEqual(estimate.server_startup_seconds, 120.0)
        self.assertEqual(estimate.cooldown_seconds, 300.0)
        self.assertEqual(estimate.overhead_seconds, 40.0)
        self.assertEqual(estimate.total_seconds, 980.0)


if __name__ == "__main__":
    unittest.main()
