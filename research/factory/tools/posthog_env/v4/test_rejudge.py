import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from rejudge import blinded, key_for, main


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

    def test_cli_reuses_same_samples_and_reports_secondary_paired_gap(self):
        def score(trace, model):
            self.assertNotIn("model", trace)
            self.assertEqual(model, "independent-judge")
            correct = trace["messages"][0]["content"] == "correct"
            return {"overall": 9 if correct else 4, "material_wrong_final": 0 if correct else 1,
                    "material_unsupported_final": 0}

        judge = types.SimpleNamespace(score_transcript=Mock(side_effect=score))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = {"task_id": "task", "twin_id": "world", "split": "test", "validation": {"verdict": "SOUND"},
                    "grading_notes": {"must_include": ["correct finding"]}, "synth": {"family": "warehouse"}}
            (root / "tasks.jsonl").write_text(json.dumps(task) + "\n")
            for arm, answer in (("qwen", "wrong"), ("gpt-sol", "correct")):
                p = root / "bench" / arm / "runs/task/r0.json"
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps({"model": arm, "status": "ok", "messages": [{"content": answer}]}))
            args = ["rejudge", "--tasks", str(root / "tasks.jsonl"), "--bench", str(root / "bench"), "--out",
                    str(root / "secondary"), "--judge-model", "independent-judge", "--student-samples", "1"]
            with patch("sys.argv", args), patch("rejudge.importlib.import_module", return_value=judge), patch("builtins.print"):
                main()
                main()
            self.assertEqual(judge.score_transcript.call_count, 2)
            report = json.loads((root / "secondary/quality_report.json").read_text())
            self.assertEqual(report["paired"]["complete_tasks"], 1)
            self.assertEqual(report["paired"]["frontier_minus_student"], 1)


if __name__ == "__main__":
    unittest.main()
