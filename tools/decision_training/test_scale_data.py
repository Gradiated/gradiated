import json
import unittest

from scale_data import (
    normalize_procedural,
    normalize_verqen,
    repair_event_probability_wording,
)


class ScaleDataTests(unittest.TestCase):
    def test_graded_event_target_does_not_answer_a_threshold_question(self):
        row = {
            "id": "ledger",
            "task": "arithmetic",
            "state": "One deposit, two withdrawals",
            "questions": {
                "random_is_deposit": {
                    "type": "noul",
                    "instructions": "If one transaction is picked uniformly at random, is it more likely than not to be a deposit?",
                }
            },
            "answers": {"random_is_deposit": {"noul": 1 / 3}},
        }
        result = next(normalize_procedural(row))
        self.assertNotIn("more likely than not", result["question"]["instructions"])
        self.assertAlmostEqual(result["target"][1], 1 / 3)
        self.assertIn(
            "more likely than not", result["curation"]["original_instructions"]
        )
        self.assertEqual(
            repair_event_probability_wording(
                "arithmetic",
                "random_line_bulk",
                "Is a randomly chosen line more likely than not to order 3 or more units?",
            ),
            "Does a uniformly randomly chosen line order 3 or more units?",
        )
        self.assertEqual(
            repair_event_probability_wording(
                "arithmetic",
                "random_is_long",
                "If one task is picked uniformly at random, is it more likely than not to last more than 20 minutes?",
            ),
            "If one task is picked uniformly at random, does it last more than 20 minutes?",
        )
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            repair_event_probability_wording(
                "arithmetic", "new", "Is it more likely than not to rain?"
            )

    def test_alternate_event_probability_templates_are_also_repaired(self):
        for key, instruction in (
            (
                "random_is_deposit",
                "Is a randomly chosen transaction more likely than not a deposit?",
            ),
            (
                "random_line_bulk",
                "If one order line is picked uniformly at random, is its quantity more likely than not to be at least 3?",
            ),
            (
                "random_is_long",
                "Is a randomly chosen task more likely than not to take longer than 30 minutes?",
            ),
        ):
            with self.subTest(key=key):
                self.assertNotIn(
                    "more likely than not",
                    repair_event_probability_wording("arithmetic", key, instruction),
                )

    def test_native_choice_aligns_by_id_instead_of_dictionary_order(self):
        row = {
            "id": "case1",
            "task": "routing",
            "state": "case",
            "questions": {
                "q": {
                    "type": "choice",
                    "instructions": "Pick",
                    "criteria": {"b": None, "a": "Option A"},
                }
            },
            "answers": {"q": {"probabilities": {"a": 0.8, "b": 0.2}}},
        }
        result = next(normalize_procedural(row))
        self.assertEqual(result["labels"], ["b", "a"])
        self.assertEqual(result["descriptions"], ["b", "Option A"])
        self.assertEqual(result["target"], [0.2, 0.8])

    def test_native_binary_and_ordinal_probabilities_keep_their_meaning(self):
        row = {
            "id": "case2",
            "task": "uncertainty",
            "state": "case",
            "questions": json.dumps(
                {
                    "n": {"type": "noul", "instructions": "True?"},
                    "s": {
                        "type": "score",
                        "instructions": "Rate",
                        "criteria": ["low", "high"],
                    },
                }
            ),
            "answers": json.dumps(
                {"n": {"noul": 0.25}, "s": {"probabilities": {"1": 0.7, "0": 0.3}}}
            ),
        }
        a, b = list(normalize_procedural(row))
        self.assertEqual(a["target"], [0.75, 0.25])
        self.assertEqual(b["target"], [0.3, 0.7])
        self.assertEqual(a["group"], b["group"])

    def test_native_missing_answer_is_not_silently_dropped(self):
        row = {"questions": {"q": {}}, "answers": {}}
        with self.assertRaisesRegex(ValueError, "IDs differ"):
            list(normalize_procedural(row))

    def test_verqen_related_source_views_share_holdout_family(self):
        row = {
            "id": "mnli_12",
            "source": "mnli",
            "license": "cc-by-sa-3.0",
            "state": "text",
            "questions": [
                {
                    "type": "choice",
                    "text": "Relation?",
                    "options": ["yes", "no"],
                    "target": [0.2, 0.8],
                }
            ],
        }
        a = next(normalize_verqen(row))
        b = next(normalize_verqen({**row, "source": "mnli+fmt"}))
        self.assertEqual(a["family_group"], b["family_group"])
        self.assertEqual(a["group"], b["group"])
        self.assertEqual(a["target"], [0.2, 0.8])

    def test_repeated_option_text_cannot_hide_behind_distinct_numeric_labels(self):
        row = {
            "id": "bad",
            "source": "v3:browser",
            "license": "cc-by-4.0",
            "state": "case",
            "questions": [
                {
                    "type": "choice",
                    "text": "Pick",
                    "options": ["click A", "click A"],
                    "target": [1.0, 0.0],
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "repeated option"):
            list(normalize_verqen(row))


if __name__ == "__main__":
    unittest.main()
