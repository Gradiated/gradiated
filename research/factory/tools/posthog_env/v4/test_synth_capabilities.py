import importlib.util
from pathlib import Path
import random
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock


class FamilyCapabilities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("synth_under_test", Path(__file__).with_name("synth_tasks.py"))
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {k: types.ModuleType(k) for k in ("llm_proxy", "curate_tasks", "spot_card")}):
            spec.loader.exec_module(cls.module)

    def test_unsupported_families_and_duplicate_jobs_are_excluded(self):
        base = {"supported_families": ["warehouse", "funnel_conversion"]}
        weights = {"warehouse": 1, "funnel_conversion": 1, "session_replay": 100}
        got = self.module.choose_families(base, weights, 5, random.Random(1), set())
        self.assertEqual(set(got), {"warehouse", "funnel_conversion"})
        self.assertEqual(len(got), 2)

    def test_explicit_empty_capabilities_do_not_enable_everything(self):
        self.assertEqual(self.module.choose_families({"supported_families": []}, {"warehouse": 1}, 3,
                                                    random.Random(1), set()), [])

    def test_requested_calibration_subset_is_respected(self):
        got = self.module.choose_families({}, {"warehouse": 1, "funnel_conversion": 1}, 3,
                                          random.Random(1), {"warehouse"})
        self.assertEqual(got, ["warehouse"])

    def test_author_executes_queries_before_accepting_proposed_task(self):
        q = {"queries": [{"why": "count", "sql": "SELECT count() FROM events WHERE team_id={team}"}]}
        task = {"turns": ["Compare the reporting cohorts."], "grading_notes": {"must_include": ["findings"]},
                "key": "model-key", "twin_id": "wrong", "queries_run": [{"result": "fabricated"}]}
        proxy, ct, sc = self.module.llm_proxy, self.module.CT, self.module.SC
        proxy.judge_complete = Mock(side_effect=[(json.dumps({**q, **task}), {}), (json.dumps(task), {})])
        ct.run_queries = Mock(return_value=[{"why": "count", "sql": "scoped", "result": "[[12]]"}])
        sc.twin_state = sc.event_props = lambda _: []
        sc.team_objects = lambda _: "none"
        sc.clip = lambda value, _: value
        with tempfile.TemporaryDirectory() as out, patch.object(self.module, "exemplars", return_value=[]):
            rec = self.module.author({"twin_id": "synthetic", "team_id": 7}, "warehouse", 4,
                                     random.Random(1), "author", out)
        self.assertEqual(rec["twin_id"], "synthetic")
        self.assertNotEqual(rec["key"], "model-key")
        self.assertEqual(rec["queries_run"][0]["result"], "[[12]]")
        self.assertEqual(proxy.judge_complete.call_count, 2)


if __name__ == "__main__":
    unittest.main()
