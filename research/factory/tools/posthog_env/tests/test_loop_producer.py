"""Synthetic producer failures must not publish stale tasks as an accepted batch. No host/model calls."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("loop_producer_under_test", Path(__file__).parents[1] / "loop_producer.py")
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)


class ProducerReadiness(unittest.TestCase):
    def test_failed_required_stages_never_publish_ready_even_with_old_outputs(self):
        stages = ("qfacts.py", "run_all2.py", "load_all_v2.py", "build_tasks_v3.py", "curate_tasks.py",
                  "apply_overrides.py", "validate_tasks.py", "spot_card.py", "bench_env.py")
        for failed in stages:
            with self.subTest(stage=failed), tempfile.TemporaryDirectory() as tmp:
                batch = Path(tmp) / "batch"
                for name in ("tasks/train.jsonl", "curated/curated.jsonl", "validated/validated.jsonl"):
                    p = batch / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps({"task_id": "synthetic"}) + "\n")
                (batch / "READY").write_text("old success")
                calls = []

                def run(cmd, **kwargs):
                    stage = Path(cmd[1]).name
                    calls.append(stage)
                    code = 7 if stage == failed else 0
                    if code and kwargs.get("check"):
                        raise subprocess.CalledProcessError(code, cmd)
                    return subprocess.CompletedProcess(cmd, code, stdout="")

                with patch.object(producer, "BATCHES", tmp), patch.object(producer, "version", return_value={"combined": "test"}), \
                        patch.object(producer, "lint"), patch.object(producer, "refresh_teams"), \
                        patch.object(producer, "regen_pending"), patch.object(producer.subprocess, "run", side_effect=run):
                    with self.assertRaises(subprocess.CalledProcessError):
                        producer.build_batch("batch", ["synthetic"], "train", True)
                self.assertFalse((batch / "READY").exists())
                self.assertEqual(calls[-1], failed)

    def test_successful_pipeline_publishes_valid_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "batch"
            for name in ("tasks/train.jsonl", "curated/curated.jsonl", "validated/validated.jsonl"):
                p = batch / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({"task_id": "synthetic"}) + "\n")
            with patch.object(producer, "BATCHES", tmp), patch.object(producer, "version", return_value={"combined": "test"}), \
                    patch.object(producer, "lint"), patch.object(producer, "refresh_teams"), \
                    patch.object(producer, "regen_pending"), patch.object(producer.subprocess, "run",
                    side_effect=lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="")), patch("builtins.print"):
                producer.build_batch("batch", ["synthetic"], "train", True)
            self.assertEqual(json.loads((batch / "READY").read_text())["included"], 1)
            self.assertFalse((batch / "READY.tmp").exists())

    def test_missing_task_output_is_failure_not_empty_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(producer, "BATCHES", tmp), patch.object(producer, "version", return_value={"combined": "test"}), \
                    patch.object(producer, "lint"), patch.object(producer.subprocess, "run",
                    side_effect=lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="")):
                with self.assertRaises(FileNotFoundError):
                    producer.build_batch("batch", ["synthetic"], "train", False)
            self.assertFalse((Path(tmp) / "batch/READY").exists())

    def test_setup_index_has_no_test_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "twingen/targets.jsonl"
            target.parent.mkdir()
            target.write_text("{}\n")
            with patch.object(producer, "ROOT", tmp), patch.object(producer, "BATCHES", tmp + "/batches"), \
                    patch.object(producer, "sh", return_value=0) as sh, patch("builtins.print"):
                producer.setup()
            index = sh.call_args_list[-1].args[0]
            self.assertEqual(index[-2:], ["--splits", "train,dev"])

    def test_missing_curated_or_validated_output_cannot_fall_back_to_earlier_tasks(self):
        for missing in ("curated/curated.jsonl", "validated/validated.jsonl"):
            with self.subTest(output=missing), tempfile.TemporaryDirectory() as tmp:
                batch = Path(tmp) / "batch"
                for name in ("tasks/train.jsonl", "curated/curated.jsonl", "validated/validated.jsonl"):
                    if name == missing:
                        continue
                    p = batch / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps({"task_id": "synthetic"}) + "\n")
                with patch.object(producer, "BATCHES", tmp), \
                        patch.object(producer, "version", return_value={"combined": "test"}), \
                        patch.object(producer, "lint"), patch.object(producer, "refresh_teams"), \
                        patch.object(producer.subprocess, "run", side_effect=lambda cmd, **kwargs:
                                     subprocess.CompletedProcess(cmd, 0, stdout="")):
                    with self.assertRaises(FileNotFoundError):
                        producer.build_batch("batch", ["synthetic"], "train", False)
                self.assertFalse((batch / "READY").exists())


if __name__ == "__main__":
    unittest.main()
