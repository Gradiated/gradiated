from __future__ import annotations

import unittest

from grad_research.portfolio import plan_setup_affine_session, select_portfolio

from helpers import scout


class PortfolioTests(unittest.TestCase):
    def test_shortlist_preserves_cross_stack_model_and_adversarial_routes(self):
        cards = [
            scout("attention-local", slot="bottleneck_adjacent", family="attention", origin="trace_local"),
            scout("attention-first", slot="bottleneck_adjacent", family="attention", origin="first_principles"),
            scout("attention-third", slot="bottleneck_adjacent", family="attention", origin="trace_local", impact=1.0),
            scout("runtime-cross", slot="cross_stack", family="runtime", origin="literature_recombination"),
            scout("model-layout", slot="model_architecture", family="representation", origin="cross_model_analogy"),
            scout("measurement-skeptic", slot="adversarial", family="measurement", origin="adversarial"),
            scout("duplicate-layout", slot="model_architecture", family="representation", origin="trace_local", novelty_key="model-layout", impact=0.1),
        ]

        result = select_portfolio(cards, max_size=5)
        selected = result["selected"]
        slots = [card["slot"] for card in selected]
        family_counts = result["coverage"]["family_counts"]

        self.assertEqual(5, len(selected))
        self.assertGreaterEqual(slots.count("bottleneck_adjacent"), 2)
        self.assertIn("cross_stack", slots)
        self.assertIn("model_architecture", slots)
        self.assertIn("adversarial", slots)
        self.assertLessEqual(max(family_counts.values()), 2)
        self.assertGreaterEqual(result["coverage"]["origin_count"], 3)
        self.assertTrue(result["coverage"]["ready"])
        self.assertEqual(len({card["novelty_key"] for card in selected}), len(selected))

    def test_prior_failure_is_not_repeated_without_revisit_reason(self):
        old = scout("old", slot="bottleneck_adjacent", family="attention", origin="trace_local", novelty_key="same-change")
        changed = scout("changed", slot="bottleneck_adjacent", family="attention", origin="first_principles", novelty_key="same-change")
        changed["revisit_reason"] = "new phase-correct trace"
        result = select_portfolio([old, changed], previous_novelty_keys={"same-change"})
        self.assertEqual(["changed"], [card["id"] for card in result["selected"]])

    def test_session_planner_prefers_multiple_arms_per_setup(self):
        cards = [
            scout("a", slot="bottleneck_adjacent", family="attention", origin="trace_local", cost=0.05, setup_key="resident-l40s"),
            scout("b", slot="cross_stack", family="scheduler", origin="first_principles", cost=0.05, setup_key="resident-l40s"),
            scout("c", slot="model_architecture", family="model", origin="cross_model_analogy", cost=0.04, setup_key="new-h100", impact=1.0),
        ]
        plan = plan_setup_affine_session(
            cards,
            setup_cost_usd={"resident-l40s": 0.20, "new-h100": 0.50},
            budget_usd=0.40,
            max_arms=3,
        )
        self.assertEqual("resident-l40s", plan["setup_key"])
        self.assertEqual(["a", "b"], [card["id"] for card in plan["arms"]])
        self.assertEqual(2, plan["arms_per_setup"])


if __name__ == "__main__":
    unittest.main()
