from __future__ import annotations

import unittest

from entry_revenue_model import (
    PriceSchedule,
    cohort_adjusted_share,
    infer_fitness_scenarios,
    project_entry,
    quantile,
    reprice_share,
)


class EntryRevenueModelTest(unittest.TestCase):
    def test_quantile_interpolates(self) -> None:
        self.assertEqual(quantile([0.0, 10.0], 25), 2.5)

    def test_fitness_conditions_on_stable_endpoints(self) -> None:
        shares = {"stable-a": 0.20, "stable-b": 0.10, "fallback": 0.70}
        prices = {
            "stable-a": {"blend": 2.0},
            "stable-b": {"blend": 1.0},
            "fallback": {"blend": 1.0},
        }
        scenarios = infer_fitness_scenarios(
            shares,
            prices,
            stable_providers={"stable-a", "stable-b"},
            proxies=("blend",),
            percentiles=(0, 100),
        )
        self.assertAlmostEqual(scenarios["p0"], 0.10)
        self.assertAlmostEqual(scenarios["p100"], 0.80)

    def test_projection_reports_share_billings_and_capacity(self) -> None:
        cheapest = PriceSchedule(input=1.0, cache=0.2, output=3.0)
        projection = project_entry(
            price_ratio=1.0,
            fitness=0.25,
            cheapest=cheapest,
            monthly_uncached_prompt_tokens=100_000_000,
            monthly_cached_prompt_tokens=200_000_000,
            monthly_output_tokens=50_000_000,
            monthly_requests=10_000,
            cogs_ratio=1.25,
        )
        self.assertAlmostEqual(projection["token_share"], 0.2)
        self.assertAlmostEqual(projection["gross_endpoint_billings_monthly"], 58.0)
        self.assertAlmostEqual(projection["inference_cogs_monthly"], 72.5)
        self.assertAlmostEqual(
            projection["gross_margin_before_platform_terms_monthly"], -14.5
        )
        self.assertAlmostEqual(projection["served_output_tokens_monthly"], 10_000_000)
        self.assertAlmostEqual(
            projection["required_average_output_tokens_per_second"],
            10_000_000 / (365.25 / 12 * 86_400),
        )
        self.assertAlmostEqual(projection["served_requests_monthly"], 2_000)
        self.assertEqual(
            projection["displayed_price_per_million"],
            {"input": 1.0, "cache_read": 0.2, "output": 3.0},
        )

    def test_cohort_adjustment_holds_known_good_tool_share_at_anchor(self) -> None:
        anchor_share = 0.10
        self.assertAlmostEqual(
            cohort_adjusted_share(
                anchor_share=anchor_share,
                anchor_price_ratio=1.25,
                price_ratio=1.25,
                tool_fraction=0.6,
                tool_tier_multiplier=1.0,
            ),
            0.10,
        )
        self.assertAlmostEqual(
            cohort_adjusted_share(
                anchor_share=anchor_share,
                anchor_price_ratio=1.25,
                price_ratio=1.25,
                tool_fraction=0.6,
                tool_tier_multiplier=0.0,
            ),
            0.04,
        )
        self.assertGreater(reprice_share(0.10, 1.25, 0.75), 0.10)


if __name__ == "__main__":
    unittest.main()
