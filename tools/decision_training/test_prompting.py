import unittest

from prompting import render_prompt


class Tokenizer:
    def apply_chat_template(self, messages, tokenize, reasoning_effort):
        assert not tokenize and reasoning_effort == "none"
        return messages[0]["content"]


class PromptTests(unittest.TestCase):
    def test_targets_rationales_and_outcomes_never_change_the_visible_input(self):
        row = {
            "state": {"z": "é", "a": 1},
            "question": {"instructions": "Act?"},
            "descriptions": ["Wait", "Approve"],
            "target": [1, 0],
            "rationale": "private answer",
            "future_outcome": "secret",
        }
        first = render_prompt(Tokenizer(), row)
        second = render_prompt(
            Tokenizer(),
            {**row, "target": [0, 1], "rationale": "other", "future_outcome": "other"},
        )
        self.assertEqual(first, second)
        self.assertNotIn("secret", first)
        self.assertNotIn("private answer", first)
        self.assertIn('{"a": 1, "z": "é"}', first)
        self.assertIn("A: Wait\nB: Approve", first)


if __name__ == "__main__":
    unittest.main()
