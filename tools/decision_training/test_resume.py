import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from train import (
    baseline_complete,
    validate_checkpoint_identity,
    validate_resume_arguments,
    verify_checkpoint_payloads,
)


class ResumeTests(unittest.TestCase):
    def test_summary_without_complete_predictions_is_not_a_baseline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "baseline-dev.json").write_text(
                json.dumps({"n": 1, "accuracy": 1.0})
            )
            rows = [{"id": "x", "labels": ["no", "yes"], "target": [0, 1]}]
            self.assertFalse(baseline_complete(root, "baseline-dev", rows))
            (root / "baseline-dev.jsonl").write_text(
                json.dumps(
                    {"id": "x", "probs": {"no": 0.4, "yes": 0.6}, "logits": [0, 1]}
                )
                + "\n"
            )
            self.assertFalse(baseline_complete(root, "baseline-dev", rows))
            complete = {
                "id": "x",
                "probs": {"no": 0.4, "yes": 0.6},
                "logits": [math.log(0.4), math.log(0.6)],
                "target": [0, 1],
                "correct": True,
            }
            (root / "baseline-dev.jsonl").write_text(json.dumps(complete) + "\n")
            self.assertTrue(baseline_complete(root, "baseline-dev", rows))
            for change in (
                {"target": [1, 0]},
                {"correct": False},
                {"probs": {"yes": 0.6, "no": 0.4}},
            ):
                (root / "baseline-dev.jsonl").write_text(
                    json.dumps({**complete, **change}) + "\n"
                )
                self.assertFalse(baseline_complete(root, "baseline-dev", rows))
            self.assertFalse(
                baseline_complete(
                    root, "baseline-dev", [{"id": "other", "labels": ["no", "yes"]}]
                )
            )

    def test_checkpoint_requires_loaded_payloads_even_with_an_empty_manifest(self):
        from cached_data import digest

        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("trainer.pt", "adapter_model.safetensors"):
                (root / name).write_bytes(b"original")
            files = {
                name: digest(root / name)
                for name in ("trainer.pt", "adapter_model.safetensors")
            }
            verify_checkpoint_payloads(root, {"files": files})
            with self.assertRaisesRegex(ValueError, "mandatory"):
                verify_checkpoint_payloads(
                    root,
                    {
                        "files": {
                            "adapter_model.safetensors": files[
                                "adapter_model.safetensors"
                            ]
                        }
                    },
                )
            (root / "trainer.pt").write_bytes(b"stale optimizer")
            with self.assertRaisesRegex(ValueError, "corrupt"):
                verify_checkpoint_payloads(root, {"files": files})

    def test_checkpoint_requires_explicit_matching_model_and_data_identity(self):
        identity = {"model": "base-a", "data": {"train": "sha256-a"}}
        for manifest in (
            {},
            {"identity": None},
            {"identity": {**identity, "model": "base-b"}},
            {"identity": {**identity, "data": {"train": "sha256-b"}}},
        ):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                validate_checkpoint_identity(manifest, identity)
        validate_checkpoint_identity({"identity": identity}, identity)

    def setUp(self):
        self.saved = {
            "batch_size": 16,
            "accumulation": 2,
            "max_length": 2048,
            "learning_rate": 1e-4,
            "brier_weight": 1.0,
            "rank": 32,
            "steps": 1500,
            "run_dir": "/old-vm",
            "seconds": 9000,
        }

    def test_continuation_rejects_every_changed_training_setting(self):
        for key in [
            "batch_size",
            "accumulation",
            "max_length",
            "learning_rate",
            "brier_weight",
            "rank",
            "steps",
        ]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                validate_resume_arguments(
                    self.saved, {**self.saved, key: self.saved[key] * 2}
                )

    def test_new_host_and_deadline_do_not_change_training_sequence(self):
        validate_resume_arguments(
            self.saved, {**self.saved, "run_dir": "/new-vm", "seconds": 6000}
        )


if __name__ == "__main__":
    unittest.main()
