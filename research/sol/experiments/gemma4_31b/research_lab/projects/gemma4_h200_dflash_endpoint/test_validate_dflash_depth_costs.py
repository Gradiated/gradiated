#!/usr/bin/env python3

import unittest

from validate_dflash_depth_costs import quantile, summarize


class SummaryTests(unittest.TestCase):
    def test_quantile_interpolates(self) -> None:
        self.assertEqual(quantile([0.0, 10.0], 0.25), 2.5)

    def test_summary_preserves_full_sum_and_robust_center(self) -> None:
        result = summarize([1.0] * 9 + [100.0])
        self.assertEqual(result["count"], 10)
        self.assertEqual(result["sum_ms"], 109.0)
        self.assertEqual(result["median_ms"], 1.0)
        self.assertEqual(result["trimmed_mean_10pct_ms"], 1.0)


if __name__ == "__main__":
    unittest.main()
