import os
import unittest

from gdecide.backends.knowline import plan_batches
from gdecide.prepare_knowline import target


class PlanBatches(unittest.TestCase):
    def test_budget_and_cover(self):
        lengths = [5, 100, 30, 30, 2000, 7, 64]
        groups = plan_batches(lengths, 128)
        self.assertEqual(sorted(i for g in groups for i in g), list(range(len(lengths))))
        for g in groups:
            self.assertTrue(len(g) == 1 or max(lengths[i] for i in g) * len(g) <= 128)
        self.assertEqual(groups[0], [4])

    def test_max_rows(self):
        self.assertEqual([len(g) for g in plan_batches([1] * 10, 1000, max_rows=4)], [4, 4, 2])


class Target(unittest.TestCase):
    def test_knowline_option_order(self):
        noul = {"type": "noul"}
        self.assertEqual(target(["true", "false"], noul, True), [1.0, 0.0])
        self.assertEqual(target(["true", "false"], noul, 0.25), [0.25, 0.75])
        self.assertEqual(target(["a", "b"], {"type": "choice"}, "b"), [0.0, 1.0])
        self.assertEqual(target(["a", "b"], {"type": "choice"}, {"a": 3, "b": 1}), [0.75, 0.25])
        self.assertIsNone(target(["a", "b"], {"type": "choice"}, "c"))
        self.assertIsNone(target(["a", "b"], {"type": "choice"}, None))


@unittest.skipUnless(os.environ.get("KNOWLINE_DIR"), "set KNOWLINE_DIR to a KnowLine repo directory (tokenizer and front end)")
class Rendering(unittest.TestCase):
    def test_matches_release_engine_prompts(self):
        from gdecide.backends.knowline import Renderer

        r = Renderer(os.environ["KNOWLINE_DIR"])
        request = {"state": "Customer: my order arrived broken.",
                   "questions": {"refund": {"type": "noul", "instructions": "Refund?"},
                                 "tone": {"type": "choice", "instructions": "Tone?", "criteria": {"angry": "Angry", "calm": None}}}}
        prompts = r.texts(request)
        text, keys = prompts["tone"]
        self.assertEqual(keys, ["angry", "calm"])
        self.assertTrue(text.startswith("<bos><|turn>user\nCustomer: my order arrived broken.<turn|>"))
        self.assertIn("Read the same input again before answering:\n", text)
        self.assertTrue(text.endswith("<|turn>model\n<|channel>thought\n<channel|>Answer:"))
        self.assertEqual(len(r.label_ids), 255)


if __name__ == "__main__":
    unittest.main()
