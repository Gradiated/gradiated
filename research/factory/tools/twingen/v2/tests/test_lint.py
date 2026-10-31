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
        rows = [pv(f"p{i}") for i in range(100)] + [("clicked_cta", f"p{i}", {}) for i in range(86)]
        self.assertIn("event_reach", checks(rows))  # round 3: 86% was implausible
        rows = [pv(f"p{i}") for i in range(100)] + [("clicked_cta", f"p{i}", {}) for i in range(60)]
        self.assertNotIn("event_reach", checks(rows))

    def test_repeat_once(self):
        rows = [pv(f"p{i}") for i in range(100)] + [("trial_converted", f"p{i % 25}", {}) for i in range(400)]
        self.assertIn("repeat_once", checks(rows))

    def test_lifecycle_reach_is_minor_and_family_counts_by_persons(self):
        rows = [pv(f"p{i}") for i in range(100)] + [("signed_up", f"p{i}", {}) for i in range(100)]
        self.assertEqual({f["severity"] for f in checks(rows)["event_reach"]}, {"minor"})
        rows = [("calc_page_view", f"p{i}", {}) for i in range(30)] + [("calc_run", f"p{i % 30}", {}) for i in range(200)]
        self.assertNotIn("funnel_order", checks(rows))

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

    def test_anonymized_hosts_are_minor(self):
        rows = [pv(f"p{i}", f"https://sub1.sub2.example-1.com/page{i % 4}", **{"$host": "sub1.sub2.example-1.com"})
                for i in range(100)]
        self.assertTrue(all(f["severity"] == "minor" for f in checks(rows).get("placeholder", [])))

    def test_third_party_host_and_url_dominance(self):
        rows = [pv(f"p{i}", "https://github.com/org/repo/pull/12") for i in range(10)]
        rows += [pv(f"p{i}", "https://shop.example/home?utm_source=x") for i in range(90)]
        c = checks(rows)
        self.assertIn("third_party_host", c)
        self.assertIn("url_dominance", c)

    def test_value_domain(self):
        rows = [pv(f"p{i}", trigger_status="https://shop.example/pricing", landing_url="https://shop.example/")
                for i in range(50)]
        c = checks(rows)
        self.assertEqual([f["detail"].split(":")[0] for f in c["value_domain"]], ["trigger_status"])

    def test_warehouse_join(self):
        d = twin([pv("p1")])
        os.makedirs(f"{d}/warehouse")
        pq.write_table(pa.table({"id": ["id_1", "id_2"]}), f"{d}/warehouse/x_organizations.parquet")
        pq.write_table(pa.table({"organization_id": ["orga_9", "orga_8"]}), f"{d}/warehouse/x_org_memberships.parquet")
        self.assertEqual([f["check"] for f in lint.lint_project(d)["findings"]], ["warehouse_join"])
        pq.write_table(pa.table({"organization_id": ["id_1", "id_2"]}), f"{d}/warehouse/x_org_memberships.parquet")
        self.assertEqual(lint.lint_project(d)["findings"], [])

    def test_warehouse_duplicate(self):
        d = twin([pv("p1")])
        os.makedirs(f"{d}/warehouse")
        for n in ("neon.hv.orgs", "hvneon_orgs"):
            pq.write_table(pa.table({"id": ["a"]}), f"{d}/warehouse/{n}.parquet")
        self.assertEqual([f["check"] for f in lint.lint_project(d)["findings"]], ["warehouse_duplicate"])

    def test_campaign_source(self):
        bad = [pv(f"p{i}", utm_campaign="google_search_brand", utm_source="facebook") for i in range(40)]
        self.assertIn("campaign_source", checks(bad))
        ok = [pv(f"p{i}", utm_campaign="google_search_brand", utm_source="google") for i in range(40)]
        self.assertNotIn("campaign_source", checks(ok))


if __name__ == "__main__":
    unittest.main()
