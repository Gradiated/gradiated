from __future__ import annotations

import unittest

from recurrent_local_attention import (
    TARGET_VERIFY_ROWS,
    WINDOW_TOKENS,
    deterministic_information_fixture,
    window_transitions,
)


class RecurrentLocalAttentionTest(unittest.TestCase):
    def test_exact_target_verify_horizon_and_eviction(self) -> None:
        transitions = window_transitions(4_214, TARGET_VERIFY_ROWS)
        for row, transition in enumerate(transitions):
            self.assertEqual(len(transition.represented_positions), WINDOW_TOKENS)
            self.assertEqual(transition.represented_positions[-1], 4_214 + row)
            self.assertEqual(len(transition.added_positions), row + 1)
            self.assertEqual(len(transition.evicted_positions), row + 1)
            self.assertEqual(
                set(transition.added_positions)
                & set(transition.represented_positions[:-row - 1 or None]),
                set(),
            )

    def test_invalid_query_blocks_fail_closed(self) -> None:
        for start, count in ((-1, 1), (0, 0), (0, 33)):
            with self.assertRaises(ValueError):
                window_transitions(start, count)

    def test_pure_python_consumer_matches_direct_window(self) -> None:
        fixture = deterministic_information_fixture()
        self.assertTrue(fixture["consumer_executed"])
        self.assertTrue(fixture["every_in_window_token_once"])
        self.assertTrue(fixture["expired_tokens_contribute_zero"])
        self.assertTrue(fixture["direct_recurrent_match"])
        self.assertTrue(fixture["finite"])
        self.assertLess(fixture["maximum_absolute_error"], 1.0e-12)


if __name__ == "__main__":
    unittest.main()
