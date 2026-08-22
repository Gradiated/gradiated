from __future__ import annotations

import unittest

from train_cpu_speculative_decoder import (
    accepted_prefix,
    in_request_ngram_draft,
    label_for_next,
)


class CpuSpeculativeDecoderTest(unittest.TestCase):
    def test_copy_label_uses_nearest_matching_token(self) -> None:
        self.assertEqual(label_for_next([4, 5, 4], 4, 4, {4: 0}), 1)
        self.assertEqual(label_for_next([4, 5], 4, 4, {4: 0}), 2)

    def test_vocabulary_label_follows_copy_classes(self) -> None:
        self.assertEqual(label_for_next([4, 5], 9, 4, {9: 2}), 7)

    def test_in_request_ngram_generates_repeated_pattern(self) -> None:
        self.assertEqual(
            in_request_ngram_draft([7, 8, 7, 8], depth=4, max_order=4),
            [7, 8, 7, 8],
        )

    def test_accepted_prefix_stops_at_first_mismatch(self) -> None:
        self.assertEqual(accepted_prefix([1, 2, 9, 4], [1, 2, 3, 4]), 2)


if __name__ == "__main__":
    unittest.main()
