import hashlib
import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_scale import (
    capture_sources,
    decision_keys,
    group_components,
    legacy_acquisitions,
)


class ScaleAuditTests(unittest.TestCase):
    def test_portable_legacy_acquisitions_are_explicit_and_hash_verified(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "copied.parquet"
            raw.write_bytes(b"verified source")
            original = {
                "repo": "tasksource/tasksource-jev-typed-decisions",
                "revision": "pinned",
                "file": "train.parquet",
                "path": "/missing/builder/path",
                "bytes": raw.stat().st_size,
                "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            }
            manifest = {"sources": [original]}
            with self.assertRaisesRegex(ValueError, "explicit"):
                legacy_acquisitions(manifest, [])
            supplied = root / "acquired.json"
            supplied.write_text(json.dumps([{**original, "path": str(raw)}]))
            self.assertEqual(
                legacy_acquisitions(manifest, [supplied])[0]["path"], str(raw)
            )
            raw.write_bytes(b"different bytes")
            with self.assertRaisesRegex(ValueError, "hash"):
                legacy_acquisitions(manifest, [supplied])
            self.assertEqual(
                legacy_acquisitions(
                    {
                        **manifest,
                        "normalization_version": "canonical-v2-zero-groups-preserved",
                    },
                    [],
                ),
                [],
            )

    def test_helper_source_change_changes_archived_audit_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "audit_scale.py",
                "data.py",
                "prepare_scale.py",
                "scale_data.py",
                "original_data.py",
            ):
                (root / name).write_text("# fixture\n")
            first = root / "first"
            first.mkdir()
            before = capture_sources(first, root)
            (root / "data.py").write_text("# changed overlap algorithm\n")
            second = root / "second"
            second.mkdir()
            after = capture_sources(second, root)
            self.assertNotEqual(before["data.py"], after["data.py"])
            self.assertEqual(before["audit_scale.py"], after["audit_scale.py"])

    def row(self):
        return {
            "state": "An order arrived with a damaged item and incomplete shipping address.",
            "question": {"type": "choice", "instructions": "What should happen?"},
            "descriptions": ["Refund", "Request address"],
            "target": [0.2, 0.8],
        }

    def test_nominal_reordering_keeps_input_and_aligned_target_identity(self):
        row = self.row()
        reordered = {
            **row,
            "descriptions": row["descriptions"][::-1],
            "target": row["target"][::-1],
        }
        self.assertEqual(decision_keys(row), decision_keys(reordered))
        self.assertNotEqual(
            decision_keys(row)[2],
            decision_keys({**reordered, "target": row["target"]})[2],
        )

    def test_ordinal_order_and_numeric_operators_are_not_erased(self):
        row = {**self.row(), "question": {"type": "score", "instructions": "Severity?"}}
        self.assertNotEqual(
            decision_keys(row)[1],
            decision_keys({**row, "descriptions": row["descriptions"][::-1]})[1],
        )
        self.assertNotEqual(
            decision_keys({**row, "state": "x > 2"})[1],
            decision_keys({**row, "state": "x < 2"})[1],
        )

    def test_empty_state_does_not_merge_unrelated_questions(self):
        row = {**self.row(), "state": ""}
        self.assertNotEqual(
            decision_keys(row)[0],
            decision_keys(
                {
                    **row,
                    "question": {
                        "type": "choice",
                        "instructions": "Different question",
                    },
                }
            )[0],
        )

    def test_components_propagate_across_case_state_and_exact_input_links(self):
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE items(n INTEGER,case_key TEXT,state_key TEXT,input_key TEXT)"
        )
        connection.executemany(
            "INSERT INTO items VALUES(?,?,?,?)",
            [
                (0, "a", "s0", "i0"),
                (1, "a", "s1", "i1"),
                (2, "b", "s1", "i2"),
                (3, "c", "s3", "i2"),
                (4, "d", "s4", "i4"),
            ],
        )
        groups = group_components(connection, 5)
        self.assertEqual(len({groups.root(i) for i in range(4)}), 1)
        self.assertNotEqual(groups.root(0), groups.root(4))
        connection.close()


if __name__ == "__main__":
    unittest.main()
