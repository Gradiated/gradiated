"""qfacts SQL analysis tests (needs the PostHog venv for the HogQL parser):
    cd /opt/posthog-env/posthog && .venv/bin/python /opt/posthog-sft/env-research/twingen/v2/tests/test_qfacts_sql.py
"""
import os
import sys
import unittest

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)
sys.path.insert(0, "/opt/posthog-env")
import boot  # noqa: E402

boot.init()
import qfacts  # noqa: E402


class WrappedColumns(unittest.TestCase):
    """r1 card 12: coalesce(nullIf(properties.utm_source, ''), '(none)') AS x was not mapped to the property, so
    production's utm_source breakdown never reached the generator."""

    def test_wrapped_property_is_a_field(self):
        sql = ("SELECT coalesce(nullIf(properties.utm_source, ''), '(none)') AS src, ifNull(properties.plan, 'x') AS plan, "
               "count() AS cnt FROM events WHERE event = 'signup' GROUP BY src, plan")
        an = qfacts.analyze_sql(sql, {})
        cols = {c["name"]: c for c in an["result_cols"]}
        self.assertEqual(cols["src"]["kind"], "field")
        self.assertEqual(cols["src"]["path"], "properties.utm_source")
        self.assertEqual(cols["plan"]["path"], "properties.plan")
        self.assertEqual(an["shape"], "B")


if __name__ == "__main__":
    unittest.main()
