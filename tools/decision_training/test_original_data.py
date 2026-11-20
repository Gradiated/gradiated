import unittest

from original_data import normalize_eikos, normalize_esci, normalize_snli


class OriginalDataTests(unittest.TestCase):
    def test_snli_neutral_index_and_premise_group_are_preserved(self):
        row = {
            "premise": "A person is walking.",
            "hypothesis": "The person is happy.",
            "label": 1,
        }
        first = normalize_snli(row)
        self.assertEqual(first["labels"], ["entailment", "neutral", "contradiction"])
        self.assertEqual(first["target"], [0, 1, 0])
        self.assertEqual(
            first["group"],
            normalize_snli({**row, "hypothesis": "The person is standing."})["group"],
        )
        with self.assertRaisesRegex(ValueError, "no agreed"):
            normalize_snli({**row, "label": -1})

    def test_esci_is_nominal_query_grouped_and_contains_no_gold_metadata(self):
        row = {
            "query": "phone",
            "query_id": 2,
            "product_locale": "us",
            "product_id": "p",
            "example_id": 1,
            "product_title": "Phone case",
            "product_description": "Protects a phone",
            "esci_label": "Complement",
            "small_version": True,
        }
        result = normalize_esci(row)
        self.assertEqual(result["question"]["type"], "choice")
        self.assertEqual(result["target"], [0, 0, 1, 0])
        self.assertNotIn("esci_label", result["state"])
        self.assertEqual(
            result["group"],
            normalize_esci({**row, "example_id": 3, "product_title": "Other product"})[
                "group"
            ],
        )

    def test_eikos_yes_first_probability_order_is_not_flipped(self):
        row = {
            "id": "x",
            "split": "train",
            "item_writer": "program",
            "label_source": "exact_probability",
            "family": "probability",
            "state": "Eight successes among ten",
            "question_type": "noul",
            "instructions": "Is a random draw successful?",
            "options": [
                {"label": "yes", "description": "Yes"},
                {"label": "no", "description": "No"},
            ],
            "target_probs": [0.8, 0.2],
            "teacher_probs": [0.4, 0.6],
        }
        result = normalize_eikos(row)
        self.assertEqual(result["labels"], ["yes", "no"])
        self.assertEqual(result["target"], [0.8, 0.2])
        self.assertIsNone(
            normalize_eikos(
                {**row, "item_writer": "GLM-5.3-Flash", "label_source": "teacher"}
            )
        )
        self.assertIsNone(normalize_eikos({**row, "split": "heldout"}))


if __name__ == "__main__":
    unittest.main()
