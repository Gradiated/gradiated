import unittest

from validation.qwen_int4_quality.wikitext import (
    SelectedTokenWindow,
    build_corpus_document,
    select_sequential_token_windows,
    select_token_windows,
    serialize_corpus,
)


class FakeTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool) -> list[str]:
        return text.split()

    def decode(
        self,
        token_ids: list[str],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        return " ".join(token_ids)


class WikiTextSelectionTests(unittest.TestCase):
    def test_hash_ranked_selection_is_deterministic_and_filters_rows(self) -> None:
        rows = [
            "",
            " = Heading = ",
            "too short",
            "alpha beta gamma delta epsilon",
            "one two three four five",
            "red blue green white black",
        ]

        first, eligible_count = select_token_windows(
            rows,
            FakeTokenizer(),
            example_count=2,
            context_tokens=2,
            target_tokens=2,
            selection_seed="seed-v1",
        )
        second, _ = select_token_windows(
            rows,
            FakeTokenizer(),
            example_count=2,
            context_tokens=2,
            target_tokens=2,
            selection_seed="seed-v1",
        )

        self.assertEqual(eligible_count, 3)
        self.assertEqual(first, second)
        self.assertEqual([window.source_row_index for window in first], [3, 5])
        self.assertEqual(
            [window.prompt for window in first], ["alpha beta", "red blue"]
        )
        self.assertEqual(
            [window.completion for window in first], ["gamma delta", "green white"]
        )
        self.assertTrue(all(len(window.selection_sha256) == 64 for window in first))

    def test_rejects_insufficient_eligible_rows(self) -> None:
        with self.assertRaisesRegex(ValueError, "eligible"):
            select_token_windows(
                ["one two three four"],
                FakeTokenizer(),
                example_count=2,
                context_tokens=2,
                target_tokens=2,
                selection_seed="seed-v1",
            )

    def test_builds_pinned_v2_corpus_document(self) -> None:
        manifest = {
            "source": {
                "dataset_id": "Salesforce/wikitext",
                "dataset_config": "wikitext-2-raw-v1",
                "split": "test",
                "dataset_fingerprint": "fingerprint",
            },
            "generation": {
                "generator_version": "generator-v1",
                "selection_method": "hash-ranked rows",
                "selection_seed": "seed-v1",
                "example_count": 1,
                "context_tokens_per_example": 2,
                "target_tokens_per_example": 2,
            },
            "tokenizer": {
                "model_id": "model",
                "class": "FakeTokenizer",
                "vocab_size": 10,
                "files": [{"name": "tokenizer.json", "sha256": "hash"}],
            },
        }
        windows = (
            SelectedTokenWindow(
                source_row_index=7,
                selection_sha256="digest",
                prompt="alpha beta",
                completion=" gamma delta",
            ),
        )

        document = build_corpus_document(manifest, windows, eligible_row_count=3)
        serialized = serialize_corpus(document)

        self.assertEqual(document["schema_version"], "inference-foundry.corpus.v2")
        self.assertEqual(document["source"]["dataset_fingerprint"], "fingerprint")
        self.assertEqual(document["generation"]["eligible_row_count"], 3)
        self.assertEqual(document["generation"]["selected_row_indices"], [7])
        self.assertEqual(document["expected_target_tokens"], 2)
        self.assertEqual(document["examples"][0]["id"], "wikitext-test-row-0007")
        self.assertTrue(serialized.endswith(b"\n"))

    def test_sequential_windows_cover_contiguous_targets(self) -> None:
        windows, stream_token_count, stream_sha256 = select_sequential_token_windows(
            [
                "zero one two three four five",
                "six seven eight nine ten eleven",
            ],
            FakeTokenizer(),
            example_count=3,
            context_tokens=2,
            target_tokens=2,
        )

        self.assertEqual(stream_token_count, 12)
        self.assertEqual(len(stream_sha256), 64)
        self.assertEqual([window.target_start_token for window in windows], [2, 4, 6])
        self.assertEqual(
            [window.completion for window in windows],
            ["two three", "four five", "six seven"],
        )
        self.assertEqual(
            [window.prompt for window in windows],
            ["zero one", "two three", "four five"],
        )


if __name__ == "__main__":
    unittest.main()
