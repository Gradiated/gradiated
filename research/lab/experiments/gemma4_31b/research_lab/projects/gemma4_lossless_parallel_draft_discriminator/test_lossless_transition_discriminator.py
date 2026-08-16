#!/usr/bin/env python3

import unittest

from lossless_transition_discriminator import (
    build_result,
    evaluate_transition,
)


class TransitionTest(unittest.TestCase):
    def test_matching_multi_token_transition(self) -> None:
        result = evaluate_transition(
            pending_seed=10,
            proposal_tokens=[11, 12, 99],
            verifier_top1=[11, 12, 13, 14],
            ordinary_tokens=[11, 12, 13, 14],
            committed_length_before=20,
            kv_write_locations=[100, 101, 102, 103],
        )
        self.assertTrue(result["exact_transition"])
        self.assertEqual(result["accepted_draft_count"], 2)
        self.assertEqual(result["emitted_tokens"], [11, 12, 13])
        self.assertEqual(result["committed_kv_write_locations"], [100, 101, 102])
        self.assertEqual(result["committed_length_after"], 23)
        self.assertEqual(result["next_pending_seed"], 13)

    def test_fail_closed_reconstructs_ordinary_one_step(self) -> None:
        result = evaluate_transition(
            pending_seed=236814,
            proposal_tokens=[174501, 74443, 104105],
            verifier_top1=[759, 236814, 236761, 87096],
            ordinary_tokens=[3496, 3496, 3496, 3496],
            committed_length_before=4214,
            kv_write_locations=[71603],
        )
        self.assertFalse(result["exact_transition"])
        self.assertEqual(result["first_verifier_difference_index"], 0)
        self.assertEqual(
            result["fail_closed_correction"],
            {
                "action": "discard_speculative_only_writes_and_use_ordinary_target",
                "accepted_draft_count": 0,
                "emitted_tokens": [3496],
                "commit_length": 1,
                "committed_kv_write_locations": [71603],
                "committed_length_after": 4215,
                "next_pending_seed": 3496,
                "exact_against_ordinary_one_step": True,
            },
        )

    def test_bound_capture_and_hurdle(self) -> None:
        result = build_result()
        self.assertEqual(
            result["classification"],
            "localized_first_target_token_divergence_with_exact_fail_closed_correction",
        )
        transition = result["request_25"]["transition"]
        self.assertEqual(transition["bonus_token"], 759)
        self.assertEqual(
            transition["fail_closed_correction"]["next_pending_seed"], 3496
        )
        hurdle = result["economic_hurdle"]
        self.assertEqual(
            hurdle["optimistic_zero_draft_cost"]["minimum_integer_draft_depth"], 13
        )
        self.assertFalse(
            hurdle["measured_current_dflash"]["passes_accepted_depth_hurdle"]
        )
        self.assertFalse(
            hurdle["measured_current_dflash"]["passes_verification_cost_hurdle"]
        )


if __name__ == "__main__":
    unittest.main()
