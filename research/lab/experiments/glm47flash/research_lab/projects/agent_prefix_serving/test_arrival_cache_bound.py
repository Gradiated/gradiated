import sys
import unittest

from pathlib import Path


PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from arrival_cache_bound import build_bound


class ArrivalCacheBoundTest(unittest.TestCase):
    def test_schedule_requires_two_hits_for_five_percent_and_measured_cases_miss(self):
        value = build_bound()
        self.assertEqual(value["inputs"]["within_session_gap_ms"], 100)
        self.assertEqual(value["inputs"]["potential_reuse_requests"], 16)
        self.assertEqual(value["inputs"]["minimum_hits_for_five_percent"], 2)
        cases = {row["case"]: row for row in value["cases"]}
        self.assertEqual(cases["optimistic_zero_intercept_scaled_c1"]["eligible_reuse_requests"], 16)
        self.assertEqual(cases["v21_c8_p95_scheduler_step_proxy"]["eligible_reuse_requests"], 16)
        self.assertEqual(cases["v21_c1_observed"]["eligible_reuse_requests"], 0)
        self.assertEqual(cases["v21_c8_p95_observed"]["eligible_reuse_requests"], 0)
        self.assertEqual(value["source_audit"]["source_commit"], "f176443446f659dbab5315e056e605d8984fd976")


if __name__ == "__main__":
    unittest.main()
