import unittest

from prepare_scale import candidates


class ScalePrepareTests(unittest.TestCase):
    def test_bad_question_does_not_change_the_next_question_id_or_target(self):
        row = {
            "id": "source-case-9",
            "source": "v3:policy",
            "license": "cc-by-4.0",
            "state": "case",
            "questions": [
                {
                    "type": "choice",
                    "text": "Bad",
                    "options": ["A", "A"],
                    "target": [1, 0],
                },
                {
                    "type": "choice",
                    "text": "Good",
                    "options": ["A", "B"],
                    "target": [0.25, 0.75],
                },
            ],
        }
        first, second = list(candidates(row, "zorqelis-ai/verqen-decisions"))
        with self.assertRaises(ValueError):
            first[1]()
        normalized = second[1]()
        self.assertTrue(normalized["id"].endswith(":source-case-9:q1"))
        self.assertEqual(normalized["target"], [0.25, 0.75])
        self.assertTrue(normalized["group"].endswith(":source-case-9"))

    def test_unregistered_corpus_is_not_silently_mapped(self):
        with self.assertRaisesRegex(ValueError, "unsupported source"):
            list(candidates({}, "unreviewed/evaluation-data"))


if __name__ == "__main__":
    unittest.main()
