import copy
import unittest

from freeze_eval import digest, eligible


class EvaluationAdmission(unittest.TestCase):
    def setUp(self):
        self.tasks = [{"task_id": str(i), "twin_id": str(i % 2), "split": "test",
                       "synth": {"family": str(i % 12)}, "validation": {"verdict": "SOUND"}} for i in range(24)]
        self.selection = {"task_hashes": {t["task_id"]: digest(t) for t in self.tasks[:15]}}
        self.review = {"quality_bar_met": True, "results": [{"task_id": str(i), "verdict": "SOUND",
                        "contract_checks": True, "query_count": 3} for i in range(15)]}

    def test_quality_failure_excluded_without_model_score_selection(self):
        self.review["results"][0]["verdict"] = "MINOR"
        chosen = eligible(self.tasks, self.selection, self.review, set(), 12)
        self.assertEqual(len(chosen), 23)
        self.assertNotIn("0", {t["task_id"] for t in chosen})
        self.assertEqual(len({t["synth"]["family"] for t in chosen}), 12)

    def test_quality_or_task_changes_cannot_reuse_freeze_admission(self):
        self.review["results"][0]["verdict"] = "MINOR"
        self.review["results"][1]["verdict"] = "BROKEN"
        with self.assertRaises(ValueError):
            eligible(self.tasks, self.selection, self.review, set(), 12)
        changed = copy.deepcopy(self.tasks)
        changed[0]["turns"] = ["different request"]
        with self.assertRaises(ValueError):
            eligible(changed, self.selection, self.review, set(), 12)

    def test_calibration_overlap_or_insufficient_breadth_rejected(self):
        with self.assertRaises(ValueError):
            eligible(self.tasks, self.selection, self.review, {"0"}, 12)
        with self.assertRaises(ValueError):
            eligible(self.tasks, self.selection, self.review, set(), 13)


if __name__ == "__main__":
    unittest.main()
