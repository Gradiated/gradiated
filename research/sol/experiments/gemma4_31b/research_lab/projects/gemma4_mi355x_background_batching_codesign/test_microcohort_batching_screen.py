import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

import run_microcohort_batching_screen as screen
import run_rolling_batching_screen as physical
from phase_aligned_microcohort_policy import (
    COHORT_SIZE,
    PhaseAlignedMicrocohortPolicy,
)


class MicrocohortPolicyTests(unittest.TestCase):
    def test_only_full_cohort_admits_before_stream_close(self) -> None:
        policy = PhaseAlignedMicrocohortPolicy()
        waiting = physical.make_requests(COHORT_SIZE - 1, 0.0)
        self.assertIsNone(
            policy.form_ready_cohort(
                waiting, 0, arrival_stream_closed=False
            )
        )
        self.assertEqual(len(waiting), COHORT_SIZE - 1)
        cohort = policy.form_ready_cohort(
            waiting, 0, arrival_stream_closed=True
        )
        self.assertIsNotNone(cohort)
        assert cohort is not None
        self.assertTrue(cohort.terminal_partial_fallback)

    def test_mixed_cache_prefill_completes_together(self) -> None:
        policy = PhaseAlignedMicrocohortPolicy()
        waiting = physical.make_requests(840, 0.0)[814:830]
        cohorts = []
        while not cohorts or cohorts[0].is_prefill:
            rows, admitted = policy.schedule(
                waiting, cohorts, arrival_stream_closed=True
            )
            self.assertEqual(len(rows), COHORT_SIZE)
            if admitted:
                self.assertEqual(len(admitted), 1)
            for row in rows:
                row.request.fresh_computed += row.tokens
        cohort = cohorts[0]
        self.assertEqual(
            {request.fresh_computed for request in cohort.requests},
            {3678, 3679},
        )
        self.assertEqual({request.output_tokens for request in cohort.requests}, {0})

    def test_finite_stream_preserves_work_and_terminal_fallback(self) -> None:
        requests = physical.make_requests(24, 0.01)
        result = screen.simulate(requests)
        accounting = result["accounting"]
        self.assertTrue(result["all_requests_completed"])
        self.assertEqual(int(accounting["fallback_requests"]), 8)
        self.assertEqual(
            int(accounting["prefill_tokens"]),
            sum(request.fresh_prompt_tokens for request in requests),
        )
        self.assertEqual(
            int(accounting["decode_rows"] + accounting["prefill_head_rows"]),
            24 * physical.OUTPUT_TOKENS,
        )
        self.assertEqual(
            int(accounting["target_cycles"]),
            24 * physical.TARGET_CYCLES,
        )
        self.assertGreater(result["alignment_checks"], 0)

    def test_fixed_policy_contract(self) -> None:
        policy = PhaseAlignedMicrocohortPolicy()
        self.assertEqual(policy.cohort_size, 16)
        self.assertEqual(policy.max_live_sequences, 96)
        self.assertEqual(policy.prefill_token_budget, 8192)
        self.assertEqual(screen.OFFERED_CAPACITY_FRACTION, 0.90)


if __name__ == "__main__":
    unittest.main()
