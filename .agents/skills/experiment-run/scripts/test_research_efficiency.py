from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("research_efficiency.py")
SPEC = importlib.util.spec_from_file_location("research_efficiency", MODULE_PATH)
assert SPEC and SPEC.loader
efficiency = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(efficiency)


def row(timestamp: str, outer: str, inner: str, **payload: object) -> dict:
    return {
        "timestamp": timestamp,
        "type": outer,
        "payload": {"type": inner, **payload},
    }


class ResearchEfficiencyTests(unittest.TestCase):
    def test_partitions_active_turn_and_summarizes_failed_provider_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollout = root / "rollout-00000000-0000-0000-0000-000000000001.jsonl"
            rows = [
                row("2026-07-14T00:00:00Z", "event_msg", "task_started", turn_id="turn-1"),
                row("2026-07-14T00:00:10Z", "response_item", "function_call", call_id="a", name="exec"),
                row("2026-07-14T00:00:20Z", "response_item", "function_call_output", call_id="a"),
                row("2026-07-14T00:00:30Z", "response_item", "function_call", call_id="b", name="wait"),
                row("2026-07-14T00:01:00Z", "response_item", "function_call_output", call_id="b"),
                row("2026-07-14T00:01:10Z", "event_msg", "task_complete", turn_id="turn-1"),
            ]
            rollout.write_text("".join(json.dumps(item) + "\n" for item in rows))
            allocation = root / "campaign" / "allocations" / "trial-1"
            allocation.mkdir(parents=True)
            events = [
                {"timestamp": "2026-07-14T00:00:00Z", "event": "stock_control"},
                {"timestamp": "2026-07-14T00:00:10Z", "event": "instance_created"},
                {"timestamp": "2026-07-14T00:00:20Z", "event": "ssh_ready"},
                {"timestamp": "2026-07-14T00:00:50Z", "event": "experiment_error"},
                {"timestamp": "2026-07-14T00:00:50Z", "event": "factory_lifecycle", "action": "request-cleanup"},
                {"timestamp": "2026-07-14T00:01:00Z", "event": "cleanup_verified"},
            ]
            (allocation / "events.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in events)
            )
            (allocation / "summary.json").write_text(
                json.dumps({"cost_usd_derived": 0.1, "outcome": "FAIL"})
            )
            (allocation / "factory-result.json").write_text(
                json.dumps({"outcome_class": "operational_failure", "failure_class": "preflight"})
            )
            report = efficiency.build_report(
                rollout,
                since=datetime(2026, 7, 14, tzinfo=timezone.utc),
                now=datetime(2026, 7, 14, 0, 2, tzinfo=timezone.utc),
                campaign_dir=root / "campaign",
                state_db=None,
            )
            self.assertEqual(70.0, report["codex"]["active_seconds"])
            self.assertEqual(40.0, report["codex"]["tool_wait_seconds"])
            self.assertEqual(30.0, report["codex"]["model_orchestration_seconds"])
            self.assertEqual(60.0, report["campaign"]["summary"]["provider_active_seconds"])
            self.assertEqual(0.1, report["campaign"]["summary"]["invalid_or_operational_cost_usd"])
            self.assertIn("prebuild", " ".join(report["efficiency"]["recommendations"]))


if __name__ == "__main__":
    unittest.main()
