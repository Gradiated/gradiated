import math
import unittest

from validation.qwen_int4_quality.metrics import EvaluationSums, aggregate_evaluations


class AggregateEvaluationsTests(unittest.TestCase):
    def test_weights_losses_by_target_token_count(self) -> None:
        result = aggregate_evaluations(
            [
                EvaluationSums(
                    target_tokens=1,
                    baseline_nll_sum=1.0,
                    candidate_nll_sum=1.5,
                    squared_logit_error_sum=4.0,
                    logit_values=4,
                    logit_dot_product=3.0,
                    baseline_logit_squared_sum=4.0,
                    candidate_logit_squared_sum=9.0,
                    top1_matches=1,
                    compared_positions=1,
                ),
                EvaluationSums(
                    target_tokens=3,
                    baseline_nll_sum=9.0,
                    candidate_nll_sum=10.5,
                    squared_logit_error_sum=12.0,
                    logit_values=12,
                    logit_dot_product=5.0,
                    baseline_logit_squared_sum=12.0,
                    candidate_logit_squared_sum=16.0,
                    top1_matches=1,
                    compared_positions=3,
                ),
            ]
        )

        self.assertEqual(result.target_tokens, 4)
        self.assertAlmostEqual(result.baseline_mean_nll, 2.5)
        self.assertAlmostEqual(result.candidate_mean_nll, 3.0)
        self.assertAlmostEqual(result.baseline_perplexity, math.exp(2.5))
        self.assertAlmostEqual(result.candidate_perplexity, math.exp(3.0))
        self.assertAlmostEqual(result.logit_rmse, 1.0)
        self.assertAlmostEqual(result.logit_cosine_similarity, 8.0 / math.sqrt(400.0))
        self.assertAlmostEqual(result.top1_agreement, 0.5)

    def test_rejects_empty_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one evaluation"):
            aggregate_evaluations([])

    def test_rejects_zero_denominators(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive counts"):
            aggregate_evaluations(
                [
                    EvaluationSums(
                        target_tokens=0,
                        baseline_nll_sum=0.0,
                        candidate_nll_sum=0.0,
                        squared_logit_error_sum=0.0,
                        logit_values=0,
                        logit_dot_product=0.0,
                        baseline_logit_squared_sum=0.0,
                        candidate_logit_squared_sum=0.0,
                        top1_matches=0,
                        compared_positions=0,
                    )
                ]
            )


if __name__ == "__main__":
    unittest.main()
