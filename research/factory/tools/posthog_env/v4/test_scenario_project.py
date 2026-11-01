import datetime as dt
import json
import unittest
from collections import defaultdict

from scenario_project import build


class ScenarioProject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
        cls.data = build(41, cls.now, people=60, days=35)

    def test_reproducible_and_no_future_or_pre_signup_events(self):
        self.assertEqual(self.data, build(41, self.now, people=60, days=35))
        people = {p["id"]: p for p in self.data["persons"]}
        for r in self.data["events"]:
            self.assertLess(r["timestamp"], self.now)
            self.assertGreaterEqual(r["timestamp"], people[r["person_id"]]["created_at"])
            self.assertEqual(r["distinct_id"], r["person_id"])
            props = json.loads(r["properties"])
            if props["$lib"] == "web":
                if props["$is_identified"]:
                    self.assertEqual(props["$user_id"], r["person_id"])
                else:
                    self.assertNotIn("$user_id", props)
                    self.assertFalse(props["$is_identified"])
                self.assertEqual(props["$session_id"], r["$session_id"])

    def test_web_sessions_have_one_person_and_start_with_pageview(self):
        sessions = defaultdict(list)
        for r in self.data["events"]:
            if r["$session_id"]:
                sessions[r["$session_id"]].append(r)
        for rows in sessions.values():
            self.assertEqual(len({r["person_id"] for r in rows}), 1)
            self.assertEqual(rows[0]["event"], "$pageview")
            self.assertLess((rows[-1]["timestamp"] - rows[0]["timestamp"]).total_seconds(), 1800)

    def test_report_outcomes_follow_their_own_start_and_creation(self):
        seen = defaultdict(set)
        for r in self.data["events"]:
            props = json.loads(r["properties"])
            key = (r["person_id"], props.get("report_id"))
            if r["event"] in ("report_export_succeeded", "report_export_failed"):
                self.assertTrue({"report_created", "report_export_started"} <= seen[key])
            if r["event"] == "summary_generated":
                self.assertIn("summary_requested", seen[key])
            seen[key].add(r["event"])

    def test_billing_joins_and_cost_arithmetic(self):
        accounts = {a["id"]: a for a in self.data["accounts"]}
        self.assertEqual(len(accounts), sum(p["is_identified"] for p in self.data["persons"]))
        self.assertEqual(len({x["id"] for x in self.data["invoices"]}), len(self.data["invoices"]))
        for invoice in self.data["invoices"]:
            self.assertEqual(invoice["person_id"], accounts[invoice["account_id"]]["person_id"])
            self.assertEqual(invoice["amount_usd"], 29)
        ai = [json.loads(r["properties"]) for r in self.data["events"] if r["event"] == "$ai_generation"]
        self.assertTrue(ai)
        for p in ai:
            self.assertAlmostEqual(p["$ai_total_cost_usd"], p["$ai_input_cost_usd"] + p["$ai_output_cost_usd"], places=6)

    def test_capability_boundaries_are_explicit(self):
        self.assertNotIn("session_replay", self.data["manifest"]["supported_families"])
        self.assertNotIn("errors_logs", self.data["manifest"]["supported_families"])
        self.assertIn("warehouse", self.data["manifest"]["supported_families"])

    def test_distinct_seeds_change_identities_and_regression_segment(self):
        other = build(42, self.now, people=60, days=35, split="test")
        self.assertEqual(other["manifest"]["split"], "test")
        self.assertNotEqual(other["ground_truth"]["export_regression"]["segment"],
                            self.data["ground_truth"]["export_regression"]["segment"])
        self.assertFalse({p["id"] for p in other["persons"]} & {p["id"] for p in self.data["persons"]})

    def test_numeric_definitions_match_values(self):
        defs = {d["name"]: d for d in self.data["definitions"]["property_definitions"] if d["type"] == 1}
        self.assertEqual(defs["$ai_input_tokens"]["property_type"], "Numeric")
        self.assertTrue(defs["$ai_total_cost_usd"]["is_numerical"])

    def test_ai_summaries_require_an_active_paid_subscription(self):
        paid = {}
        for r in self.data["events"]:
            if r["event"] == "subscription_started":
                paid[r["person_id"]] = r["timestamp"]
            if r["event"] in ("summary_requested", "$ai_generation", "summary_generated"):
                self.assertIn(r["person_id"], paid)
                self.assertGreaterEqual(r["timestamp"], paid[r["person_id"]])

    def test_anonymous_visitors_do_not_receive_accounts_or_core_product_events(self):
        anon = {p["id"] for p in self.data["persons"] if not p["is_identified"]}
        self.assertEqual(len(anon), 120)
        self.assertFalse(anon & {a["person_id"] for a in self.data["accounts"]})
        for r in self.data["events"]:
            if r["person_id"] in anon:
                self.assertIn(r["event"], ("$pageview", "signup_started", "signup_abandoned"))

    def test_visitor_ratio_can_reproduce_the_registered_only_control(self):
        control = build(41, self.now, people=60, days=35, anonymous_ratio=0)
        self.assertEqual(len(control["persons"]), 60)
        core = [r for r in self.data["events"] if r["person_id"] in {p["id"] for p in control["persons"]}]
        self.assertEqual(core, control["events"])

    def test_registered_users_have_a_linked_pre_signup_landing_journey(self):
        landing, completed = set(), set()
        for r in self.data["events"]:
            p = json.loads(r["properties"])
            if r["event"] == "$pageview" and p.get("$pathname") == "/":
                landing.add(r["person_id"])
            if r["event"] == "signup_completed":
                self.assertIn(r["person_id"], landing)
                self.assertTrue(p["$is_identified"])
                completed.add(r["person_id"])
        self.assertEqual(completed, {p["id"] for p in self.data["persons"] if p["is_identified"]})

    def test_registration_continues_into_the_final_week(self):
        recent = [r for r in self.data["events"] if r["event"] == "signup_completed"
                  and r["timestamp"] >= self.now - dt.timedelta(days=7)]
        self.assertGreater(len(recent), 0)


if __name__ == "__main__":
    unittest.main()
