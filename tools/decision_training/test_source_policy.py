import unittest

from source_policy import allowed_license, canonical_family, near_state_key, rejection


class SourcePolicyTests(unittest.TestCase):
    def test_parent_and_recast_share_global_family(self):
        self.assertEqual(
            canonical_family("tasksource/procedural-typed-decisions/graph_navigation"),
            canonical_family("procedural-typed-decisions/graph_navigation"),
        )
        self.assertEqual(canonical_family("mnli+fmt+long"), "multi_nli")

    def test_mixed_custom_terms_and_known_writers_fail_closed(self):
        self.assertFalse(allowed_license("mit, Custom (DPI)"))
        self.assertFalse(allowed_license("cc-by-nc-4.0"))
        self.assertTrue(allowed_license("CC BY-SA 4.0 (DPI)"))
        self.assertTrue(allowed_license("cc-by-3.0/cc-by-sa-3.0"))
        self.assertEqual(
            rejection({"source_task": "WANLI", "license": "cc-by-4.0"}),
            "excluded_or_unresolved_writer_provenance",
        )
        self.assertEqual(
            rejection({"source_task": "prm800k_dpo/step", "license": "mit"}),
            "excluded_or_unresolved_writer_provenance",
        )

    def test_near_groups_never_erase_numeric_or_operator_facts(self):
        row = {
            "state": "The observed payment is 20 units and the threshold is > 10 units."
        }
        self.assertNotEqual(
            near_state_key(row),
            near_state_key({"state": row["state"].replace("20", "30")}),
        )
        self.assertNotEqual(
            near_state_key(row),
            near_state_key({"state": row["state"].replace(">", "<")}),
        )
        self.assertIsNone(near_state_key({"state": ""}))
        self.assertNotEqual(
            near_state_key({"state": row["state"].replace("20", "-20")}),
            near_state_key(row),
        )
        self.assertNotEqual(
            near_state_key({"state": row["state"].replace("20", ".20")}),
            near_state_key(row),
        )


if __name__ == "__main__":
    unittest.main()
