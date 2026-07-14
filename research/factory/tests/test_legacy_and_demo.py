from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from grad_research.demo import run_demo
from grad_research.events import EventStore
from grad_research.legacy import classify_legacy_event, import_legacy_campaign, replay_legacy_ledger
from grad_research.util import ValidationError


class LegacyAndDemoTests(unittest.TestCase):
    def test_glm_campaign_replays_without_promoting_legacy_claims(self):
        workspace = Path(__file__).resolve().parents[3]
        ledger = workspace / "research/sol/experiments/glm47flash/campaign_100/CAMPAIGN_LEDGER.jsonl"
        source_count = sum(1 for line in ledger.read_text().splitlines() if line.strip())
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(directory, "glm47-legacy")
            summary = replay_legacy_ledger(ledger, store)
            state = store.project()
            self.assertEqual(source_count, summary["source_event_count"])
            self.assertGreaterEqual(source_count, 82)
            self.assertEqual(source_count, state["legacy"]["event_count"])
            self.assertGreaterEqual(state["legacy"]["cumulative_spend_usd"], 17.656500383)
            self.assertGreater(state["legacy"]["outcome_counts"]["harness_invalid"], 0)
            self.assertGreater(state["legacy"]["outcome_counts"]["operational_failure"], 0)
            self.assertGreater(state["legacy"]["outcome_counts"]["scientific_negative"], 0)
            self.assertEqual({}, state["mechanism_beliefs"])

            repeated = replay_legacy_ledger(ledger, store)
            self.assertEqual(0, repeated["events_appended"])
            self.assertEqual(source_count, store.project()["legacy"]["event_count"])

    def test_key_glm_outcomes_and_final_resume_state_are_normalized(self):
        workspace = Path(__file__).resolve().parents[3]
        campaign = workspace / "research/sol/experiments/glm47flash/campaign_100"
        rows = [json.loads(line) for line in (campaign / "CAMPAIGN_LEDGER.jsonl").read_text().splitlines()]
        self.assertEqual("operational_failure", classify_legacy_event(rows[61]))
        self.assertEqual("scientific_negative", classify_legacy_event(rows[67]))
        self.assertEqual("scientific_positive", classify_legacy_event(rows[73]))
        self.assertEqual("harness_invalid", classify_legacy_event(rows[74]))
        self.assertEqual("scientific_negative", classify_legacy_event(rows[81]))

        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(directory, "glm47-resume")
            first = import_legacy_campaign(
                campaign / "CAMPAIGN_LEDGER.jsonl",
                campaign / "CAMPAIGN_STATUS.json",
                campaign / "DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json",
                store,
            )
            event_count = store.project()["event_count"]
            second = import_legacy_campaign(
                campaign / "CAMPAIGN_LEDGER.jsonl",
                campaign / "CAMPAIGN_STATUS.json",
                campaign / "DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json",
                store,
            )
            state = store.project()
            self.assertTrue(first["snapshot_appended"])
            self.assertFalse(second["snapshot_appended"])
            self.assertEqual(event_count, state["event_count"])
            self.assertEqual("CONTINUE_NARROWLY", state["legacy"]["campaign_decision"])
            self.assertEqual("STOP_NUM_KV_SPLITS_8", state["legacy"]["lineage_decision"])
            self.assertEqual("SPLIT8_STOP_DENSE_RESIDUAL_AND_QUALITY_CALIBRATION_NEXT", state["legacy"]["phase"])
            self.assertFalse(state["legacy"]["claims_permitted"])
            self.assertEqual("nebius_l40s_vllm_awq_splits_ab_v28r1", state["legacy"]["last_experiment_id"])
            self.assertIn("Dense GEMM/GEMV", state["residual_bottleneck"])
            self.assertIn("Calibrate", state["next_action"])
            self.assertEqual(25.0, state["legacy"]["budgets"]["nebius"]["authorized_usd"])
            self.assertEqual([], state["legacy"]["cleanup"]["active_pods"])

    def test_legacy_replay_accepts_append_only_growth_and_rejects_rewrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "ledger.jsonl"
            first_row = {"timestamp": "2026-07-14T00:00:00Z", "event": "scientific_positive"}
            second_row = {"timestamp": "2026-07-14T00:01:00Z", "event": "below_gate"}
            ledger.write_text(json.dumps(first_row) + "\n")
            store = EventStore(root / "state", "append-only")
            self.assertEqual(1, replay_legacy_ledger(ledger, store)["events_appended"])
            ledger.write_text(json.dumps(first_row) + "\n" + json.dumps(second_row) + "\n")
            self.assertEqual(1, replay_legacy_ledger(ledger, store)["events_appended"])
            self.assertEqual(2, store.project()["legacy"]["event_count"])

            rewritten = {**first_row, "event": "scientific_negative"}
            ledger.write_text(json.dumps(rewritten) + "\n" + json.dumps(second_row) + "\n")
            with self.assertRaisesRegex(ValidationError, "line 1 changed"):
                replay_legacy_ledger(ledger, store)

            ledger.write_text(json.dumps(first_row) + "\n")
            with self.assertRaisesRegex(ValidationError, "truncated"):
                replay_legacy_ledger(ledger, store)

    def test_demo_completes_two_loops_and_cleans_runtime_state(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory))
            state = result["state"]
            self.assertGreaterEqual(state["current_cycle"], 2)
            self.assertGreaterEqual(state["research_metrics"]["valid_scientific_outcomes"], 2)
            self.assertEqual(1, state["outcome_counts"]["harness_invalid"])
            self.assertEqual("cleaned", result["lab_snapshot"]["allocations"][0]["state"])
            self.assertIn("residual", result["coordinator_context"].lower())


if __name__ == "__main__":
    unittest.main()
