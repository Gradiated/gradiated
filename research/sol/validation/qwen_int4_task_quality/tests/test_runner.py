import unittest

from validation.qwen_int4_task_quality.runner import (
    ExampleScore,
    aggregate_task_scores,
)
from validation.qwen_int4_task_quality.schema import GateConfig, UncertaintyConfig


class TaskAggregationTests(unittest.TestCase):
    def test_aggregates_accuracy_scores_and_paired_changes(self) -> None:
        baseline = [
            ExampleScore("a", 0, (0.8, 0.1)),
            ExampleScore("b", 1, (0.7, 0.2)),
            ExampleScore("c", 1, (0.1, 0.4)),
        ]
        candidate = [
            ExampleScore("a", 0, (0.6, 0.2)),
            ExampleScore("b", 1, (0.1, 0.3)),
            ExampleScore("c", 1, (0.5, 0.4)),
        ]

        report = aggregate_task_scores(
            baseline,
            candidate,
            GateConfig(maximum_accuracy_drop=0.02),
            UncertaintyConfig(paired_bootstrap_samples=100, confidence_level=0.95),
            seed=7,
        )

        self.assertAlmostEqual(report["baseline"]["accuracy"], 2 / 3)
        self.assertAlmostEqual(report["candidate"]["accuracy"], 2 / 3)
        self.assertEqual(report["paired_outcomes"]["candidate_only_correct"], 1)
        self.assertEqual(report["paired_outcomes"]["baseline_only_correct"], 1)
        self.assertEqual(report["prediction_change_count"], 2)
        self.assertTrue(report["gate"]["passed"])
        self.assertFalse(
            report["uncertainty_interpretation"][
                "bootstrap_interval_excludes_accuracy_drop_beyond_margin"
            ]
        )

    def test_accuracy_gate_includes_exact_boundary(self) -> None:
        baseline = [ExampleScore(str(i), 0, (1.0, 0.0)) for i in range(100)]
        candidate = [
            ExampleScore(str(i), 0, (0.0, 1.0) if i < 2 else (1.0, 0.0))
            for i in range(100)
        ]

        report = aggregate_task_scores(
            baseline,
            candidate,
            GateConfig(maximum_accuracy_drop=0.02),
            UncertaintyConfig(paired_bootstrap_samples=10, confidence_level=0.95),
            seed=7,
        )

        self.assertTrue(report["gate"]["passed"])

    def test_rejects_misaligned_examples(self) -> None:
        baseline = [ExampleScore("a", 0, (1.0, 0.0))]
        candidate = [ExampleScore("b", 0, (1.0, 0.0))]

        with self.assertRaisesRegex(ValueError, "order"):
            aggregate_task_scores(
                baseline,
                candidate,
                GateConfig(maximum_accuracy_drop=0.02),
                UncertaintyConfig(paired_bootstrap_samples=10, confidence_level=0.95),
                seed=7,
            )


if __name__ == "__main__":
    unittest.main()
