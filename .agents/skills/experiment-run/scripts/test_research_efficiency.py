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

    def test_discovers_research_lab_artifacts_and_aggregates_typed_phases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = root / "glm" / "campaign_100"
            campaign.mkdir(parents=True)
            artifact = root / "glm" / "research_lab" / "projects" / "candidate" / "artifacts" / "run-1"
            artifact.mkdir(parents=True)
            events = [
                {"timestamp": "2026-07-14T00:00:00Z", "event": "stock_control"},
                {"timestamp": "2026-07-14T00:00:10Z", "event": "instance_created"},
                {"timestamp": "2026-07-14T00:00:10Z", "event": "phase_started", "phase": "runtime_bootstrap"},
                {"timestamp": "2026-07-14T00:02:10Z", "event": "phase_finished", "phase": "runtime_bootstrap", "outcome": "FAIL"},
                {"timestamp": "2026-07-14T00:02:20Z", "event": "cleanup_verified"},
            ]
            (artifact / "events.jsonl").write_text("".join(json.dumps(item) + "\n" for item in events))
            (artifact / "summary.json").write_text(json.dumps({"outcome": "FAIL", "cost_usd_derived": 0.2}))
            result = efficiency.analyze_campaign(
                campaign,
                since=datetime(2026, 7, 14, tzinfo=timezone.utc),
                now=datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(len(result["allocations"]), 1)
        self.assertEqual(result["allocations"][0]["phase_seconds"]["runtime_bootstrap"], 120.0)
        self.assertEqual(result["allocations"][0]["failed_phase"], "runtime_bootstrap")
        self.assertEqual(result["summary"]["pre_science_failure_count"], 1)
        self.assertEqual(result["summary"]["pre_science_failure_provider_seconds"], 140.0)

    def test_valid_allocation_result_counts_as_science_despite_legacy_fail_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allocation = root / "campaign" / "allocations" / "background-c16"
            allocation.mkdir(parents=True)
            events = [
                {"timestamp": "2026-07-14T00:00:00Z", "event": "stock_control"},
                {"timestamp": "2026-07-14T00:02:00Z", "event": "cleanup_verified"},
            ]
            (allocation / "events.jsonl").write_text("".join(json.dumps(item) + "\n" for item in events))
            (allocation / "summary.json").write_text(
                json.dumps(
                    {
                        "outcome": "FAIL",
                        "cost_usd_derived": 0.2,
                        "allocation_result": {
                            "batch_pass": False,
                            "performance": {"profiles": [{"wall_seconds": 61.216}]},
                            "semantic": {"pass": True},
                        },
                    }
                )
            )
            result = efficiency.analyze_campaign(
                root / "campaign",
                since=datetime(2026, 7, 14, tzinfo=timezone.utc),
                now=datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(result["summary"]["scientific_outcomes"], 1)
        self.assertEqual(result["summary"]["invalid_or_operational_outcomes"], 0)
        self.assertEqual(result["summary"]["useful_gpu_seconds_observed"], 61.216)

    def test_project_owner_cleanup_file_closes_pre_science_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "research_lab" / "projects" / "candidate" / "artifacts" / "run-1"
            artifact.mkdir(parents=True)
            events = [
                {"timestamp": "2026-07-14T00:00:00Z", "event": "owner_started"},
                {"timestamp": "2026-07-14T00:00:40Z", "event": "instance_created"},
                {
                    "timestamp": "2026-07-14T00:01:15Z",
                    "event": "owner_error",
                    "error_type": "CalledProcessError",
                },
            ]
            (artifact / "events.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in events)
            )
            (artifact / "failure.json").write_text(
                json.dumps({"error_type": "CalledProcessError", "message": "scp failed"})
            )
            (artifact / "cleanup.json").write_text(
                json.dumps(
                    {
                        "cleanup_pass": True,
                        "cleanup_elapsed_seconds": 15.0,
                        "verified_at_utc": "2026-07-14T00:01:30Z",
                    }
                )
            )
            result = efficiency.analyze_campaign(
                root / "research_lab",
                since=datetime(2026, 7, 14, tzinfo=timezone.utc),
                now=datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(result["summary"]["completed_allocations"], 1)
        self.assertEqual(result["summary"]["invalid_or_operational_outcomes"], 1)
        self.assertEqual(result["summary"]["pre_science_failure_count"], 1)
        self.assertEqual(result["summary"]["provider_active_seconds"], 90.0)
        self.assertEqual(result["allocations"][0]["outcome"], "operational_failure")
        self.assertEqual(result["allocations"][0]["failed_phase"], "ssh_readiness")
        self.assertEqual(result["allocations"][0]["cleanup_seconds"], 15.0)

    def test_typed_stage_records_count_as_science_and_report_useful_gpu_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "research_lab" / "projects" / "candidate" / "artifacts" / "run-1"
            artifact.mkdir(parents=True)
            events = [
                {"timestamp": "2026-07-14T00:00:00Z", "event": "instance_created"},
                {"timestamp": "2026-07-14T00:10:00Z", "event": "cleanup_verified"},
            ]
            (artifact / "events.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in events)
            )
            (artifact / "summary.json").write_text(
                json.dumps(
                    {
                        "outcome": "PASS",
                        "cost_usd_derived": 0.1,
                        "stage_records": [
                            {
                                "label": "primary",
                                "returncode": 0,
                                "terminal": {
                                    "pass": True,
                                    "result": {
                                        "pass": True,
                                        "rows": [{"m": 1, "cuda_event_ms": {"p50": 3.9}}],
                                        "useful_gpu_seconds": 1.401232476,
                                    },
                                },
                            }
                        ],
                    }
                )
            )
            result = efficiency.analyze_campaign(
                root / "research_lab",
                since=datetime(2026, 7, 14, tzinfo=timezone.utc),
                now=datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(result["summary"]["scientific_outcomes"], 1)
        self.assertEqual(result["summary"]["invalid_or_operational_outcomes"], 0)
        self.assertEqual(result["summary"]["useful_gpu_seconds_observed"], 1.401)
        self.assertEqual(result["summary"]["useful_gpu_to_provider_fraction"], 0.0023)
        self.assertEqual(
            result["allocations"][0]["useful_gpu_seconds_source"],
            "stage_records[].terminal.result.useful_gpu_seconds",
        )

    def test_project_terminal_scope_rejection_overrides_inferred_science(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "research_lab" / "projects" / "candidate"
            artifact = project / "artifacts" / "run-1"
            artifact.mkdir(parents=True)
            events = [
                {"timestamp": "2026-07-14T00:00:00Z", "event": "instance_created"},
                {"timestamp": "2026-07-14T00:10:00Z", "event": "cleanup_verified"},
            ]
            (artifact / "events.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in events)
            )
            (artifact / "summary.json").write_text(
                json.dumps(
                    {
                        "outcome": "PASS",
                        "allocation_result": {
                            "performance": {"profiles": [{"wall_seconds": 3.291}]}
                        },
                    }
                )
            )
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "last_result_classification": "terminal_partial_mechanism_pass_exact_shape_claim_rejected",
                        "terminal_artifact": "artifacts/run-1/summary.json",
                    }
                )
            )
            result = efficiency.analyze_campaign(
                root / "research_lab",
                since=datetime(2026, 7, 14, tzinfo=timezone.utc),
                now=datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(result["summary"]["scientific_outcomes"], 0)
        self.assertEqual(result["summary"]["invalid_or_operational_outcomes"], 1)
        self.assertEqual(result["summary"]["useful_gpu_seconds_observed"], 0)
        self.assertEqual(result["allocations"][0]["outcome"], "scope_rejected_result")

    def test_tracks_live_owner_timestamp_utc_and_provider_created_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "research_lab" / "projects" / "candidate" / "artifacts" / "run-1"
            artifact.mkdir(parents=True)
            events = [
                {"timestamp_utc": "2026-07-14T00:00:00Z", "event": "owner_started"},
                {"timestamp_utc": "2026-07-14T00:00:45Z", "event": "provider_created"},
                {"timestamp_utc": "2026-07-14T00:01:20Z", "event": "ssh_ready"},
            ]
            (artifact / "events.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in events)
            )
            result = efficiency.analyze_campaign(
                root / "research_lab",
                since=datetime(2026, 7, 14, tzinfo=timezone.utc),
                now=datetime(2026, 7, 14, 0, 2, tzinfo=timezone.utc),
            )
        self.assertEqual(len(result["allocations"]), 1)
        self.assertFalse(result["allocations"][0]["completed"])
        self.assertEqual(result["allocations"][0]["provider_active_seconds"], 120.0)
        self.assertEqual(result["allocations"][0]["provisioning_seconds"], 45.0)
        self.assertEqual(result["allocations"][0]["ssh_ready_seconds"], 35.0)
        self.assertEqual(result["allocations"][0]["outcome"], "in_progress")


if __name__ == "__main__":
    unittest.main()
