import unittest

from validation.qwen_kv_recovery.data import build_training_windows


class IntegerTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        del add_special_tokens
        return [int(value) for value in text.split()]


class TrainingDataTests(unittest.TestCase):
    def test_reserves_calibration_prefix_and_counts_next_token_targets_exactly(
        self,
    ) -> None:
        rows = [" ".join(str(value) for value in range(40))]

        corpus = build_training_windows(
            rows,
            IntegerTokenizer(),
            reserved_calibration_tokens=8,
            training_target_tokens=12,
            target_tokens_per_step=4,
        )

        self.assertEqual(corpus.calibration_token_range, (0, 8))
        self.assertEqual(corpus.training_target_token_range, (8, 20))
        self.assertEqual(corpus.training_target_tokens, 12)
        self.assertEqual(len(corpus.windows), 3)
        self.assertEqual(corpus.windows[0].input_ids, (7, 8, 9, 10, 11))
        self.assertEqual(corpus.windows[0].target_ids, (8, 9, 10, 11))
        self.assertEqual(corpus.windows[-1].target_ids, (16, 17, 18, 19))

    def test_rejects_non_integral_steps(self) -> None:
        with self.assertRaisesRegex(ValueError, "divisible"):
            build_training_windows(
                ["0 1 2 3 4 5 6 7 8 9"],
                IntegerTokenizer(),
                reserved_calibration_tokens=2,
                training_target_tokens=5,
                target_tokens_per_step=2,
            )


if __name__ == "__main__":
    unittest.main()
