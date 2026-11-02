"""Curator cache boundaries, using synthetic inputs without model/database calls."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class CuratorCache(unittest.TestCase):
    def setUp(self):
        proxy, sc = types.ModuleType("llm_proxy"), types.ModuleType("spot_card")
        self.answer = {"decision": "keep", "turns": ["Compare the reporting cohorts."], "reason": "grounded"}
        proxy.judge_complete = Mock(return_value=(json.dumps(self.answer), {}))
        sc.twin_state = Mock(return_value=["synthetic world"])
        sc.event_props = Mock(return_value=[])
        sc.team_objects = Mock(return_value="baseline objects")
        sc.render_trace = Mock(return_value=["synthetic reference"])
        sc.clip = lambda value, _: value
        spec = importlib.util.spec_from_file_location("curator_under_test", Path(__file__).parents[1] / "curate_tasks.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"llm_proxy": proxy, "spot_card": sc}):
            spec.loader.exec_module(self.module)
        self.proxy, self.sc = proxy, sc
        self.task = {"task_id": "synthetic", "team_id": 7, "twin_id": "world", "conversation_id": "synthetic",
                     "turns": ["Compare the reporting cohorts."], "loaded_now_utc": "2026-11-02T00:00:00Z"}

    def test_legacy_corrupt_and_error_caches_retry(self):
        with tempfile.TemporaryDirectory() as out:
            path = Path(out) / "synthetic.json"
            path.write_text(json.dumps(self.answer))
            r = self.module.curate_one(self.task, None, "curator", out)
            path.write_text("{corrupt")
            self.module.curate_one(self.task, None, "curator", out)
            path.write_text(json.dumps({**r, "error": "provider unavailable"}))
            self.module.curate_one(self.task, None, "curator", out)
        self.assertEqual(self.proxy.judge_complete.call_count, 3)

    def test_task_model_reference_and_feedback_changes_invalidate_same_id(self):
        with tempfile.TemporaryDirectory() as out:
            self.module.curate_one(self.task, None, "curator", out)
            self.module.curate_one(self.task, None, "curator", out)
            self.assertEqual(self.proxy.judge_complete.call_count, 1)
            changed = {**self.task, "turns": ["Compare a different cohort."]}
            self.module.curate_one(changed, None, "curator", out)
            self.module.curate_one(changed, None, "other-curator", out)
            self.module.curate_one(changed, {"id": "different reference"}, "other-curator", out)
            self.module.curate_one(changed, {"id": "different reference"}, "other-curator", out,
                                   feedback={"prev": self.answer, "findings": ["incorrect denominator"]})
        self.assertEqual(self.proxy.judge_complete.call_count, 5)

    def test_live_twin_or_object_changes_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as out:
            self.module.curate_one(self.task, None, "curator", out)
            self.sc.event_props.return_value = ["changed event coverage"]
            self.module.curate_one(self.task, None, "curator", out)
            self.sc.team_objects.return_value = "changed object baseline"
            self.module.curate_one(self.task, None, "curator", out)
        self.assertEqual(self.proxy.judge_complete.call_count, 3)

    def test_complete_negative_result_can_reuse_identical_inputs(self):
        self.proxy.judge_complete.return_value = (json.dumps({"decision": "drop", "reason": "missing recordings"}), {})
        with tempfile.TemporaryDirectory() as out:
            self.module.curate_one(self.task, None, "curator", out)
            self.module.curate_one(self.task, None, "curator", out)
        self.assertEqual(self.proxy.judge_complete.call_count, 1)

    def test_model_cannot_replace_harness_identity_or_query_evidence(self):
        query = {"queries": [{"why": "count", "sql": "SELECT count() FROM events WHERE team_id={team}"}]}
        forged = {**self.answer, "task_id": "other", "model": "other", "input_key": "forged",
                  "queries_run": [{"result": "fabricated"}], "revision": True}
        self.proxy.judge_complete.side_effect = [(json.dumps(query), {}), (json.dumps(forged), {})]
        real = [{"why": "count", "sql": "scoped", "result": "[[12]]"}]
        with tempfile.TemporaryDirectory() as out, patch.object(self.module, "run_queries", return_value=real):
            r = self.module.curate_one(self.task, None, "curator", out)
        self.assertEqual(r["task_id"], self.task["task_id"])
        self.assertEqual(r["model"], "curator")
        self.assertNotEqual(r["input_key"], "forged")
        self.assertEqual(r["queries_run"], real)
        self.assertFalse(r["revision"])


if __name__ == "__main__":
    unittest.main()
