import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from data import normalize_tasksource, normalize_typed, read_jsonl, split_rows


class DecisionDataTests(unittest.TestCase):
    def test_zero_group_id_keeps_counterfactuals_in_one_partition(self):
        base = {
            "source": "CREAK",
            "question": "Is it true?",
            "kind": "noul",
            "options": [],
            "target": [0.3],
            "group_id": 0,
            "license": "cc-by-4.0",
            "license_use": "commercial",
        }
        rows = [
            normalize_tasksource({**base, "id": str(i), "state": f"Claim {i}"})
            for i in range(100)
        ]
        self.assertEqual(len({row["group"] for row in rows}), 1)
        self.assertTrue(rows[0]["group"].endswith(":0"))
        train, dev = split_rows(rows)
        self.assertEqual(sorted((len(train), len(dev))), [0, 100])
        fallback = normalize_tasksource(
            {**base, "id": "fallback", "state": "Claim", "group_id": None}
        )
        self.assertTrue(fallback["group"].endswith(":fallback"))

    def test_jsonl_preserves_unicode_line_separator_inside_state(self):
        row = {"state": "first\u2028second\u0085third"}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n")
            self.assertEqual(read_jsonl(path), [row])

    def test_scalar_binary_target_becomes_no_yes_distribution(self):
        row = normalize_tasksource(
            {
                "id": "a",
                "source": "CREAK",
                "state": "A claim",
                "question": "Is it true?",
                "kind": "noul",
                "options": [],
                "target": [0.3],
                "group_id": "claim-a",
                "license": "cc-by-4.0",
                "license_use": "commercial",
            }
        )
        self.assertEqual(row["labels"], ["no", "yes"])
        self.assertEqual(row["descriptions"], ["No", "Yes"])
        self.assertEqual(row["target"], [0.7, 0.3])

    def test_option_keys_supply_missing_descriptions(self):
        row = normalize_typed(
            {
                "id": "a",
                "state": "An order",
                "question": {
                    "type": "choice",
                    "instructions": "Act?",
                    "criteria": {"approve": None, "reject": "Decline the order"},
                },
                "expected": "approve",
            },
            "synthetic",
        )
        self.assertEqual(row["descriptions"], ["approve", "Decline the order"])
        self.assertEqual(row["target"], [1.0, 0.0])

    def test_noncommercial_rows_are_not_admitted(self):
        self.assertIsNone(normalize_tasksource({"license_use": "non-commercial"}))

    def test_soft_targets_stay_aligned_to_option_order(self):
        row = normalize_typed(
            {
                "id": "a",
                "state": "A ticket",
                "question": {
                    "type": "choice",
                    "instructions": "Where?",
                    "criteria": {"billing": "Invoices", "support": "Errors"},
                },
                "expected": "support",
                "labels": ["support", "billing"],
                "target_probs": [0.8, 0.2],
            },
            "synthetic",
        )
        self.assertEqual(row["target"], [0.2, 0.8])

    def test_split_keeps_groups_and_states_disjoint(self):
        rows = [
            {"id": str(i), "group": f"g{i // 2}", "state": f"s{i // 2}"}
            for i in range(200)
        ]
        rows[0]["state"] = rows[-1]["state"]
        train, dev = split_rows(rows, 20)
        self.assertTrue(train and dev)
        self.assertFalse({r["group"] for r in train} & {r["group"] for r in dev})
        self.assertFalse({r["state"] for r in train} & {r["state"] for r in dev})


if __name__ == "__main__":
    unittest.main()
