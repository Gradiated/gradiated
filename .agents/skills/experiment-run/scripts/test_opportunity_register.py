import unittest

from opportunity_register import ranked_document, validate_entry


def entry(identifier: str, cost: float, discrimination: float) -> dict:
    return {
        "id": identifier,
        "observation": "measured queueing",
        "evidence_scope": "model/revision/workload/phase/hardware",
        "competing_explanations": ["scheduler", "kernel"],
        "mechanism": "change one scheduler limit",
        "falsifier": "queueing unchanged",
        "next_measurement": "matched A/B",
        "cost_usd": cost,
        "decision_impact": 0.8,
        "uncertainty": 0.7,
        "discrimination_power": discrimination,
        "readiness": 1.0,
        "transfer_penalty": 0.0,
    }


class OpportunityRegisterTests(unittest.TestCase):
    def test_missing_fields_fail_closed(self):
        self.assertTrue(validate_entry({"id": "bad"}))

    def test_ranking_rewards_discrimination_and_low_cost(self):
        result = ranked_document({"schema_version": 1, "opportunities": [entry("slow", 1.0, 0.5), entry("fast", 0.2, 0.9)]})
        self.assertEqual(result["opportunities"][0]["id"], "fast")
        self.assertIn("claim_limit", result["ranking_method"])

    def test_rich_campaign_entry_is_normalized_without_discarding_evidence(self):
        rich = {
            "id": "rich",
            "title": "Measured opportunity",
            "observation": {"summary": "measured launch gaps", "evidence_scope": "model/hardware/workload"},
            "bottleneck_interpretation": {"competing_explanations": ["host launch", "GPU dependency"]},
            "candidate": {"intervention": "capture a dependency timeline"},
            "falsifier": "no launch gaps on the critical path",
            "next_measurement": {"experiment": "phase_trace"},
            "information_value": {"estimated_cost_usd": 0.0},
            "ranking_inputs": {
                "decision_impact": 0.9,
                "uncertainty": 0.8,
                "discrimination_power": 0.95,
                "readiness": 1.0,
                "transfer_penalty": 0.1,
            },
        }
        result = ranked_document({"schema_version": 1, "opportunities": [rich]})
        self.assertEqual(result["opportunities"][0]["title"], "Measured opportunity")
        self.assertGreater(result["opportunities"][0]["decision_resolution_per_dollar"], 0)


if __name__ == "__main__":
    unittest.main()
