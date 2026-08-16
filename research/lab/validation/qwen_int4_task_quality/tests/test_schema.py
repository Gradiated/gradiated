import json
import tempfile
import unittest
from pathlib import Path

from validation.qwen_int4_task_quality.schema import load_task_config


class TaskConfigTests(unittest.TestCase):
    def test_loads_frozen_contract(self) -> None:
        document = self._document()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            config = load_task_config(path)

        self.assertEqual(config.selection.example_count, 256)
        self.assertEqual(config.quantization.scale_storage, "bfloat16")
        self.assertEqual(config.quantization.expected_module_count, 84)
        self.assertEqual(config.gates.maximum_accuracy_drop, 0.02)
        self.assertEqual(
            config.scoring.method, "length_normalized_continuation_log_likelihood"
        )
        self.assertEqual(config.model.weight_bytes, 1503300328)
        self.assertEqual(config.dataset.dataset_version, "1.1.0")

    def test_rejects_non_kernel_equivalent_scale_contract(self) -> None:
        document = self._document()
        document["quantization"]["scale_storage"] = "float32"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scale_storage"):
                load_task_config(path)

    def test_rejects_incomplete_tokenizer_file_identity(self) -> None:
        document = self._document()
        del document["model"]["tokenizer_files"][0]["name"]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "tokenizer"):
                load_task_config(path)

    def test_rejects_quantization_mask_different_from_runtime_transform(self) -> None:
        document = self._document()
        document["quantization"]["included_module_patterns"] = [
            "model.layers.*.self_attn.q_proj"
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "module patterns"):
                load_task_config(path)

    @staticmethod
    def _document() -> dict[str, object]:
        return {
            "schema_version": "inference-foundry.int4-task-quality.v1",
            "suite": "test",
            "seed": 20260712,
            "dtype": "bfloat16",
            "torch_threads": 4,
            "model": {
                "model_id": "Qwen/Qwen3-0.6B",
                "model_revision": "f" * 40,
                "local_path": "models/Qwen3-0.6B",
                "config_sha256": "f" * 64,
                "weight_file": "model.safetensors",
                "weight_bytes": 1503300328,
                "weight_sha256": "f" * 64,
                "tokenizer_files": [{"name": "tokenizer.json", "sha256": "f" * 64}],
            },
            "dataset": {
                "dataset_id": "ybisk/piqa",
                "dataset_revision": "a" * 40,
                "dataset_version": "1.1.0",
                "dataset_script_sha256": "a" * 64,
                "source_url": "https://example.test/piqa.zip",
                "archive_sha256": "a" * 64,
                "validation_jsonl_sha256": "b" * 64,
                "validation_labels_sha256": "c" * 64,
                "expected_validation_rows": 1838,
                "expected_validation_rows_sha256": "a" * 64,
            },
            "selection": {
                "method": "sha256_ranked_seed_colon_index",
                "seed": 20260712,
                "example_count": 256,
                "expected_selected_indices_sha256": "d" * 64,
                "expected_selected_rows_sha256": "e" * 64,
            },
            "prompt": {"template": "Question: {goal}\\nAnswer:", "choice_prefix": " "},
            "scoring": {
                "method": "length_normalized_continuation_log_likelihood",
                "tie_break": "lowest_choice_index",
            },
            "quantization": {
                "scheme": "symmetric_signed_int4",
                "group_size": 8,
                "code_scale": "float32_max_abs_div_7",
                "scale_storage": "bfloat16",
                "dequantization_scale": "stored_bfloat16_promoted_to_float32",
                "included_module_patterns": [
                    "model.layers.*.self_attn.o_proj",
                    "model.layers.*.mlp.gate_proj",
                    "model.layers.*.mlp.up_proj",
                ],
                "expected_module_count": 84,
                "expected_parameter_count": 234881024,
            },
            "gates": {"maximum_accuracy_drop": 0.02},
            "uncertainty": {
                "paired_bootstrap_samples": 10000,
                "confidence_level": 0.95,
            },
        }


if __name__ == "__main__":
    unittest.main()
