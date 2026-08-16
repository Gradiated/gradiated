import unittest

from analyze_first_target_verifier_capture import analyze


class FirstTargetVerifierCaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analyze()

    def test_request_25_transition(self):
        transition = self.result["request_25_transition"]
        self.assertEqual(transition["ar_endpoint_prefix"], [236814, 3496])
        self.assertEqual(transition["candidate_endpoint_prefix"], [236814, 759])
        self.assertEqual(
            transition["first_target_step"]["target_top1"],
            [759, 236814, 236761, 87096],
        )

    def test_bonus_consumer_propagates_first_wrong_top1(self):
        chain = self.result["causal_chain"]
        self.assertEqual(
            chain["first_incorrect_observable_symbol"]["request_owned_value"], 759
        )
        self.assertTrue(chain["downstream_consumer"]["consumer_consistent_with_input"])
        self.assertEqual(
            self.result["request_25_transition"]["first_target_step"]["bonus_token"],
            759,
        )

    def test_no_patch_without_source_complete_replay(self):
        self.assertEqual(self.result["classification"], "capture_insufficient_for_cause")
        self.assertIsNone(self.result["repair_candidate"])
        self.assertFalse(self.result["source_completeness"]["pass"])
        self.assertFalse(self.result["repair_gate"]["pass"])


if __name__ == "__main__":
    unittest.main()
