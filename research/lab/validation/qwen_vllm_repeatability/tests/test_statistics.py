import unittest

from validation.qwen_vllm_repeatability.statistics import (
    paired_ratio_summary,
    summarize_samples,
)


class StatisticsTests(unittest.TestCase):
    def test_reports_sample_dispersion_and_student_confidence_interval(self) -> None:
        summary = summarize_samples([8.0, 9.0, 10.0, 11.0, 12.0])

        self.assertEqual(summary.count, 5)
        self.assertEqual(summary.mean, 10.0)
        self.assertEqual(summary.median, 10.0)
        self.assertAlmostEqual(summary.sample_standard_deviation, 2.5**0.5)
        self.assertAlmostEqual(summary.coefficient_of_variation, 2.5**0.5 / 10)
        self.assertAlmostEqual(summary.ci95_low, 8.0367568385, places=6)
        self.assertAlmostEqual(summary.ci95_high, 11.9632431615, places=6)

    def test_rejects_non_finite_and_too_few_samples(self) -> None:
        for values in ([1.0], [1.0, float("nan")], [0.0, 0.0]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    summarize_samples(values)

    def test_paired_ratio_uses_matching_repeat_indices(self) -> None:
        summary = paired_ratio_summary(
            {1: 10.0, 2: 20.0, 3: 40.0},
            {1: 20.0, 2: 30.0, 3: 60.0},
        )

        self.assertEqual(summary.count, 3)
        self.assertAlmostEqual(summary.median, 1.5)


if __name__ == "__main__":
    unittest.main()
