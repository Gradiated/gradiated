import unittest

import torch

from validation.qwen_int4_task_quality.scoring import (
    build_choice_encoding,
    length_normalized_continuation_log_likelihood,
)


class FakeTokenizer:
    def encode(self, text: str, add_special_tokens: bool) -> list[int]:
        values = {
            "Question: goal\nAnswer:": [9, 10, 11],
            "Question: goal\nAnswer: solution": [9, 10, 11, 4, 5],
        }
        return values[text]


class ContinuationScoringTests(unittest.TestCase):
    def test_joint_tokenization_pins_continuation_boundary(self) -> None:
        encoding = build_choice_encoding(
            FakeTokenizer(),
            prompt="Question: goal\nAnswer:",
            choice="solution",
        )

        self.assertEqual(encoding.input_ids.tolist(), [[9, 10, 11, 4, 5]])
        self.assertEqual(encoding.target_start, 2)
        self.assertEqual(encoding.target_tokens, 2)

    def test_rejects_tokenization_that_changes_prompt_prefix(self) -> None:
        class BoundaryChangingTokenizer(FakeTokenizer):
            def encode(self, text: str, add_special_tokens: bool) -> list[int]:
                if text.endswith(" solution"):
                    return [9, 10, 12, 4]
                return [9, 10, 11]

        with self.assertRaisesRegex(ValueError, "token prefix"):
            build_choice_encoding(
                BoundaryChangingTokenizer(),
                prompt="Question: goal\nAnswer:",
                choice="solution",
            )

    def test_length_normalization_averages_only_continuation_tokens(self) -> None:
        logits = torch.tensor(
            [
                [
                    [0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0],
                    [0.0, 2.0, 0.0],
                    [0.0, 0.0, 2.0],
                ]
            ]
        )
        input_ids = torch.tensor([[2, 0, 0, 1, 2]])
        expected = torch.log_softmax(logits[:, 2:4], dim=-1)
        expected = (expected[0, 0, 1] + expected[0, 1, 2]) / 2

        score = length_normalized_continuation_log_likelihood(
            logits,
            input_ids,
            target_start=2,
            target_tokens=2,
        )

        self.assertAlmostEqual(score, expected.item())


if __name__ == "__main__":
    unittest.main()
