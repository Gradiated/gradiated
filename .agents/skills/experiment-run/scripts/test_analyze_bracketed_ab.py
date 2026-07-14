import unittest

from analyze_bracketed_ab import analyze


class BracketedAbTests(unittest.TestCase):
    def test_three_positive_bracketed_effects_have_positive_interval(self):
        sequence = [
            {"label": "A1", "role": "control", "value": 100},
            {"label": "B1", "role": "candidate", "value": 110},
            {"label": "A2", "role": "control", "value": 100},
            {"label": "B2", "role": "candidate", "value": 108},
            {"label": "A3", "role": "control", "value": 100},
            {"label": "B3", "role": "candidate", "value": 106},
            {"label": "A4", "role": "control", "value": 100},
        ]
        result = analyze(sequence, "test", 1000)
        self.assertEqual(len(result["pairs"]), 3)
        self.assertGreater(result["paired_percentile_bootstrap_95"]["lower"], 0)

    def test_non_alternating_sequence_fails(self):
        with self.assertRaises(ValueError):
            analyze([
                {"label": "A1", "role": "control", "value": 1},
                {"label": "A2", "role": "control", "value": 1},
                {"label": "A3", "role": "control", "value": 1},
            ], "test")

    def test_two_candidate_repetitions_are_descriptive_only(self):
        sequence = [
            {"label": "A1", "role": "control", "value": 100},
            {"label": "B1", "role": "candidate", "value": 108},
            {"label": "A2", "role": "control", "value": 101},
            {"label": "B2", "role": "candidate", "value": 107},
            {"label": "A3", "role": "control", "value": 100},
        ]
        result = analyze(sequence, "underpowered", 1000)
        self.assertEqual(result["independent_candidate_repetitions"], 2)
        self.assertIsNone(result["paired_percentile_bootstrap_95"])
        self.assertEqual(result["precision_status"], "descriptive_only_fewer_than_three_candidate_repetitions")


if __name__ == "__main__":
    unittest.main()
