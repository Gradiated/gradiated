import json
import tempfile
import unittest
from pathlib import Path

from validation.qwen_int4_quality.provenance import (
    checkpoint_precision_bits,
    tokenizer_identity,
)


class CheckpointPrecisionTests(unittest.TestCase):
    def test_reads_declared_checkpoint_precision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory)
            (model_path / "config.json").write_text(
                json.dumps({"torch_dtype": "bfloat16"}),
                encoding="utf-8",
            )

            self.assertEqual(checkpoint_precision_bits(model_path), 16)

    def test_rejects_unknown_checkpoint_precision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory)
            (model_path / "config.json").write_text(
                json.dumps({"torch_dtype": "mystery"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "checkpoint dtype"):
                checkpoint_precision_bits(model_path)

    def test_tokenizer_identity_hashes_local_definition_files(self) -> None:
        class FakeTokenizer:
            vocab_size = 123

        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory)
            (model_path / "tokenizer.json").write_text("tokenizer", encoding="utf-8")
            (model_path / "tokenizer_config.json").write_text(
                "config", encoding="utf-8"
            )

            identity = tokenizer_identity(model_path, FakeTokenizer())

        self.assertEqual(identity["class"], "FakeTokenizer")
        self.assertEqual(identity["vocab_size"], 123)
        self.assertEqual(
            [file["name"] for file in identity["files"]],
            ["tokenizer.json", "tokenizer_config.json"],
        )
        self.assertEqual(
            identity["files"][0]["sha256"],
            "5f97e3774c51edd1d63706c2ec3826c564a067794770cdab0f8c4797971cacf9",
        )


if __name__ == "__main__":
    unittest.main()
