import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validation.qwen_int4_task_quality.dataset import (
    PiqaExample,
    canonical_rows_sha256,
    hash_ranked_indices,
    load_piqa_validation,
    selected_indices_sha256,
)


class DatasetSelectionTests(unittest.TestCase):
    def test_hash_ranking_is_deterministic_and_independent_of_row_content(self) -> None:
        expected = sorted(
            range(8),
            key=lambda index: hashlib.sha256(f"17:{index}".encode()).digest(),
        )[:3]

        self.assertEqual(hash_ranked_indices(8, 3, 17), expected)
        self.assertEqual(hash_ranked_indices(8, 3, 17), expected)

    def test_selected_index_identity_uses_canonical_json(self) -> None:
        indices = [3, 1, 8]
        expected = hashlib.sha256(
            json.dumps(indices, separators=(",", ":")).encode()
        ).hexdigest()

        self.assertEqual(selected_indices_sha256(indices), expected)

    def test_canonical_row_identity_covers_labels_and_text(self) -> None:
        rows = [
            PiqaExample(0, "goal", ("first", "second"), 1),
            PiqaExample(1, "other", ("a", "b"), 0),
        ]
        changed = [
            PiqaExample(0, "goal", ("first", "second"), 0),
            PiqaExample(1, "other", ("a", "b"), 0),
        ]

        self.assertEqual(canonical_rows_sha256(rows), canonical_rows_sha256(rows))
        self.assertNotEqual(canonical_rows_sha256(rows), canonical_rows_sha256(changed))

    def test_selection_fails_closed_on_invalid_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "example_count"):
            hash_ranked_indices(2, 3, 17)

    def test_loader_preserves_official_choice_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = root / "dev.jsonl"
            labels = root / "dev-labels.lst"
            rows.write_text(
                json.dumps({"goal": "goal", "sol1": "first ", "sol2": "second  "})
                + "\n",
                encoding="utf-8",
            )
            labels.write_text("1\n", encoding="utf-8")

            example = load_piqa_validation(rows, labels)[0]

        self.assertEqual(example.choices, ("first ", "second  "))


if __name__ == "__main__":
    unittest.main()
