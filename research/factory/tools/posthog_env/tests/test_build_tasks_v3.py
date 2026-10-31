"""Unit tests for build_tasks_v3 rules (synthetic text only).

Run on the GPU host:  cd /opt/posthog-env/runner && python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/opt/posthog-env/runner")
import build_tasks_v3 as B  # noqa: E402

NOW = dt.date(2026, 10, 30)


class Dates(unittest.TestCase):
    """r1 cards 08/17/20: month-grain literals were shifted to the 12th/18th and matched no warehouse rows."""

    def test_month_start_in_daily_table_shifts(self):
        """b01 card 02: month-start rows of an attached daily table were kept while their neighbours shifted."""
        s, n, kept = B.shift_text("2026-09-30 | 5\n2026-10-01 | 7", 3, NOW)
        self.assertEqual(s, "2026-10-03 | 5\n2026-10-04 | 7")
        self.assertEqual(kept, 0)

    def test_monthly_table_kept(self):
        """b11 card 10: a monthly result table (all month starts) was shifted to the 18th."""
        s, n, kept = B.shift_text("mes|usuarios\n2026-08-01|5\n2026-09-01|7\n2026-10-01|9", 17, NOW)
        self.assertIn("2026-09-01", s)
        self.assertEqual((n, kept), (0, 3))

    def test_month_start_kept_day_dates_shift(self):
        s, n, kept = B.shift_text("where month = '2025-09-01' and day = '2025-09-14'", 11, NOW)
        self.assertIn("'2025-09-01'", s)
        self.assertIn("'2025-09-25'", s)
        self.assertEqual((n, kept), (1, 1))

    def test_prose_dates_still_shift(self):
        s, n, _ = B.shift_text("since Oct 2", 3, NOW)
        self.assertEqual(s, "since Oct 5")
        self.assertEqual(n, 1)


class FollowUps(unittest.TestCase):
    """r1 cards 01/10: bare "yes" turns and follow-ups naming the assistant's suggestions were sent as scripted turns."""

    def test_bare_ack_depends_on_answer(self):
        f = B.premise_flags(["count signups since yesterday", "yes"], ["Shall I re-check without the URL filter?", ""])
        self.assertTrue(f[1]["depends_on_answer"])
        self.assertEqual(f[1]["evidence"].get("ack"), 1)

    def test_phrase_from_answer_depends(self):
        turns = ["list our events and recommend dashboards", "now build the business referral performance one"]
        answers = ["I recommend: 1) Business referral performance dashboard 2) Search funnel", ""]
        self.assertTrue(B.premise_flags(turns, answers)[1]["depends_on_answer"])

    def test_independent_followup_stays(self):
        turns = ["weekly visitors last 12 weeks", "also break it down by country"]
        answers = ["Here are weekly visitors.", ""]
        self.assertFalse(B.premise_flags(turns, answers)[1]["depends_on_answer"])


class OwnText(unittest.TestCase):
    """b01 cards 02/09: deixis inside attached page context ("the result", "the query") marked every turn dependent."""

    CTX = "<attached_context>the result of the query: 2026-10-01 | 5</attached_context>"

    def test_context_stripped(self):
        self.assertEqual(B.own_text(self.CTX + " graph of users who onboarded"), "graph of users who onboarded")

    def test_context_deixis_ignored(self):
        turns = ["help me learn " + self.CTX, "graph of users who onboarded but have not ordered " + self.CTX]
        self.assertFalse(B.premise_flags(turns, ["Welcome! Here is how dashboards work.", ""])[1]["depends_on_answer"])

    def test_short_ui_label_quote_ignored(self):
        """b01 card 03: a quoted UI label ("All") counted as quoting the answer."""
        turns = ["top users of bulk reports", 'which search params do people use when they pick "All"?']
        self.assertFalse(B.premise_flags(turns, ["Filters: All, Recent. Top user ran 64 reports.", ""])[1]["depends_on_answer"])

    def test_number_with_unit_from_answer(self):
        """b01 card 06: "80 días" from the production answer was not detected."""
        turns = ["qué eventos puedo borrar", "y los de hace 80 días también?"]
        self.assertTrue(B.premise_flags(turns, ["Estos eventos no se ven desde hace 80 días.", ""])[1]["depends_on_answer"])

    def test_guillemet_quote_from_answer(self):
        turns = ["eventos sin uso", "qué significa «último uso» exactamente?"]
        self.assertTrue(B.premise_flags(turns, ["La columna «último uso» muestra la fecha.", ""])[1]["depends_on_answer"])


class DependencyR2(unittest.TestCase):
    def test_accent_folded_quote(self):
        """b01 card 06: user quoted "ultimo uso", production wrote "Último uso"."""
        turns = ["eventos sin uso", 'a que te refieres con "ultimo uso" ?']
        self.assertTrue(B.premise_flags(turns, ["| evento | Último uso |", ""])[1]["depends_on_answer"])

    def test_correction_depends(self):
        """b01 card 06: "No, pero me refiero a ..." corrects the production agent's reading."""
        turns = ["puedo borrar estos eventos?", "No, pero me refiero a los eventos que retorna"]
        self.assertTrue(B.premise_flags(turns, ["Puedes borrar el insight.", ""])[1]["depends_on_answer"])

    def test_context_identifier_from_answer_depends(self):
        """b01 card 10: the next turn's attached context holds the insight built from the production answer."""
        ctx = "<attached_context>insight game_play_seconds_v2 rows ...</attached_context>"
        turns = ["measure time on game pages", "change it to only count paid games " + ctx]
        self.assertTrue(B.premise_flags(turns, ["Saved as game_play_seconds_v2.", ""])[1]["depends_on_answer"])

    def test_docs_call(self):
        self.assertTrue(B.is_docs_call("search", {"kind": "docs", "query": "pricing"}))
        self.assertFalse(B.is_docs_call("execute_sql", {"query": "select 1"}))


class InitialMode(unittest.TestCase):
    """b02 review: tasks started in sql mode although production started in product_analytics (spec mode = final)."""

    def test_from_reminder(self):
        self.assertEqual(B.initial_mode("<system_reminder>Your initial mode is product_analytics.</system_reminder> hi", "sql"),
                         "product_analytics")

    def test_fallback_to_spec(self):
        self.assertEqual(B.initial_mode("hi", "sql"), "sql")
        self.assertIsNone(B.initial_mode("hi", "nonsense"))


class Filters(unittest.TestCase):
    def test_capture_placeholder(self):
        """r1 card 09: the whole prompt was a capture placeholder."""
        self.assertTrue(B.CAPTURE.search("[truncated: 429914 bytes too large for capture]"))

    def test_greeting(self):
        """r1 card 14: turn 0 was a bare greeting."""
        for g in ("hi", "Hello!", "hey there", "hola", "good morning"):
            self.assertTrue(B.GREETING.match(g), g)
        self.assertFalse(B.GREETING.match("hi, how many signups last week?"))

    def test_relative_day_words(self):
        self.assertTrue(B.RELDAY.search("how many since yesterday"))


if __name__ == "__main__":
    unittest.main()
