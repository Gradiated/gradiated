import unittest

from rejudge import blinded, key_for


class SecondaryJudge(unittest.TestCase):
    def test_arm_labels_removed_without_altering_observed_work(self):
        trace = {"model": "frontier", "arm": "frontier", "provider": "provider", "status": "ok",
                 "messages": [{"type": "ToolMessage", "content": "AI model swift-small cost 0.25"}]}
        result = blinded(trace, {"grading_notes": {"must_include": ["cost"]}})
        self.assertNotIn("arm", result)
        self.assertNotIn("model", result)
        self.assertNotIn("provider", result)
        self.assertEqual(result["messages"], trace["messages"])
        self.assertIn("model", trace)

    def test_judge_and_task_changes_invalidate_cache(self):
        tr, task = {"messages": []}, {"task_id": "a"}
        key = key_for(tr, task, "judge-a", "v3i")
        self.assertNotEqual(key, key_for(tr, task, "judge-b", "v3i"))
        self.assertNotEqual(key, key_for(tr, {**task, "grading_notes": "changed"}, "judge-a", "v3i"))


if __name__ == "__main__":
    unittest.main()
