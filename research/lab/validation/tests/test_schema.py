import json
import tempfile
import unittest
from pathlib import Path

from validation.qwen_int4_quality.schema import load_corpus, load_run_config


class CorpusSchemaTests(unittest.TestCase):
    def test_loads_memory_bounded_interleaved_evaluation_strategy(self) -> None:
        document = {
            "schema_version": "inference-foundry.quality-run.v1",
            "suite": "suite",
            "seed": 1,
            "dtype": "bfloat16",
            "torch_threads": 4,
            "evaluation_strategy": "interleaved_models",
            "quantization": {
                "scheme": "symmetric_signed_int4_quantize_dequantize",
                "granularity": "groupwise",
                "group_size": 8,
                "excluded_modules": ["lm_head"],
            },
            "non_inferiority": {
                "maximum_nll_increase": 0.15,
                "maximum_perplexity_ratio": 1.15,
                "maximum_logit_rmse": 0.5,
                "minimum_logit_cosine_similarity": 0.98,
                "minimum_top1_agreement": 0.8,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            config = load_run_config(path)

        self.assertEqual(config.evaluation_strategy, "interleaved_models")

    def test_loads_legacy_hand_authored_corpus_with_truthful_metadata(self) -> None:
        corpus = self._load(
            {
                "schema_version": "inference-foundry.corpus.v1",
                "description": "Hand-authored examples.",
                "examples": [
                    {"id": "one", "prompt": "Prompt", "completion": " completion"}
                ],
            }
        )

        self.assertEqual(corpus.kind, "hand_authored_agent_style_calibration")
        self.assertEqual(corpus.task, "teacher_forced_completion")
        self.assertFalse(corpus.is_standard_benchmark)
        self.assertEqual(corpus.source, {"type": "hand_authored"})
        self.assertEqual(len(corpus.entries), 1)
        self.assertIsNone(corpus.expected_target_tokens)

    def test_loads_held_out_corpus_provenance(self) -> None:
        document = self._held_out_document()

        corpus = self._load(document)

        self.assertEqual(corpus.kind, "held_out_language_modeling_subset")
        self.assertEqual(corpus.task, "teacher_forced_next_token_prediction")
        self.assertFalse(corpus.is_standard_benchmark)
        self.assertEqual(corpus.source["dataset_fingerprint"], "fingerprint")
        self.assertEqual(corpus.generation["generator_version"], "generator-v1")
        self.assertEqual(corpus.tokenizer["class"], "FakeTokenizer")
        self.assertEqual(corpus.expected_example_count, 1)
        self.assertEqual(corpus.expected_target_tokens, 2)
        self.assertEqual(corpus.entries[0].identifier, "row-7")

    def test_rejects_held_out_corpus_without_source_provenance(self) -> None:
        document = self._held_out_document()
        del document["source"]

        with self.assertRaisesRegex(ValueError, "source"):
            self._load(document)

    def test_rejects_held_out_corpus_without_pinned_tokenizer_files(self) -> None:
        document = self._held_out_document()
        document["tokenizer"]["files"] = []

        with self.assertRaisesRegex(ValueError, "tokenizer files"):
            self._load(document)

    def _load(self, document: dict[str, object]):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_corpus(path)

    @staticmethod
    def _held_out_document() -> dict[str, object]:
        return {
            "schema_version": "inference-foundry.corpus.v2",
            "kind": "held_out_language_modeling_subset",
            "description": "Pinned held-out subset.",
            "task": "teacher_forced_next_token_prediction",
            "is_standard_benchmark": False,
            "source": {
                "dataset_id": "dataset",
                "dataset_config": "config",
                "split": "test",
                "dataset_fingerprint": "fingerprint",
            },
            "generation": {
                "generator_version": "generator-v1",
                "selection_method": "hash-ranked rows",
            },
            "tokenizer": {
                "model_id": "model",
                "class": "FakeTokenizer",
                "vocab_size": 10,
                "files": [{"name": "tokenizer.json", "sha256": "hash"}],
            },
            "expected_example_count": 1,
            "expected_target_tokens": 2,
            "examples": [
                {"id": "row-7", "prompt": "Prompt", "completion": " completion"}
            ],
        }


if __name__ == "__main__":
    unittest.main()
