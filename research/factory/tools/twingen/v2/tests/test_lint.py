"""Unit tests for lint.py on small synthetic twins (twingen venv: pyarrow)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

import lint  # noqa: E402


def twin(rows: list[tuple[str, str, dict]]) -> str:
    d = tempfile.mkdtemp(prefix="lint_test_")
    pq.write_table(pa.table({"event": [r[0] for r in rows], "person_id": [r[1] for r in rows],
                             "properties": [json.dumps(r[2]) for r in rows]}), f"{d}/events.parquet")
    return d


def checks(rows) -> dict:
    out: dict = {}
    for f in lint.lint_project(twin(rows))["findings"]:
        out.setdefault(f["check"], []).append(f)
    return out


def pv(p, url="https://shop.example/home", **kw):
    return ("$pageview", p, {"$current_url": url, **kw})


class TestLint(unittest.TestCase):
    def test_clean_twin_has_no_findings(self):
        rows = [pv(f"p{i}", f"https://shop.example/page-{i % 7}") for i in range(200)]
        rows += [("signed_up", f"p{i}", {"plan": "pro"}) for i in range(40)]
        self.assertEqual(checks(rows), {})

    def test_event_reach(self):
        rows = [pv(f"p{i}") for i in range(100)] + [("clicked_cta", f"p{i}", {}) for i in range(95)]
        self.assertIn("event_reach", checks(rows))
        rows = [pv(f"p{i}") for i in range(100)] + [("clicked_cta", f"p{i}", {}) for i in range(60)]
        self.assertNotIn("event_reach", checks(rows))

    def test_ecommerce_funnel_order(self):
        rows = [pv(f"p{i}") for i in range(100)]
        rows += [("add_to_cart", f"p{i}", {}) for i in range(10)] + [("purchase", f"p{i}", {}) for i in range(30)]
        self.assertIn("funnel_order", checks(rows))

    def test_buyers_vs_visitors(self):
        rows = [pv(f"p{i}") for i in range(20)] + [("order_completed", f"p{i}", {}) for i in range(60)]
        self.assertIn("buyers_vs_visitors", checks(rows))

    def test_placeholder_values(self):
        rows = [pv(f"p{i}", **{"$config_defaults": "config_defaults_" + "abc"[i % 3]}) for i in range(100)]
        c = checks(rows)
        self.assertEqual(c["placeholder"][0]["severity"], "material")
        rows = [pv(f"p{i}", **{"app_version": "Version 2", "quarter": "Q3 2025"}) for i in range(100)]
        self.assertNotIn("placeholder", checks(rows))

    def test_third_party_host_and_url_dominance(self):
        rows = [pv(f"p{i}", "https://github.com/org/repo/pull/12") for i in range(10)]
        rows += [pv(f"p{i}", "https://shop.example/home?utm_source=x") for i in range(90)]
        c = checks(rows)
        self.assertIn("third_party_host", c)
        self.assertIn("url_dominance", c)

    def test_campaign_source(self):
        bad = [pv(f"p{i}", utm_campaign="google_search_brand", utm_source="facebook") for i in range(40)]
        self.assertIn("campaign_source", checks(bad))
        ok = [pv(f"p{i}", utm_campaign="google_search_brand", utm_source="google") for i in range(40)]
        self.assertNotIn("campaign_source", checks(ok))


if __name__ == "__main__":
    unittest.main()
