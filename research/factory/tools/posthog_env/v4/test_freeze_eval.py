import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from freeze_eval import digest, eligible, main


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

    def test_full_freeze_binds_taskfile_and_refuses_changed_raw_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.parquet"
            raw.write_bytes(b"synthetic raw fixture")
            (root / "world.json").write_text(json.dumps({"status": "UNSCORED", "files": {
                "raw.parquet": hashlib.sha256(raw.read_bytes()).hexdigest()}}))
            (root / "tasks.jsonl").write_text("".join(json.dumps(t) + "\n" for t in self.tasks))
            (root / "cal.jsonl").write_text(json.dumps({"twin_id": "calibration-only"}) + "\n")
            review = root / "review"
            (review / "reviews").mkdir(parents=True)
            (review / "selection.json").write_text(json.dumps(self.selection))
            (review / "summary.json").write_text(json.dumps(self.review))
            (review / "baseline_objects.json").write_text("{}")
            proof = {"verdict": "SOUND", "queries_run": [{"result": "verified"}],
                     "checks": {"minimal_answer": "concrete answer", "contract_match": "explicit request"}}
            (root / "validation/gate").mkdir(parents=True)
            for t in self.tasks:
                for folder in (root / "validation", root / "validation/gate"):
                    (folder / (t["task_id"] + ".json")).write_text(json.dumps(proof))
            for t in self.tasks[:15]:
                (review / "reviews" / (t["task_id"] + ".json")).write_text(json.dumps(proof))
            protocol = {"arms": {"qwen": 2, "frontier": 1}, "model_identity": {"qwen": "fixture"},
                        "max_turns": 12, "wall_s": 1200, "judge": "fixture", "judge_model": "fixture",
                        "pass_rule": "fixture", "deadline": (dt.datetime.now(dt.timezone.utc)
                                                                 + dt.timedelta(hours=1)).isoformat()}
            (root / "protocol.json").write_text(json.dumps(protocol))
            args = ["freeze_eval", "--tasks", str(root / "tasks.jsonl"), "--world-freeze", str(root / "world.json"),
                    "--review", str(review), "--validation", str(root / "validation"), "--protocol",
                    str(root / "protocol.json"), "--calibration-tasks", str(root / "cal.jsonl"), "--out",
                    str(root / "frozen")]
            with patch("sys.argv", args), patch("builtins.print"):
                main()
            manifest = json.loads((root / "frozen/manifest.json").read_text())
            self.assertEqual(len(manifest["task_ids"]), 24)
            self.assertEqual(manifest["taskfile_sha256"],
                             hashlib.sha256((root / "frozen/tasks.jsonl").read_bytes()).hexdigest())
            raw.write_bytes(b"changed raw fixture")
            args[-1] = str(root / "another-freeze")
            with patch("sys.argv", args), self.assertRaises(ValueError):
                main()
            self.assertFalse((root / "another-freeze").exists())


if __name__ == "__main__":
    unittest.main()
