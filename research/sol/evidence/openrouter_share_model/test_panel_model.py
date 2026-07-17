from __future__ import annotations

import math
import unittest

from panel_model import (
    EndpointRow,
    FittedModel,
    evaluate_predictions,
    fit_compositional_model,
    _benchmark_match,
    _provider_key,
    panel_rows,
    predict_group,
    request_share_nowcast,
    uptime_gated_inverse_square,
)


def synthetic_rows() -> list[EndpointRow]:
    rows: list[EndpointRow] = []
    for model_index in range(8):
        prices = (1.0, 1.5 + model_index * 0.03, 2.2)
        weights = [price**-2 for price in prices]
        total = sum(weights)
        for endpoint_index, (price, weight) in enumerate(zip(prices, weights)):
            rows.append(
                EndpointRow(
                    model=f"model-{model_index}",
                    provider=f"provider-{endpoint_index}",
                    share=weight / total,
                    features={
                        "log_price_non_tool": math.log(price),
                        "log_price_tool": 0.0,
                        "uptime_shortfall_99": 0.0,
                        "uptime_degraded": 0.0,
                    },
                    price_ratio=price,
                    uptime=99.9,
                )
            )
    return rows


class PanelModelTest(unittest.TestCase):
    def test_benchmark_provider_matching_handles_public_name_variants(self) -> None:
        scores = {
            "alibaba": {"gpqa_diamond": {"score": 0.9, "run_count": 2}},
            "wafer": {"gpqa_diamond": {"score": 0.7, "run_count": 3}},
        }
        self.assertEqual(_provider_key("Alibaba Cloud Int."), "alibaba")
        matched, method = _benchmark_match("Alibaba Cloud Int.", scores)
        self.assertEqual(method, "exact")
        self.assertEqual(matched["gpqa_diamond"]["score"], 0.9)
        _, fast_method = _benchmark_match("Wafer Fast", scores)
        self.assertEqual(fast_method, "base_provider_fallback")

    def test_panel_rows_builds_tool_weighted_benchmark_shortfall(self) -> None:
        raw_rows = []
        for provider, gpqa, tau in (
            ("good", 0.90, 0.75),
            ("median", 0.87, 0.72),
            ("bad", 0.70, 0.50),
        ):
            raw_rows.append(
                {
                    "model": "model-benchmark",
                    "provider": provider,
                    "share": 1 / 3,
                    "price_ratio": 1.0,
                    "uptime": 99.9,
                    "throughput": 40.0,
                    "tool_error_rate": 0.0,
                    "cache_hit_rate": 0.0,
                    "parameter_coverage": 1.0,
                    "context_ratio": 1.0,
                    "age_days": 10.0,
                    "derankable_error_rate": 0.0,
                    "rate_limit_rate": 0.0,
                    "request_count_30m": 100,
                    "benchmark_gpqa_score": gpqa,
                    "benchmark_tau_score": tau,
                }
            )
        rows = panel_rows(
            {"models": [{"rows": raw_rows, "tool_fraction_proxy": 0.5}]}
        )
        self.assertEqual(rows[0].features["benchmark_gpqa_shortfall_z"], 0.0)
        self.assertGreater(rows[2].features["benchmark_gpqa_shortfall_z"], 1.0)
        self.assertGreater(rows[2].features["benchmark_tau_shortfall_z"], 1.0)
        self.assertEqual(rows[2].features["benchmark_missing"], 0.0)

    def test_fit_recovers_price_direction_and_beats_equal_share(self) -> None:
        rows = synthetic_rows()
        names = (
            "log_price_non_tool",
            "log_price_tool",
            "uptime_shortfall_99",
            "uptime_degraded",
        )
        fitted = fit_compositional_model(
            rows,
            feature_names=names,
            constrained_nonpositive=set(names),
            iterations=2_000,
            learning_rate=0.05,
            l2=0.001,
        )
        self.assertLess(fitted.coefficients["log_price_non_tool"], -1.5)
        predictions = {
            model: predict_group(group, fitted)
            for model, group in fitted.group_rows(rows).items()
        }
        learned = evaluate_predictions(rows, predictions)
        equal = evaluate_predictions(
            rows,
            {
                model: {row.provider: 1 / len(group) for row in group}
                for model, group in fitted.group_rows(rows).items()
            },
        )
        self.assertLess(learned["mean_total_variation"], equal["mean_total_variation"] / 5)

    def test_uptime_gated_baseline_normalizes_and_deprioritizes(self) -> None:
        rows = synthetic_rows()[:3]
        rows[0].uptime = 99.9
        rows[1].uptime = 90.0
        rows[2].uptime = 70.0
        prediction = uptime_gated_inverse_square(rows)
        self.assertAlmostEqual(sum(prediction.values()), 1.0)
        self.assertGreater(prediction[rows[0].provider], prediction[rows[1].provider])
        self.assertGreater(prediction[rows[1].provider], prediction[rows[2].provider])

    def test_provider_reputation_learns_persistent_cross_model_effect(self) -> None:
        rows = synthetic_rows()
        for row in rows:
            if row.provider == "provider-2":
                row.share *= 8
        for group in FittedModel.group_rows(rows).values():
            total = sum(row.share for row in group)
            for row in group:
                row.share /= total
        fitted = fit_compositional_model(
            rows,
            feature_names=("log_price_non_tool",),
            constrained_nonpositive={"log_price_non_tool"},
            iterations=1_200,
            learning_rate=0.04,
            provider_effect_l2=0.02,
        )
        self.assertGreater(
            fitted.provider_effects["provider-2"],
            fitted.provider_effects["provider-0"],
        )

    def test_request_share_nowcast_uses_counts_and_excludes_missing(self) -> None:
        rows = synthetic_rows()[:3]
        for row, count in zip(rows, (10.0, 30.0, None)):
            row.features["log_request_count_relative"] = (
                math.log(count / 10.0) if count is not None else 0.0
            )
            row.features["request_count_missing"] = 1.0 if count is None else 0.0
        prediction = request_share_nowcast(rows)
        self.assertAlmostEqual(prediction[rows[0].provider], 0.25)
        self.assertAlmostEqual(prediction[rows[1].provider], 0.75)
        self.assertEqual(prediction[rows[2].provider], 0.0)


if __name__ == "__main__":
    unittest.main()
