import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class TaskValidation(unittest.TestCase):
    def setUp(self):
        self.proxy = types.ModuleType("llm_proxy")
        self.query = {"queries": [{"why": "count", "sql": "SELECT count() FROM events WHERE team_id=7"}]}
        self.final = {"verdict": "SOUND", "defects": [], "checks": {"data": "ok"}, "summary": "verified"}
        self.proxy.judge_complete = Mock(side_effect=[(json.dumps({**self.query, **self.final}), {}),
                                                     (json.dumps(self.final), {})])
        ct = types.ModuleType("curate_tasks")
        ct.run_queries = Mock(return_value=[{"why": "count", "sql": "scoped", "result": "[[12]]"}])
        sc = types.ModuleType("spot_card")
        sc.twin_state = sc.event_props = sc.render_trace = lambda *args: []
        sc.team_objects = lambda _: "none"
        sc.clip = lambda value, _: value
        spec = importlib.util.spec_from_file_location("validator_under_test", Path(__file__).parents[1] / "validate_tasks.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"llm_proxy": self.proxy, "curate_tasks": ct, "spot_card": sc}):
            spec.loader.exec_module(self.module)
        self.task = {"task_id": "synthetic", "conversation_id": "synthetic", "team_id": 7,
                     "turns": ["Compare the cohorts"], "grading_notes": {"must_include": ["findings"]}}

    def test_failed_or_legacy_cache_retries_and_complete_cache_reuses(self):
        with tempfile.TemporaryDirectory() as out:
            (Path(out) / "synthetic.json").write_text(json.dumps({"verdict": "SOUND"}))
            r = self.module.validate_one(self.task, None, "validator", out)
            self.assertTrue(self.module.validation_complete(r))
            self.module.validate_one(self.task, None, "validator", out)
        self.assertEqual(self.proxy.judge_complete.call_count, 2)
        self.assertIn("{team}", self.module.CT.run_queries.call_args[0][0][0]["sql"])

    def test_changed_notes_invalidate_successful_cache(self):
        self.proxy.judge_complete.side_effect = [(json.dumps(self.query), {}), (json.dumps(self.final), {})] * 2
        with tempfile.TemporaryDirectory() as out:
            self.module.validate_one(self.task, None, "validator", out)
            changed = {**self.task, "grading_notes": {"must_include": ["different verified findings"]}}
            self.module.validate_one(changed, None, "validator", out)
        self.assertEqual(self.proxy.judge_complete.call_count, 4)

    def test_model_evidence_without_execution_is_not_accepted(self):
        self.proxy.judge_complete.side_effect = None
        self.proxy.judge_complete.return_value = (json.dumps({**self.final, "queries_run": [{"result": "[[0]]"}]}), {})
        with tempfile.TemporaryDirectory() as out:
            r = self.module.validate_one(self.task, None, "validator", out)
        self.assertFalse(self.module.validation_complete(r))
        self.assertEqual(r["queries_run"], [])

    def test_sound_cannot_hide_defects(self):
        r = {**self.final, "queries_run": [{"result": "[[12]]"}],
             "defects": [{"what": "incorrect grading numbers", "evidence": "query -> 12"}]}
        self.assertFalse(self.module.validation_complete(r))
        r["verdict"] = "BROKEN"
        self.assertTrue(self.module.validation_complete(r))

    def test_independent_review_uses_frozen_object_context(self):
        self.module.SC.team_objects = Mock(side_effect=RuntimeError("mutable objects must not be read"))
        task = {**self.task, "_audit_objects_snapshot": "frozen baseline objects"}
        with tempfile.TemporaryDirectory() as out:
            r = self.module.validate_one(task, None, "validator", out)
        self.assertTrue(self.module.validation_complete(r))
        self.module.SC.team_objects.assert_not_called()

    def test_required_contract_checks_cannot_be_omitted(self):
        missing = self.final
        complete = {**self.final, "checks": {"data": "ok", "minimal_answer": "The minimum correct findings"}}
        self.proxy.judge_complete.side_effect = [(json.dumps(self.query), {}), (json.dumps(missing), {}),
                                               (json.dumps(complete), {})]
        with tempfile.TemporaryDirectory() as out:
            r = self.module.validate_one(self.task, None, "validator", out, required_checks=("minimal_answer",))
        self.assertEqual(self.proxy.judge_complete.call_count, 3)
        self.assertTrue(self.module.has_checks(r, ("minimal_answer",)))


if __name__ == "__main__":
    unittest.main()
