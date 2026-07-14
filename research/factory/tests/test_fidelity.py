from __future__ import annotations

import unittest

from grad_research.fidelity import analyze_metric_semantics, evaluate_proxy_transfer, promotion_decision, score_prediction


class FidelityTests(unittest.TestCase):
    def test_summed_component_duration_is_diagnostic_not_wall_time_share(self):
        metrics = [
            {"name": "attention", "value": 0.40, "unit": "fraction", "time_semantics": "summed_component_duration", "coverage": 0.99},
            {"name": "decode_critical_path", "value": 0.18, "unit": "fraction", "time_semantics": "critical_path_union", "coverage": 0.97},
        ]
        analysis = analyze_metric_semantics(metrics)
        self.assertEqual(["decode_critical_path"], [row["name"] for row in analysis["wall_time_admissible"]])
        self.assertEqual(["attention"], [row["name"] for row in analysis["diagnostic_only"]])
        self.assertEqual(0.18, analysis["largest_admissible_fraction"])

    def test_large_component_win_small_server_effect_stops_lineage(self):
        result = evaluate_proxy_transfer(
            component_effect_fraction=0.40270374366143835,
            server_effects=[0.010475660892024452, 0.010447225074682542],
            materiality_gate=0.05,
            independent_candidate_repetitions=2,
        )
        self.assertEqual("scientific_mixed", result["outcome_class"])
        self.assertEqual("stop_proxy_lineage", result["lineage_decision"])
        self.assertFalse(result["server_gate_pass"])
        self.assertFalse(result["confidence_interval_permitted"])
        self.assertAlmostEqual(0.010461442983353497, result["median_server_effect_fraction"])

    def test_prediction_scoring_separates_direction_gate_and_magnitude(self):
        scored = score_prediction(
            {
                "expected_direction": "increase",
                "minimum_effect_fraction": 0.05,
                "point_estimate_fraction": 0.08,
            },
            observed_effect_fraction=-0.0284848,
        )
        self.assertFalse(scored["direction_pass"])
        self.assertFalse(scored["materiality_gate_pass"])
        self.assertAlmostEqual(-0.1084848, scored["magnitude_error_fraction"])

    def test_lower_fidelity_pass_only_promotes_a_measurement(self):
        decision = promotion_decision(
            fidelity="target_gpu_component",
            outcome_class="scientific_positive",
            plausible_end_to_end_ceiling_fraction=0.12,
            campaign_gate_fraction=0.05,
        )
        self.assertEqual("measure_next_fidelity", decision["action"])
        self.assertFalse(decision["claim_permitted"])


if __name__ == "__main__":
    unittest.main()
