"""Exercise the real audit loop with synthetic model/database responses."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import audit_contracts as AC


class AuditRecovery(unittest.TestCase):
    def setUp(self):
        self.base = {"twin_id": "synthetic", "team_id": 7, "loaded_now_utc": "2026-11-01", "shift_days": 0}
        self.proxy = types.ModuleType("llm_proxy")
        self.proxy.judge_complete = Mock(side_effect=[
            (json.dumps({"queries": [{"why": "count", "sql": "SELECT count() FROM events WHERE team_id = {team}"}]}), {}),
            (json.dumps({"verdict": "CLEAN", "defects": [], "summary": "consistent"}), {})])
        ct = types.ModuleType("curate_tasks")
        ct.run_queries = Mock(return_value=[{"why": "count", "sql": "scoped", "result": "[[12]]"}])
        sc = types.ModuleType("spot_card")
        sc.twin_state = sc.event_props = lambda _: []
        sc.team_objects = lambda _: "none"
        sc.clip = lambda value, _: value
        spec = importlib.util.spec_from_file_location("audit_under_test", Path(__file__).with_name("audit_twins.py"))
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"llm_proxy": self.proxy, "curate_tasks": ct, "spot_card": sc}):
            spec.loader.exec_module(self.module)

    def test_failed_cache_is_retried_and_success_then_reused(self):
        with tempfile.TemporaryDirectory() as out:
            path = Path(out) / "synthetic.json"
            path.write_text(json.dumps({"error": "429", "twin_id": "synthetic"}))
            result = self.module.audit(self.base, "author", out)
            self.assertTrue(AC.admissible(result, self.base))
            self.assertEqual(self.proxy.judge_complete.call_count, 2)
            self.module.audit(self.base, "author", out)
            self.assertEqual(self.proxy.judge_complete.call_count, 2)
            self.assertFalse(Path(str(path) + ".tmp").exists())

    def test_provider_failure_exits_without_ten_retry_rounds(self):
        self.proxy.judge_complete.side_effect = RuntimeError("model unavailable")
        with tempfile.TemporaryDirectory() as out:
            result = self.module.audit(self.base, "author", out)
        self.assertIn("unavailable", result["error"])
        self.assertFalse(AC.completed(result))
        self.assertEqual(self.proxy.judge_complete.call_count, 1)

    def test_corrupt_cache_is_recoverable(self):
        with tempfile.TemporaryDirectory() as out:
            (Path(out) / "synthetic.json").write_text("{")
            self.assertTrue(AC.completed(self.module.audit(self.base, "author", out)))


if __name__ == "__main__":
    unittest.main()
