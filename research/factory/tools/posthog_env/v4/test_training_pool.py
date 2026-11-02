import unittest

from training_pool import VARIANTS, plan
from scenario_project import identifier


class TrainingPool(unittest.TestCase):
    def test_disjoint_worlds_splits_and_fixed_eval(self):
        p = plan()
        self.assertEqual(p, plan())
        self.assertEqual(p["expected_training_candidates"], 240)
        self.assertEqual(p["expected_development_candidates"], 24)
        train = {w["twin_id"] for w in p["worlds"] if w["split"] == "train"}
        dev = {w["twin_id"] for w in p["worlds"] if w["split"] == "dev"}
        self.assertEqual((len(train), len(dev)), (20, 2))
        self.assertFalse(train & dev)
        self.assertFalse((train | dev) & {identifier(s, "project") for s in (41, 42, 43, 47, 53, 54)})

    def test_question_geometry_varies_without_answer_leakage(self):
        p = plan()
        self.assertEqual(len(VARIANTS), 12)
        for family in VARIANTS:
            self.assertEqual(len({w["family_focus"][family] for w in p["worlds"]}), 3)
        self.assertEqual({w["difficulty_target"] for w in p["worlds"]}, {3, 4})
        self.assertTrue(all(len(w["family_focus"]) == 12 for w in p["worlds"]))

    def test_rejects_ambiguous_or_reused_input_ranges(self):
        for kwargs in ({"first_seed": 43}, {"train_worlds": 0}, {"dev_worlds": 0},
                       {"now": "2026-11-02T12:00:00+00:00"}, {"now": "2026-11-02T00:00:00"}):
            with self.assertRaises(ValueError):
                plan(**kwargs)
