import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from autotrain.data import digest
from runtime import TrainingRuntime


class RuntimeTests(unittest.TestCase):
    def test_retains_exact_input_and_output_usage_for_cost_estimates(self):
        runtime = TrainingRuntime.__new__(TrainingRuntime)
        runtime.tokenizer = Mock(return_value={"input_ids": [1, 2, 3]})
        runtime.tokenizer.apply_chat_template.return_value = "formatted prompt"
        messages = [{"role": "user", "content": "hello"}]
        with patch("autotrain.Trainer.generate", return_value={"text": "answer", "tokens": 2, "seconds": 1}) as generate:
            result = runtime.generate(messages, adapted=True)
        self.assertEqual(result["usage"], {"input_tokens": 3, "output_tokens": 2})
        generate.assert_called_once_with(messages, True, 256, None)
        runtime.tokenizer.apply_chat_template.assert_called_once_with(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )

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

    def test_external_evaluation_generates_only_adapter_answers(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = TrainingRuntime(temp, recipe={})
            example = {
                "id": "example",
                "group": "session",
                "prompt": [{"role": "user", "content": "request"}],
            }
            with (
                patch.object(runtime, "load"),
                patch.object(runtime, "download", return_value=Path(temp) / "input"),
                patch.object(runtime, "load_adapter"),
                patch("runtime.read_examples", return_value=[example]),
                patch.object(
                    runtime,
                    "generate",
                    return_value={"text": "answer", "tokens": 1, "seconds": 1},
                ) as generate,
                patch.object(runtime, "upload", return_value={"key": "result"}),
            ):
                runtime.run(
                    {
                        "operation": "generate",
                        "external_evaluation": True,
                        "adapter": {},
                        "dataset": {},
                        "output": {},
                    },
                    lambda event: None,
                )
                generate.assert_called_once_with(example["prompt"], adapted=True)
                saved = json.loads((Path(temp) / "predictions.json").read_text())
                self.assertEqual(saved[0]["id"], "example")
                self.assertNotIn("comparison", saved[0])
                self.assertNotIn("judgment", saved[0])

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

    def test_evaluation_judges_each_pair_once_and_preserves_randomized_order(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = TrainingRuntime(temp, recipe={})
            examples = [
                {
                    "id": str(i),
                    "group": str(i),
                    "prompt": [{"role": "user", "content": "test"}],
                }
                for i in range(16)
            ]
            calls = []

            def generate(prompt, *, adapted, **options):
                calls.append((adapted, options))
                if options:
                    return {"text": "A"}
                return {
                    "text": "fine" if adapted else "base",
                    "tokens": 1,
                    "seconds": 1,
                }

            command = {
                "operation": "generate",
                "adapter": {},
                "dataset": {},
                "output": {},
            }
            with (
                patch.object(runtime, "load"),
                patch.object(runtime, "load_adapter"),
                patch.object(runtime, "download", return_value=Path(temp)),
                patch("runtime.read_examples", return_value=examples),
                patch.object(runtime, "generate", side_effect=generate),
                patch.object(
                    runtime,
                    "upload",
                    side_effect=lambda path, grant: json.loads(path.read_text()),
                ),
            ):
                result = runtime.run(command, lambda event: None)
                repeat = runtime.run(command, lambda event: None)

            self.assertEqual(result, repeat)
            self.assertEqual(len(calls), len(examples) * 3 * 2)
            self.assertEqual({row["fine_tuned_first"] for row in result}, {True, False})
            for index, row in enumerate(result):
                self.assertEqual(row["judgment"], "A")
                self.assertEqual(calls[index * 3][0], row["fine_tuned_first"])
                self.assertEqual(calls[index * 3 + 1][0], not row["fine_tuned_first"])
                self.assertEqual(row["fine_tuned"]["text"], "fine")
                self.assertEqual(row["comparison"]["text"], "base")
