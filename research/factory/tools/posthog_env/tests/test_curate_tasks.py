"""Unit tests for curate_tasks.resolve_turns (editor turn handling)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/opt/posthog-env/runner")
import curate_tasks as CT  # noqa: E402

BUILT = ["<attached_context>" + "x" * 5000 + "</attached_context> traffic to the landing page?", "and last week?"]


class ResolveTurns(unittest.TestCase):
    def test_null_copies_built(self):
        self.assertEqual(CT.resolve_turns([None, "and the week before?"], BUILT, [{"turn": 1}]), [BUILT[0], "and the week before?"])

    def test_placeholder_copies_built(self):
        """b02 review: "[turn 0 unchanged: original attached dashboard context ...]" was sent to the agent."""
        out = CT.resolve_turns(["[turn 0 unchanged: original attached dashboard context + system reminders]", None], BUILT, [])
        self.assertEqual(out, BUILT)

    def test_silent_shrink_rejected(self):
        with self.assertRaises(AssertionError):
            CT.resolve_turns(["traffic to the landing page?", None], BUILT, [])

    def test_edited_shrink_allowed(self):
        out = CT.resolve_turns(["traffic to the landing page /garden?", None], BUILT, [{"turn": 0, "kind": "fold_context"}])
        self.assertEqual(out[0], "traffic to the landing page /garden?")


class Queries(unittest.TestCase):
    """b02 review: the editor claimed absences from top-N card lists; its verification queries must be read-only and
    scoped to the twin team."""

    def test_rejects_unscoped_and_writes(self):
        res = CT.run_queries([{"why": "a", "sql": "SELECT count() FROM events"},
                              {"why": "b", "sql": "ALTER TABLE events DELETE WHERE team_id = {team}"}], 1)
        self.assertTrue(all(r["result"].startswith("REJECTED") for r in res))



class Warehouse(unittest.TestCase):
    """eval_v1 audit: the curator never checked warehouse-backed premises (it could not read warehouse tables)."""

    def test_expand(self):
        orig = CT.warehouse_urls
        CT.warehouse_urls = lambda team: {"stripe_customers": "http://127.0.0.1:19000/x.parquet"}
        try:
            sql, missing = CT.expand_warehouse("SELECT count() FROM warehouse('stripe_customers')", 1)
            self.assertEqual(sql, "SELECT count() FROM url('http://127.0.0.1:19000/x.parquet', 'Parquet')")
            self.assertEqual(missing, [])
            self.assertEqual(CT.expand_warehouse("SELECT 1 FROM warehouse('nope')", 1)[1], ["nope"])
        finally:
            CT.warehouse_urls = orig


if __name__ == "__main__":
    unittest.main()
