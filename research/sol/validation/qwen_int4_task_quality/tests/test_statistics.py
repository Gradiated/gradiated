import unittest

from validation.qwen_int4_task_quality.statistics import (
    exact_two_sided_mcnemar_p,
    paired_outcomes,
)


class PairedStatisticsTests(unittest.TestCase):
    def test_paired_outcomes_distinguish_candidate_wins_and_losses(self) -> None:
        baseline = [True, True, False, False, True]
        candidate = [True, False, True, False, True]

        outcomes = paired_outcomes(baseline, candidate)

        self.assertEqual(outcomes.both_correct, 2)
        self.assertEqual(outcomes.both_wrong, 1)
        self.assertEqual(outcomes.candidate_only_correct, 1)
        self.assertEqual(outcomes.baseline_only_correct, 1)
        self.assertEqual(outcomes.ties, 3)

    def test_exact_mcnemar_is_one_when_discordance_is_balanced(self) -> None:
        self.assertEqual(exact_two_sided_mcnemar_p(4, 4), 1.0)
        self.assertEqual(exact_two_sided_mcnemar_p(0, 0), 1.0)

    def test_exact_mcnemar_matches_two_sided_binomial_tail(self) -> None:
        self.assertAlmostEqual(exact_two_sided_mcnemar_p(0, 6), 0.03125)


if __name__ == "__main__":
    unittest.main()
