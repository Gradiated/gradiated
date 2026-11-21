import hashlib
import json
import signal
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from snapshot import verify_snapshot
from train import (
    bounded_checkpoint_write,
    build_run_identity,
    check_deadline,
    learning_rate_for_step,
    parse_s3_uri,
    startup_deadline,
    validate_experiment_bounds,
    validate_output_reuse,
)


class RunnerValidationTests(unittest.TestCase):
    def test_slow_startup_is_interrupted_and_alarm_restored(self):
        previous = signal.getsignal(signal.SIGALRM)
        with (
            self.assertRaisesRegex(TimeoutError, "startup"),
            startup_deadline(time.monotonic() + 0.03),
        ):
            time.sleep(0.2)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)

    def test_startup_deadline_remains_active_across_restoration_phases(self):
        completed = []
        with (
            self.assertRaisesRegex(TimeoutError, "startup"),
            startup_deadline(time.monotonic() + 0.08),
        ):
            time.sleep(0.01)
            completed.append("checkpoint verification")
            time.sleep(0.2)
            completed.append("optimizer restoration")
        self.assertEqual(completed, ["checkpoint verification"])
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_nonresume_reuse_of_training_artifacts_fails_before_model_load(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "baseline-dev.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "matching identity"):
                validate_output_reuse(output, None)
            (output / "identity.json").write_text("{}")
            validate_output_reuse(output, None)
            checkpoint = output / "checkpoint-00001"
            checkpoint.mkdir()
            (checkpoint / "checkpoint-complete.json").write_text(
                json.dumps({"step": 1})
            )
            with self.assertRaisesRegex(ValueError, "already contains"):
                validate_output_reuse(output, None)
            validate_output_reuse(output, str(checkpoint))

    def test_resuming_before_later_checkpoints_fails_up_front(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            resume = root / "checkpoint-00001"
            resume.mkdir()
            (resume / "checkpoint-complete.json").write_text(json.dumps({"step": 1}))
            (root / "checkpoint-00100.tmp").mkdir()
            with self.assertRaisesRegex(ValueError, "later checkpoint"):
                validate_output_reuse(root, str(resume))
            fresh = root / "fresh-output"
            fresh.mkdir()
            validate_output_reuse(fresh, str(resume))

    def test_snapshot_checks_expired_owner_before_verification(self):
        def expired():
            raise TimeoutError("snapshot owner deadline")

        with self.assertRaisesRegex(TimeoutError, "snapshot owner deadline"):
            verify_snapshot(Path("unused-snapshot"), expired)

    def test_checkpoint_is_skipped_near_the_evaluation_reserve(self):
        called = []
        with self.assertRaises(TimeoutError):
            bounded_checkpoint_write(
                lambda: called.append(True), time.monotonic() + 930
            )
        self.assertFalse(called)

    def test_slow_checkpoint_write_is_interrupted_before_publication(self):
        with TemporaryDirectory() as directory:
            complete = Path(directory) / "checkpoint-complete.json"
            old_handler = signal.getsignal(signal.SIGALRM)

            def slow_write():
                time.sleep(1)
                complete.write_text("{}")

            # Bypass only the conservative preflight margin to exercise the
            # actual timer with a short wall-clock deadline.
            with patch("train.check_deadline"), self.assertRaises(TimeoutError):
                bounded_checkpoint_write(slow_write, time.monotonic() + 0.03, reserve=0)
            self.assertFalse(complete.exists())
            self.assertEqual(signal.getsignal(signal.SIGALRM), old_handler)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0, 0))
            bounded_checkpoint_write(
                lambda: complete.write_text("{}"), time.monotonic() + 1000
            )
            self.assertTrue(complete.exists())

    def test_microbatches_cannot_consume_the_evaluation_reserve(self):
        completed = 0
        with self.assertRaises(TimeoutError):
            for now in range(0, 101, 10):
                check_deadline(100, reserve=20, now=now)
                completed += 1
        self.assertEqual(completed, 8)
        with self.assertRaises(TimeoutError):
            check_deadline(100, now=100)

    def test_previous_operation_duration_is_reserved_before_starting(self):
        with self.assertRaises(TimeoutError):
            check_deadline(100, reserve=20, now=75, estimated_seconds=6)

    def test_short_deadlines_and_zero_updates_are_rejected(self):
        base = {
            "steps": 1,
            "seconds": 1800,
            "batch_size": 1,
            "accumulation": 1,
            "max_length": 128,
            "rank": 8,
            "learning_rate": 1e-4,
            "brier_weight": 1,
            "evaluate_only": False,
        }
        for seconds in [120, 899, 900]:
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                validate_experiment_bounds({**base, "seconds": seconds})
        with self.assertRaises(ValueError):
            validate_experiment_bounds({**base, "steps": 0})
        validate_experiment_bounds({**base, "evaluate_only": True, "seconds": 120})

    def test_one_step_schedule_performs_a_nonzero_update(self):
        self.assertGreater(learning_rate_for_step(1, 1, 1e-4), 0)
        self.assertGreater(learning_rate_for_step(1500, 1500, 1e-4), 0)

    def test_empty_s3_bucket_or_prefix_is_rejected(self):
        for uri in ["s3://bucket/", "s3:///prefix", "s3://bucket", "s3://bucket///"]:
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                parse_s3_uri(uri)
        self.assertEqual(
            parse_s3_uri("s3://bucket/project/run/"), ("bucket", "project/run")
        )


class SnapshotTests(unittest.TestCase):
    def fixture(self, root):
        model = root / "model"
        model.mkdir()
        config, weights = b"{}\n", b"public-weights"
        (model / "config.json").write_bytes(config)
        (model / "model.safetensors").write_bytes(weights)
        manifest = {
            "id": "thinkingmachines/Inkling-2-Mini",
            "sha": "6e7c8248f75265bdd4fbab5273304243b5d8c2cb",
            "siblings": [
                {
                    "rfilename": "config.json",
                    "size": len(config),
                    "blobId": hashlib.sha1(
                        b"blob " + str(len(config)).encode() + b"\0" + config
                    ).hexdigest(),
                },
                {
                    "rfilename": "model.safetensors",
                    "size": len(weights),
                    "lfs": {"sha256": hashlib.sha256(weights).hexdigest()},
                },
            ],
        }
        (root / "model-manifest.json").write_text(json.dumps(manifest))
        benchmark = root / "jevbench" / "jevbench"
        benchmark.mkdir(parents=True)
        for name in ("__init__.py", "scoring.py", "metrics.py", "tasks.py"):
            (benchmark / name).write_text("# fixture\n")

    def test_changed_shape_compatible_weights_invalidate_cached_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            digest = verify_snapshot(root)
            self.assertEqual(verify_snapshot(root), digest)
            (root / "model/model.safetensors").write_bytes(b"changed-weight")
            with self.assertRaisesRegex(ValueError, "digest|size"):
                verify_snapshot(root)

    def test_modified_tokenizer_or_config_is_detected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "model/config.json").write_bytes(b"[]\n")
            with self.assertRaisesRegex(ValueError, "digest"):
                verify_snapshot(root)

    def test_added_loading_artifact_is_rejected_even_after_cached_verification(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            for path in (root / "model").iterdir():
                path.chmod(0o444)
            verify_snapshot(root)
            for name in (
                "adapter_config.json",
                "tokenizer_config.json",
                "chat_template.jinja",
            ):
                extra = root / "model" / name
                extra.write_text("{}\n")
                with (
                    self.subTest(name=name),
                    self.assertRaisesRegex(ValueError, "extra"),
                ):
                    verify_snapshot(root)
                extra.unlink()
            self.assertTrue(verify_snapshot(root))

    def test_runner_and_scoring_changes_invalidate_cached_evaluations(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            data = root / "data"
            data.mkdir()
            for name in ("train.jsonl", "dev.jsonl", "jevbench-231.jsonl"):
                (data / name).write_text("{}\n")
            runner = root / "source"
            runner.mkdir()
            for name in (
                "train.py",
                "data.py",
                "snapshot.py",
                "distributed.py",
                "prompting.py",
                "runtime.py",
                "cached_data.py",
                "candidate_approvals.json",
                "benchmark_identity.py",
                "native_runtime.py",
                "release_approvals.json",
                "adapter_restore.py",
            ):
                (runner / name).write_text("# fixture\n")
            with (
                patch("train.__file__", str(runner / "train.py")),
                patch("train.verify_benchmark", return_value="frozen"),
            ):
                baseline = build_run_identity(root, data, 128)
                for source in (
                    runner / "train.py",
                    root / "jevbench/jevbench/scoring.py",
                ):
                    source.write_text("# changed implementation\n")
                    self.assertNotEqual(baseline, build_run_identity(root, data, 128))
                    source.write_text("# fixture\n")
                self.assertEqual(baseline, build_run_identity(root, data, 128))

    def test_token_limit_changes_the_cached_evaluation_identity(self):
        with (
            TemporaryDirectory() as directory,
            patch("train.verify_benchmark", return_value="frozen"),
        ):
            root = Path(directory)
            self.fixture(root)
            data = root / "data"
            data.mkdir()
            for name in ["train.jsonl", "dev.jsonl", "jevbench-231.jsonl"]:
                (data / name).write_text("{}\n")
            self.assertNotEqual(
                build_run_identity(root, data, 128), build_run_identity(root, data, 256)
            )


if __name__ == "__main__":
    unittest.main()
