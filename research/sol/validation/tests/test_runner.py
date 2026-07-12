import unittest

import torch

from validation.qwen_int4_quality.runner import (
    TokenizedExample,
    _build_corpus_report,
    _validate_tokenizer_identity,
    _validate_tokenized_corpus,
)
from validation.qwen_int4_quality.schema import CorpusEntry, QualityCorpus


class CorpusReportTests(unittest.TestCase):
    def test_reports_held_out_provenance_without_hand_authored_label(self) -> None:
        corpus = self._corpus(expected_target_tokens=2)

        report = _build_corpus_report(
            corpus,
            actual_target_tokens=2,
            corpus_sha256="corpus-hash",
        )

        self.assertEqual(report["kind"], "held_out_language_modeling_subset")
        self.assertEqual(report["task"], "teacher_forced_next_token_prediction")
        self.assertEqual(report["source"]["dataset_id"], "Salesforce/wikitext")
        self.assertEqual(report["generation"]["generator_version"], "generator-v1")
        self.assertEqual(report["tokenizer"]["class"], "FakeTokenizer")
        self.assertEqual(report["generated_corpus_sha256"], "corpus-hash")
        self.assertEqual(report["target_tokens"], 2)
        self.assertNotIn("hand-authored", str(report))

    def test_rejects_generated_target_token_count_mismatch(self) -> None:
        corpus = self._corpus(expected_target_tokens=3)
        tokenized = [
            TokenizedExample(
                identifier="one",
                input_ids=torch.tensor([[1, 2, 3]]),
                target_start=0,
                target_tokens=2,
            )
        ]

        with self.assertRaisesRegex(ValueError, "target token count"):
            _validate_tokenized_corpus(corpus, tokenized)

    def test_rejects_runtime_tokenizer_hash_mismatch(self) -> None:
        corpus = self._corpus(expected_target_tokens=2)
        corpus.tokenizer["files"] = [
            {"name": "tokenizer.json", "sha256": "expected-hash"}
        ]
        actual = {
            "class": "FakeTokenizer",
            "vocab_size": 10,
            "files": [{"name": "tokenizer.json", "sha256": "other-hash"}],
        }

        with self.assertRaisesRegex(ValueError, "tokenizer identity"):
            _validate_tokenizer_identity(corpus, actual)

    @staticmethod
    def _corpus(expected_target_tokens: int) -> QualityCorpus:
        return QualityCorpus(
            schema_version="inference-foundry.corpus.v2",
            kind="held_out_language_modeling_subset",
            description="Held-out subset.",
            task="teacher_forced_next_token_prediction",
            is_standard_benchmark=False,
            source={
                "dataset_id": "Salesforce/wikitext",
                "dataset_config": "wikitext-2-raw-v1",
                "split": "test",
                "dataset_fingerprint": "fingerprint",
            },
            generation={
                "generator_version": "generator-v1",
                "selection_method": "hash-ranked rows",
            },
            tokenizer={
                "model_id": "model",
                "class": "FakeTokenizer",
                "vocab_size": 10,
                "files": [],
            },
            expected_example_count=1,
            expected_target_tokens=expected_target_tokens,
            entries=(CorpusEntry(identifier="one", prompt="A", completion=" B"),),
        )


if __name__ == "__main__":
    unittest.main()
