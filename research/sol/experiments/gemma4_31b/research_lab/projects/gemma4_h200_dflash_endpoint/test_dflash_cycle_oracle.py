#!/usr/bin/env python3

import json
import unittest
from pathlib import Path

from dflash_cycle_oracle import evaluate_cycle


ROOT = Path(__file__).parent


class DFlashCycleOracleTest(unittest.TestCase):
    def fixture(self, name: str):
        return json.loads((ROOT / "fixtures" / name).read_text())

    def test_exact_cycle_passes(self):
        result = evaluate_cycle(self.fixture("dflash_cycle_pass.json"))
        self.assertTrue(result["pass"])
        self.assertIsNone(result["earliest_divergence_phase"])
        self.assertEqual(result["derived"]["expected_bonus_token"], 203)

    def test_stale_direct_carry_localizes_to_next_state(self):
        result = evaluate_cycle(self.fixture("dflash_cycle_stale_relay.json"))
        self.assertFalse(result["pass"])
        self.assertEqual(result["earliest_divergence_phase"], "next_state_relay")
        self.assertEqual(
            {issue["invariant"] for issue in result["issues"]},
            {
                "next_cycle_seed_equals_published_bonus",
                "next_cycle_length_equals_published_committed_length",
            },
        )


if __name__ == "__main__":
    unittest.main()
