import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autotrain.data import digest
from runtime import TrainingRuntime


class RuntimeTests(unittest.TestCase):
    def test_adapts_signed_artifacts_to_local_library_inputs_and_checkpoint_callback(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "dataset.jsonl"
            source.write_text("dataset")
            checkpoint = root / "checkpoint.tar.gz"
            checkpoint.write_bytes(b"checkpoint")
            adapter = root / "adapter.tar.gz"
            adapter.write_bytes(b"adapter")
            uploaded_checkpoint = root / "uploaded-checkpoint"
            uploaded_adapter = root / "uploaded-adapter"
            reference = {"url": str(source), "sha256": digest(source)}
            command = {
                "operation": "train",
                "dataset": reference,
                "validation": reference,
                "checkpoint": {"url": str(checkpoint), "sha256": digest(checkpoint)},
                "checkpoints": {
                    "10": {
                        "url": str(uploaded_checkpoint),
                        "key": "runs/test/checkpoint",
                    }
                },
                "output": {"url": str(uploaded_adapter), "key": "runs/test/adapter"},
            }
            events = []
            runtime = TrainingRuntime(root / "run", recipe={})

            def transfer(url, destination=None, upload=None):
                shutil.copyfile(upload or url, url if upload else destination)

            def train(dataset, validation, *, checkpoint, emit, save_checkpoint):
                self.assertEqual(dataset.read_text(), "dataset")
                self.assertEqual(validation.read_text(), "dataset")
                self.assertEqual(checkpoint.read_bytes(), b"checkpoint")
                save_checkpoint(10, checkpoint)
                emit({"type": "trainer_progress", "step": 10, "train_loss": 0.5})
                return adapter

            with (
                patch("runtime.transfer", side_effect=transfer),
                patch.object(runtime, "load"),
                patch.object(runtime, "train", side_effect=train),
            ):
                result = runtime.run(command, events.append)

            self.assertEqual(
                result,
                {
                    "key": "runs/test/adapter",
                    "sha256": digest(adapter),
                    "size_bytes": 7,
                },
            )
            self.assertEqual(uploaded_adapter.read_bytes(), b"adapter")
            self.assertEqual(uploaded_checkpoint.read_bytes(), b"checkpoint")
            self.assertEqual(
                events[0],
                {
                    "type": "trainer_checkpoint",
                    "step": 10,
                    "key": "runs/test/checkpoint",
                    "sha256": digest(checkpoint),
                    "size_bytes": 10,
                },
            )
            self.assertEqual(events[1]["type"], "trainer_progress")

    def test_rejects_download_with_wrong_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = TrainingRuntime(temp, recipe={})
            with patch(
                "runtime.transfer",
                side_effect=lambda url, destination: Path(destination).write_bytes(
                    b"incorrect"
                ),
            ):
                with self.assertRaisesRegex(ValueError, "digest mismatch"):
                    runtime.download(
                        {"url": "https://example.com/artifact", "sha256": "0" * 64},
                        "artifact",
                    )
