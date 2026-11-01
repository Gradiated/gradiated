import unittest

from task_quality import pass_result, summarize


def task(tid, family="funnel_conversion"):
    return {"task_id": tid, "twin_id": "twin-" + tid, "split": "train", "validation": {"verdict": "SOUND"},
            "synth": {"family": family}, "curation": {"difficulty": "hard"}}


class TaskQuality(unittest.TestCase):
    def test_failed_or_missing_measurements_do_not_count_as_student_failure(self):
        judge = {"overall": 9, "material_wrong_final": 0, "material_unsupported_final": 0}
        self.assertTrue(pass_result(judge, {"status": "ok"}))
        self.assertIsNone(pass_result(judge, {"status": "infra_error"}))
        self.assertIsNone(pass_result(judge, None))
        self.assertIsNone(pass_result({"overall": 9}, {"status": "ok"}))
        self.assertIsNone(pass_result({**judge, "overall": float("nan")}, {"status": "ok"}))
        self.assertFalse(pass_result({**judge, "material_wrong_final": 1}, {"status": "ok"}))

    def test_complete_pair_requirement_and_equal_task_weights(self):
        tasks = [task("a"), task("b", "retention_engagement"), task("c")]
        results = {("a", "qwen", 0): False, ("a", "qwen", 1): True, ("a", "opus", 0): True,
                   ("b", "qwen", 0): False, ("b", "qwen", 1): False, ("b", "opus", 0): True,
                   ("c", "opus", 0): True}
        r = summarize(tasks, results, "qwen", "opus", {"qwen": 2, "opus": 1})
        self.assertEqual(r["tasks_eligible"], 3)
        self.assertEqual(r["paired"]["complete_tasks"], 2)
        self.assertEqual(r["paired"]["frontier_minus_student"], .75)
        self.assertEqual(r["excluded"]["incomplete_pair"], 1)
        self.assertEqual(r["families"]["funnel_conversion"]["eligible_tasks"], 2)

    def test_no_evidence_has_null_rates(self):
        r = summarize([task("a")], {}, "qwen", "opus", {"qwen": 2, "opus": 1})
        self.assertIsNone(r["paired"]["frontier_minus_student"])

    def test_invalid_and_duplicate_tasks_cannot_inflate_coverage(self):
        t = task("a")
        with self.assertRaises(ValueError):
            summarize([t, t], {}, "qwen", "opus", {"qwen": 1, "opus": 1})
        t["exclude"] = "bad premise"
        r = summarize([t], {}, "qwen", "opus", {"qwen": 1, "opus": 1})
        self.assertEqual(r["tasks_eligible"], 0)


if __name__ == "__main__":
    unittest.main()
