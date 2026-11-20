import sqlite3
import unittest

from audit_scale import decision_keys, group_components


class ScaleAuditTests(unittest.TestCase):
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
