import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validation.qwen_vllm_repeatability.host import HostSnapshot, ProcessRecord
from validation.qwen_vllm_repeatability.runner import wait_for_clean_host
from validation.qwen_vllm_repeatability.schema import CampaignSpec
from validation.qwen_vllm_repeatability.tests.test_schema import valid_mapping


def host_snapshot(cpu_percent: float) -> HostSnapshot:
    return HostSnapshot(
        captured_at="2026-07-12T00:00:00Z",
        ac_power=True,
        thermal_warning=False,
        available_memory_bytes=20_000_000_000,
        load_average=(1.0, 1.0, 1.0),
        processes=(ProcessRecord(99, 1, cpu_percent, 1_000, "external"),),
        raw_commands={},
    )


class WaitForCleanHostTests(unittest.TestCase):
    def setUp(self) -> None:
        mapping = valid_mapping()
        mapping["isolation"]["quiet_sample_interval_seconds"] = 1
        mapping["isolation"]["preflight_wait_timeout_seconds"] = 10
        self.spec = CampaignSpec.from_mapping(mapping)

    def test_requires_consecutive_clean_samples_and_persists_each_decision(
        self,
    ) -> None:
        snapshots = [
            host_snapshot(25.0),
            host_snapshot(0.0),
            host_snapshot(0.0),
            host_snapshot(0.0),
        ]
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            with (
                patch(
                    "validation.qwen_vllm_repeatability.runner.capture_host_state",
                    side_effect=snapshots,
                ),
                patch(
                    "validation.qwen_vllm_repeatability.runner.time.monotonic",
                    side_effect=[0.0, 0.0, 1.0, 2.0, 3.0],
                ),
                patch("validation.qwen_vllm_repeatability.runner.time.sleep"),
            ):
                report = wait_for_clean_host(self.spec, output_root)

            self.assertTrue(report["accepted"])
            self.assertEqual(report["sample_count"], 4)
            self.assertEqual(report["consecutive_clean_samples"], 3)
            samples = sorted((output_root / "wait-preflight").glob("sample-*.json"))
            self.assertEqual(len(samples), 4)
            first = json.loads(samples[0].read_text(encoding="utf-8"))
            self.assertFalse(first["isolation"]["accepted"])
            self.assertTrue((output_root / "wait-preflight" / "accepted.json").exists())

    def test_timeout_persists_failure_and_never_accepts_dirty_host(self) -> None:
        mapping = valid_mapping()
        mapping["isolation"]["quiet_sample_interval_seconds"] = 1
        mapping["isolation"]["preflight_wait_timeout_seconds"] = 2
        spec = CampaignSpec.from_mapping(mapping)
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            with (
                patch(
                    "validation.qwen_vllm_repeatability.runner.capture_host_state",
                    side_effect=[host_snapshot(25.0)] * 3,
                ),
                patch(
                    "validation.qwen_vllm_repeatability.runner.time.monotonic",
                    side_effect=[0.0, 0.0, 1.0, 2.0],
                ),
                patch("validation.qwen_vllm_repeatability.runner.time.sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    wait_for_clean_host(spec, output_root)

            failure = json.loads(
                (output_root / "wait-preflight" / "timeout.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(failure["accepted"])
            self.assertEqual(failure["sample_count"], 3)

    def test_timeout_writes_compact_durable_result_and_archives_raw_evidence(
        self,
    ) -> None:
        mapping = valid_mapping()
        mapping["isolation"]["quiet_sample_interval_seconds"] = 1
        mapping["isolation"]["preflight_wait_timeout_seconds"] = 2
        spec = CampaignSpec.from_mapping(mapping)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "raw"
            durable_path = root / "result.json"
            archive_root = root / "archive"
            accepted_index = output_root / "accepted-pairs" / "c8-r1.json"
            accepted_index.parent.mkdir(parents=True)
            accepted_index.write_text('{"pair_id":"c8-r1"}\n', encoding="utf-8")
            raw_spec = {
                "durable_report_path": str(durable_path),
                "archive_root": str(archive_root),
                "prior_evidence_roots": [],
            }
            with (
                patch(
                    "validation.qwen_vllm_repeatability.runner.capture_host_state",
                    side_effect=[host_snapshot(25.0)] * 3,
                ),
                patch(
                    "validation.qwen_vllm_repeatability.runner.time.monotonic",
                    side_effect=[0.0, 0.0, 1.0, 2.0],
                ),
                patch("validation.qwen_vllm_repeatability.runner.time.sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    wait_for_clean_host(spec, output_root, raw_spec)

            result = json.loads(durable_path.read_text(encoding="utf-8"))
            identity = dict(result)
            content_id = identity.pop("content_id")
            expected_content_id = hashlib.sha256(
                json.dumps(
                    identity,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(content_id, expected_content_id)
            self.assertEqual(result["terminal_status"], "host_contamination_blocked")
            self.assertFalse(result["campaign_accepted"])
            self.assertEqual(result["progress"]["accepted_pair_count"], 1)
            self.assertEqual(result["progress"]["new_measured_run_count"], 0)
            self.assertEqual(result["evidence"]["wait_sample_count"], 3)
            self.assertEqual(len(result["evidence"]["wait_samples_content_id"]), 64)
            self.assertTrue((archive_root / "wait-preflight" / "timeout.json").exists())
            self.assertTrue((archive_root / "accepted-pairs" / "c8-r1.json").exists())


if __name__ == "__main__":
    unittest.main()
