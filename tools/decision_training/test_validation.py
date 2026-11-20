import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from snapshot import verify_snapshot
from train import (
    build_run_identity,
    check_deadline,
    learning_rate_for_step,
    parse_s3_uri,
    validate_experiment_bounds,
)


class RunnerValidationTests(unittest.TestCase):
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

    def test_token_limit_changes_the_cached_evaluation_identity(self):
        with TemporaryDirectory() as directory:
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
