import unittest

from rubric_probe import complete_judgement, final_indices, parse_answers, replace_answers, wrong_numbers


class RubricProbe(unittest.TestCase):
    def setUp(self):
        self.trace = {"messages": [{"type": "HumanMessage", "content": "Compare costs"},
                                   {"type": "AssistantMessage", "content": "querying", "tool_calls": [1]},
                                   {"type": "ToolMessage", "content": "actual results"},
                                   {"type": "AssistantMessage", "content": "Cost $0.55 across 324 calls."}],
                      "final_answer": "Cost $0.55 across 324 calls."}

    def test_intervention_changes_only_final_answers(self):
        out = replace_answers(self.trace, ["Changed answer"])
        self.assertEqual(final_indices(self.trace["messages"]), [3])
        self.assertEqual(out["messages"][:3], self.trace["messages"][:3])
        self.assertEqual(out["final_answer"], "Changed answer")
        self.assertNotEqual(out["messages"][3], self.trace["messages"][3])
        self.assertEqual(self.trace["messages"][3]["content"], "Cost $0.55 across 324 calls.")

    def test_wrong_numeric_findings_preserve_dates_and_links(self):
        text = "2026 October 31: cost $0.55 for 324 calls. See https://app.io/project/4115."
        out = wrong_numbers(text)
        self.assertIn("2026 October 31", out)
        self.assertIn("https://app.io/project/4115", out)
        self.assertNotIn("$0.55", out)
        self.assertNotIn("324 calls", out)
        with self.assertRaises(ValueError):
            wrong_numbers("No numerical findings")

    def test_broken_segment_or_answer_count_is_rejected(self):
        with self.assertRaises(ValueError):
            final_indices([{"type": "HumanMessage", "content": "Question"}])
        with self.assertRaises(ValueError):
            replace_answers(self.trace, [])

    def test_rewrite_shape(self):
        self.assertEqual(parse_answers('Answer: ["short"]', 1), ["short"])
        with self.assertRaises(ValueError):
            parse_answers('["one"]', 2)

    def test_incomplete_judgement_is_not_a_rejection(self):
        self.assertFalse(complete_judgement({"error": "rate limited"}))
        self.assertFalse(complete_judgement({"overall": float("nan")}))
        self.assertTrue(complete_judgement({"overall": 8.5, "material_wrong_final": 0, "material_unsupported_final": 0}))


if __name__ == "__main__":
    unittest.main()
