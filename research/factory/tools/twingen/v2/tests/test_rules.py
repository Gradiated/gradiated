"""Unit tests for twin-generator rules (synthetic inputs only; no customer data).

Run on the GPU host from the v2 directory with the twingen venv:
    cd /opt/posthog-sft/env-research/twingen/v2 && ../.venv/bin/python -m unittest discover -s tests -v

Each test names the spot-check round and defect it guards against.
"""

from __future__ import annotations

import collections as C
import datetime as dt
import json
import os
import random
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
sys.path.insert(0, V2)
sys.path.insert(0, os.path.dirname(V2))

import gen2  # noqa: E402
import qfacts  # noqa: E402

NOW = dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.timezone.utc)


def project(**attrs) -> gen2.Project2:
    """A Project2 with only the attributes the rule under test reads (bypasses spec loading)."""
    p = object.__new__(gen2.Project2)
    base = dict(F={}, Q={}, S={"id": "test-spec"}, v2=C.Counter(), v2_info={}, now=NOW, H=90, n_persons=500,
                entity_person={}, entities={}, user_text="", ev_counts=C.Counter(), active=set(), ovr={})
    base.update(attrs)
    for k, v in base.items():
        setattr(p, k, v)
    return p


class FilterSeedZero(unittest.TestCase):
    """r1 card 12: a production SQL count of 0 for a filtered channel seeded 25 rows per query (98% of signups)."""

    def _proj(self, result_rows):
        qc = {"k": 0, "ok": True, "events": ["signup"], "window": {"interval_days": 7},
              "literals": [["events", "properties.utm_source", [{"op": "=", "values": ["newsletter_x"]}]]]}
        call = {"k": 0, "tool": "execute_sql", "rows": result_rows}
        return project(Q={"calls": [qc]}, F={"calls": [call]})

    def test_zero_result_seeds_nothing(self):
        p = self._proj([["0"]])
        rows = p.filter_seed_rows(random.Random(1))
        self.assertEqual([r for r in rows if r["props"].get("utm_source") == "newsletter_x"], [])
        self.assertEqual(p.v2["filter_seed_sql_zero_skipped"], 1)

    def test_positive_result_seeds_that_many(self):
        rows = self._proj([["12"]]).filter_seed_rows(random.Random(1))
        self.assertEqual(sum(r["props"].get("utm_source") == "newsletter_x" for r in rows), 12)

    def test_props_only_on_owning_events(self):
        """b07 card 01: amount_usd > 0 was seeded onto every event of "event IN (gen, signup, revenue)"."""
        qc = {"k": 0, "ok": True, "events": ["media_gen", "signup", "revenue"], "window": {"interval_days": 7},
              "literals": [["events", "properties.amount_usd", [{"op": "=", "values": ["5"]}]]]}
        spec = {"id": "t", "events": {"revenue": {"properties": {"amount_usd": {}}}, "media_gen": {"properties": {}},
                                      "signup": {"properties": {}}}}
        p = project(Q={"calls": [qc]}, F={"calls": [{"k": 0, "tool": "execute_sql", "rows": [["40"]]}]}, S=spec)
        rows = p.filter_seed_rows(random.Random(1))
        self.assertEqual({r["event"] for r in rows}, {"revenue"})

    def test_unknown_count_still_seeds(self):
        rows = self._proj([["a", "b"], ["c", "d"]]).filter_seed_rows(random.Random(1))
        self.assertEqual(len(rows), 25)


class FilterSeedMultiAgg(unittest.TestCase):
    """r1 card 12: a one-row countIf query (total 249, channel 0, ...) seeded 249 channel rows from the first number."""

    def test_conditional_aggregates_seed_nothing(self):
        qc = {"k": 0, "ok": True, "events": ["signup"], "window": {"interval_days": 7},
              "literals": [["events", "properties.utm_source", [{"op": "=", "values": ["newsletter_x"]}]]]}
        call = {"k": 0, "tool": "execute_sql", "rows": [["249", "0", "217"]]}
        p = project(Q={"calls": [qc]}, F={"calls": [call]})
        self.assertEqual(p.filter_seed_rows(random.Random(1)), [])
        self.assertEqual(p.v2["filter_seed_sql_multi_agg_skipped"], 1)


class FilterOnlyValues(unittest.TestCase):
    """r1 card 12: a property known only from filters used the filter value for every event."""

    def test_zero_filter_values(self):
        qc = {"k": 0, "ok": True, "literals": [["events", "properties.utm_source", [{"op": "=", "values": ["nl"]}]]]}
        p = project(Q={"calls": [qc]}, F={"calls": [{"k": 0, "rows": [["0"]]}]})
        self.assertEqual(p.zero_filter_values(), {("utm_source", "nl")})

    def test_mix_share(self):
        m = gen2.FilterMix(lambda ctx: "organic", ["nl"], 0.1, random.Random(5))
        out = C.Counter(m({}) for _ in range(5000))
        self.assertAlmostEqual(out["nl"] / 5000, 0.1, delta=0.02)
        self.assertEqual(C.Counter(gen2.FilterMix(lambda ctx: "o", [], 0.0, random.Random(5))({}) for _ in range(100)), {"o": 100})


class NullSentinel(unittest.TestCase):
    """b01 cards 01/03: SQL "(null)" display values became real property values on every event, and column aliases
    of exploratory queries became invented properties."""

    def test_null_values_dropped_and_null_only_sql_props_removed(self):
        spec = {"events": {"export": {"properties": {
            "tab": {"values": ["(null)"], "sources": {"sql": 1, "result_values": 1}},
            "plan": {"values": ["(null)", "pro"], "sources": {"sql": 1}},
            "location": {"values": ["(null)"], "sources": {"taxonomy_props": 1}}}}}, "unscoped": {}}
        n = gen2.clean_null_props(spec)
        props = spec["events"]["export"]["properties"]
        self.assertNotIn("tab", props)
        self.assertEqual(props["plan"]["values"], ["pro"])
        self.assertEqual(props["location"]["values"], [])
        self.assertEqual(n["null_only_props_removed"], 1)


class PriorNullScrub(unittest.TestCase):
    """b01 card 01: "type"/"plan" from generic priors were "(null)" on all 25k events of one event."""

    def test_scrub_keeps_real_values(self):
        sm = gen2.gen.Sampler("plan", "String", ["(null)", "pro", "free"], None, None, None, random.Random(1))
        self.assertEqual(gen2.scrub_sampler(sm), 1)
        self.assertEqual(set(sm.choices), {"pro", "free"})
        self.assertTrue(all(sm({}) in ("pro", "free") for _ in range(200)))

    def test_scrub_all_null_falls_back_to_shape(self):
        sm = gen2.gen.Sampler("type", "String", ["(null)"], None, None, None, random.Random(1))
        gen2.scrub_sampler(sm)
        vals = {str(sm({"ts": None})) for _ in range(200)}
        self.assertTrue(vals)
        self.assertFalse(vals & {"(null)", "None", "null", ""})


class StubEvents(unittest.TestCase):
    """b01 card 05: invented "mcp organization switched" was the third-largest event."""

    def test_capped_unless_named(self):
        p = project(active={"mcp organization switched": {}, "Application opened": {}, "$exception": {}},
                    invented=["mcp organization switched", "Application opened", "$exception"],
                    targets={"mcp organization switched": [200.0, 50.0], "Application opened": [80.0, 20.0],
                             "$exception": [30.0, 5.0]}, ref_text="please look at application opened")
        p.cap_stub_events()
        self.assertNotIn("mcp organization switched", p.targets)
        self.assertNotIn("mcp organization switched", p.active)
        self.assertEqual(p.targets["Application opened"], [80.0, 20.0])
        self.assertEqual(p.targets["$exception"], [30.0, 5.0])


class OverrideZeroed(unittest.TestCase):
    """b01 card 06 (curation): stale events stopped by a factor-0 override must not get rows back near "now"."""

    def test_zeroed_events(self):
        p = project(ovr={"spikes": [{"event": "a", "from": "2026-08-01", "to": "2026-10-30", "factor": 0},
                                    {"event": "b", "from": "2026-08-01", "to": "2026-08-02", "factor": 3}]})
        self.assertEqual(p.override_zeroed_events(), {"a"})


class GroupDistributions(unittest.TestCase):
    """r1 card 12: production's breakdown of utm_source on signups (none 114, google 29, ...) was ignored."""

    QF = {"event_seeds": [{"events": ["signup"], "where": [["events", "properties.is_test", []]], "groups": [
        {"dims": {"properties.utm_source": "(none)"}, "aggs": {"count()": 114}},
        {"dims": {"properties.utm_source": "google"}, "aggs": {"count()": 29}},
        {"dims": {"properties.utm_source": "bing"}, "aggs": {"count()": 7}}]}]}

    def test_distribution(self):
        d = gen2.group_distributions(self.QF)
        self.assertEqual(d[("signup", "utm_source")], {"(none)": 114.0, "google": 29.0, "bing": 7.0})

    def test_filtered_dim_skipped(self):
        qf = json.loads(json.dumps(self.QF))
        qf["event_seeds"][0]["where"] = [["events", "properties.utm_source", []]]
        self.assertEqual(gen2.group_distributions(qf), {})

    def test_sampler_interface(self):
        """gen.py calls .plan(n), .source and .pending on every event sampler (missing .plan crashed generation)."""
        g = gen2.GroupDist({"a": 1}, random.Random(0))
        self.assertIsNone(g.plan(10))
        self.assertEqual(g.source, "spec")

    def test_sampler_none_means_unset(self):
        g = gen2.GroupDist({"(none)": 114, "google": 29, "bing": 7}, random.Random(2))
        out = C.Counter(g({}) for _ in range(6000))
        self.assertAlmostEqual(out[None] / 6000, 114 / 150, delta=0.03)
        self.assertNotIn("(none)", out)


class Attribution(unittest.TestCase):
    """b02 review: utm_medium=cpc on 100% of 88k pageviews (taxonomy listed one value, so every event got it)."""

    def test_presence_table(self):
        self.assertEqual(gen2.attribution_presence("utm_medium"), 0.2)
        self.assertEqual(gen2.attribution_presence("$initial_utm_source"), 0.2)
        self.assertEqual(gen2.attribution_presence("gclid"), 0.05)
        self.assertIsNone(gen2.attribution_presence("plan"))

    def test_cache_overflow(self):
        """eval_v1 build: a twin with >200k sessions crashed with KeyError after the cache cleared itself."""
        w = gen2.SessionAttr(lambda ctx: "cpc", 1.0, "t")
        w.cache = {i: None for i in range(200000)}
        self.assertEqual(w({"session_id": "new"}), "cpc")

    def test_minority_and_constant_per_session(self):
        w = gen2.SessionAttr(lambda ctx: "cpc", 0.2, "t")
        vals = {sid: w({"session_id": sid}) for sid in range(5000)}
        share = sum(v == "cpc" for v in vals.values()) / 5000
        self.assertAlmostEqual(share, 0.2, delta=0.03)
        self.assertTrue(all(w({"session_id": sid}) == vals[sid] for sid in range(200)))


class ValuePools(unittest.TestCase):
    """b02 review: placeholder values (city_b, "Name 9", gclid_a) in 7 of 10 tasks; agents reported them as bad data."""

    SPEC = {"events": {"quiz_completed": {"properties": {
        "org_size": {"type": "String", "values": []},
        "plan": {"type": "String", "values": ["pro"]},
        "user_id": {"type": "String", "values": []},
        "score": {"type": "Numeric", "values": []}}}},
        "unscoped": {}, "entities": {"person": {"properties": {"city": {"type": None, "values": []}}}}}

    def test_candidates(self):
        keys = gen2.valuepools.candidates(self.SPEC, gen2.shape_of, {}, gen2.gen.stem_of)
        self.assertIn("quiz_completed::org_size", keys)
        self.assertIn("person::city", keys)
        self.assertNotIn("quiz_completed::plan", keys)      # has observed values
        self.assertNotIn("quiz_completed::user_id", keys)   # id shape: generated ids, not a value pool
        self.assertNotIn("quiz_completed::score", keys)     # numeric

    def test_placeholder_regex(self):
        P = gen2.valuepools.PLACEHOLDER
        for bad in ("org_size_b", "Name 9", "Flow 20", "example company 3", "n/a"):
            self.assertTrue(P.match(bad), bad)
        for ok in ("11-50", "Sydney", "pro_annual", "v2.1.0"):
            self.assertFalse(P.match(ok), ok)

    def test_hook_uses_pool(self):
        gen2.install_pool_hook()
        gen2.activate_pools({"quiz_completed::org_size": [["11-50", 5.0], ["51-200", 2.0]]})
        try:
            sm = gen2.gen.Sampler("org_size", "String", [], None, None, None, random.Random(1))
            self.assertEqual(sm.source, "llm_pool")
            self.assertTrue({sm({}) for _ in range(100)} <= {"11-50", "51-200"})
            other = gen2.gen.Sampler("color_theme", "String", [], None, None, None, random.Random(1))
            self.assertNotEqual(other.source, "llm_pool")
        finally:
            gen2.activate_pools({})


class GeoAndSessions(unittest.TestCase):
    """b07 review: country code 'US' on German/UK rows, no Belgium although production was mostly Belgian; UTM triples
    like linkedin/email/q3_promo; 30-65% of sessions started with a non-pageview event."""

    def test_catalog_has_extra_countries(self):
        cat = gen2.geo_catalog()
        self.assertIn("BE", cat)
        self.assertIn("US", cat)
        self.assertEqual(cat["BE"][1], "Belgium")

    def test_production_countries(self):
        spec = {"events": {"$pageview": {"properties": {"$geoip_country_name": {"values": ["Belgium", "Netherlands"]}}}},
                "unscoped": {}, "entities": {"person": {"properties": {"$geoip_country_code": {"values": ["BE"]}}}}}
        mix = gen2.production_countries(spec, {})
        self.assertGreater(mix["BE"], mix["NL"])

    def test_trend_breakdown_countries(self):
        """b07 card 02: Belgium 492 / US 17 came from a Trends breakdown result, not from spec values."""
        F = {"calls": [{"schema": {"kind": "TrendsQuery", "series": [{"event": "$pageview"}],
                                   "breakdownFilter": {"breakdown": "$geoip_country_name", "breakdown_type": "event"}},
                        "cols": ["Date range", "Aggregated value for Belgium breakdown for the value `Belgium`",
                                 "Aggregated value for The Netherlands breakdown for the value `The Netherlands`"],
                        "rows": [["2026-09-14 to 2026-10-14", "492", "12"]]}]}
        self.assertEqual(gen2.trend_breakdown_distributions(F), {("$pageview", "$geoip_country_name"): {"Belgium": 492.0, "The Netherlands": 12.0}})
        mix = gen2.production_countries({"events": {}}, {}, F)
        self.assertGreater(mix["BE"], 10 * mix["NL"])

    def test_breakdowns_list_schema(self):
        """b07: newer insights store breakdowns as a list ({"breakdowns": [{"property", "type"}]})."""
        self.assertEqual(gen2.breakdown_prop({"breakdowns": [{"property": "$geoip_country_name", "type": "event"}]}),
                         ("$geoip_country_name", "event"))
        self.assertEqual(gen2.breakdown_prop({"breakdown": "$browser"}), ("$browser", "event"))
        self.assertEqual(gen2.breakdown_prop({"breakdowns": [{"property": "a"}, {"property": "b"}]}), (None, ""))

    def test_coherent_utm(self):
        a = gen2.coherent_utm("linkedin", ["email", "social", "cpc"], ["q3", "brand"])
        self.assertEqual(a, gen2.coherent_utm("linkedin", ["email", "social", "cpc"], ["q3", "brand"]))
        self.assertEqual(a[0], "social")  # catalog default medium when production uses it

    def test_landing_pageview_first(self):
        import pyarrow as pa
        t0 = 1_700_000_000_000_000
        tab = pa.table({"event": ["$autocapture", "$pageview", "$pageleave"], "$session_id": ["s1", "s1", "s1"],
                        "timestamp": pa.array([t0, t0 + 5_000_000, t0 + 9_000_000], pa.int64()).cast(pa.timestamp("us", tz="UTC")),
                        "properties": ["{}", '{"utm_source": "linkedin", "utm_medium": "email"}', "{}"]})
        p = project(web=True, utm_vals={"utm_medium": ["email", "social"], "utm_campaign": ["q3"]})
        out = p.coherent_sessions(tab)
        ts = out.column("timestamp").cast(pa.int64()).to_pylist()
        self.assertLess(ts[1], ts[0])
        self.assertIn('"utm_medium":"social"', out.column("properties").to_pylist()[1])


class ConversationPages(unittest.TestCase):
    """b07: tasks dropped because the twin had generic /pricing,/login pages instead of the conversation's /chat,
    /gamelanding/<id>/play or article slugs; task host example-1.com vs twin host app.<fake>.com."""

    def test_sources(self):
        spec = {"tasks": [{"text": "users on https://www.example-1.com/chat and https://www.example-1.com/pricing."}]}
        facts = {"calls": [{"sql": "select count() from events where properties.$pathname like '%/gamelanding/abc/play%'",
                            "rows": [["/blog/garden-tips", "120"], ["/2024/05", "3"], ["2026-10-01", "4"]]}]}
        urls, paths = gen2.conversation_pages(spec, facts)
        self.assertIn("https://www.example-1.com/chat", urls)
        self.assertIn("https://www.example-1.com/pricing", urls)
        self.assertIn("/gamelanding/abc/play", paths)
        self.assertIn("/blog/garden-tips", paths)
        self.assertNotIn("/2024/05", paths)


class BackgroundPopulation(unittest.TestCase):
    """b07 card 01: people existed only through the 3 named events, so 765/781 generated photos and 69% paid."""

    def test_custom_only_web_project(self):
        p = project(S={"id": "t", "events": {"media_gen": {"standard": False, "properties": {}},
                                             "revenue": {"standard": False, "properties": {}}}})
        self.assertTrue(p.needs_background_population())

    def test_not_when_pageviews_or_mobile(self):
        self.assertFalse(project(S={"id": "t", "events": {"$pageview": {"standard": True}, "x": {"standard": False}}})
                         .needs_background_population())
        mob = {"x": {"standard": False, "properties": {"$lib": {"values": ["posthog-ios"]}}}}
        self.assertFalse(project(S={"id": "t", "events": mob}).needs_background_population())


class MobileAndFailures(unittest.TestCase):
    """b10: an iOS app generated with $lib=web and desktop OSes; payment_failed 737 vs payment_succeeded 7."""

    def test_mobile_platform(self):
        spec = {"events": {"onboarding_step_viewed": {"properties": {"$app_version": {"values": ["2.1"]},
                                                                     "$os_name": {"values": ["iOS"]}}}}}
        self.assertEqual(gen2.mobile_platform(spec), "ios")
        self.assertIsNone(gen2.mobile_platform({"events": {"$pageview": {}, "x": {"properties": {"$app_version": {}}}}}))
        self.assertIsNone(gen2.mobile_platform({"events": {"x": {"properties": {}}}}))

    def test_success_sibling(self):
        names = {"payment_failed", "payment_succeeded", "export_error", "export_completed", "login"}
        self.assertEqual(gen2.success_sibling("payment_failed", names), "payment_succeeded")
        self.assertEqual(gen2.success_sibling("export_error", names), "export_completed")
        self.assertIsNone(gen2.success_sibling("login", names))

    def test_failure_ratio(self):
        p = project(targets={"payment_failed": [737.0, 50.0], "payment_succeeded": [7.0, 5.0]})
        p.failure_ratios()
        self.assertEqual(p.targets["payment_succeeded"], [7.0, 5.0])
        self.assertLessEqual(p.targets["payment_failed"][0], 0.7 + 1e-9)


class SiblingOrder(unittest.TestCase):
    """b10: paywall_dismissed 919 vs paywall_shown 61; checkout_started > add_to_cart; $groupidentify 46% of events."""

    def test_parent_event(self):
        names = {"paywall_shown", "paywall_dismissed", "add_to_cart", "checkout_started", "onboarding_started",
                 "onboarding_completed"}
        self.assertEqual(gen2.parent_event("paywall_dismissed", names), "paywall_shown")
        self.assertEqual(gen2.parent_event("checkout_started", names), "add_to_cart")
        self.assertEqual(gen2.parent_event("onboarding_completed", names), "onboarding_started")
        self.assertIsNone(gen2.parent_event("paywall_shown", names))

    def test_caps(self):
        p = project(targets={"paywall_shown": [61.0, 30.0], "paywall_dismissed": [919.0, 200.0],
                             "$groupidentify": [800.0, 500.0]}, D=1000.0)
        p.sibling_order()
        self.assertLessEqual(p.targets["paywall_dismissed"][0], 61.0)
        self.assertLessEqual(p.targets["$groupidentify"][1], 300.0)
        self.assertLessEqual(p.targets["$groupidentify"][0], p.targets["$groupidentify"][1])


class Journeys(unittest.TestCase):
    """b11: later funnel steps without earlier ones (151/184 calc runners never viewed the calc page); sign_up repeated
    and after product use for 48% of people."""

    def _tab(self, rows):
        import pyarrow as pa
        t0 = 1_700_000_000_000_000
        return pa.table({
            "event": [r[0] for r in rows], "person_id": [r[1] for r in rows], "distinct_id": [r[1] for r in rows],
            "person_properties": ["{}"] * len(rows), "$session_id": [f"s-{r[1]}" for r in rows],
            "$window_id": [f"w-{r[1]}" for r in rows], "properties": ['{"$session_id": "s-%s"}' % r[1] for r in rows],
            "timestamp": pa.array([t0 + r[2] * 1_000_000 for r in rows], pa.int64()).cast(pa.timestamp("us", tz="UTC"))})

    def test_family_link_needs_root_volume(self):
        """round 3: 1,795 refund_ask_posted were pinned onto 40 refund_home_row_viewed rows (a product area, not a
        causal family)."""
        rows = [("refund_home_row_viewed", "a", 10)] + [("refund_ask_posted", f"p{i}", 20 + i) for i in range(10)]
        out = project().causal_children(self._tab(rows))
        pid = out.column("person_id").to_pylist()
        self.assertEqual(len({pid[i] for i in range(1, 11)}), 10)

    def test_repeat_use_family_keeps_link(self):
        """regress b11-0058: calc_run (several per calc_page_view) must follow calc_page_view."""
        self.assertEqual(gen2.causal_parent("calc_run", {"calc_run", "calc_page_view"}, {"calc_run": 10, "calc_page_view": 3}),
                         "calc_page_view")
        self.assertIsNone(gen2.causal_parent("refund_ask_posted", {"refund_ask_posted", "refund_home_row_viewed"},
                                             {"refund_ask_posted": 1795, "refund_home_row_viewed": 40}))

    def test_gated_family_member_gets_reach_cap(self):
        """round 4: a family member failing the root-volume gate was skipped by adopters and not moved by
        causal_children, reaching 95%+ of persons."""
        import pyarrow as pa
        t0 = 1_700_000_000_000_000
        rows = [("$pageview", f"p{i}", t0 + i) for i in range(200)] + [("cc_video_viewed", "p0", t0 + 999)]
        rows += [("cc_video_restarted", f"p{i}", t0 + 1000 + i) for i in range(200)]
        tab = pa.table({"event": [r[0] for r in rows], "person_id": [r[1] for r in rows],
                        "distinct_id": [r[1] for r in rows], "person_properties": ["{}"] * len(rows),
                        "$session_id": [f"s{r[1]}" for r in rows], "$window_id": [f"w{r[1]}" for r in rows],
                        "timestamp": pa.array([r[2] for r in rows], pa.int64()).cast(pa.timestamp("us", tz="UTC"))})
        out = project().adopters(tab)
        ev, pid = out.column("event").to_pylist(), out.column("person_id").to_pylist()
        reach = len({pid[i] for i, e in enumerate(ev) if e == "cc_video_restarted"}) / 200
        self.assertLessEqual(reach, 0.8)

    def test_purchase_keeps_buyer(self):
        """round 3: moving every purchase to a random pageview spread it to 8.5k of 9k persons."""
        rows = [("$pageview", "a", 10), ("$pageview", "b", 50), ("$pageview", "c", 60), ("purchase", "b", 20),
                ("purchase", "x", 70)]
        out = project().causal_children(self._tab(rows))
        ev, pid = out.column("event").to_pylist(), out.column("person_id").to_pylist()
        ts = out.column("timestamp").cast(__import__("pyarrow").int64()).to_pylist()
        self.assertEqual(pid[3], "b")
        self.assertGreater(ts[3], ts[1])  # moved after b's first pageview
        self.assertIn(pid[4], {"a", "b", "c"})  # a buyer who never visited takes a visit row

    def test_mobile_twin_runs_causal_and_lifecycle(self):
        """round 3: a non-web twin returned from coherent_sessions before causal_children and lifecycle_once."""
        p = project(web=False)
        calls = []
        p.causal_children = lambda t: calls.append("causal") or t
        p.lifecycle_once = lambda t: calls.append("lifecycle") or t
        p.coherent_sessions(self._tab([("app_opened", "a", 10)]))
        self.assertEqual(calls, ["causal", "lifecycle"])

    def test_children_follow_parents(self):
        rows = [("calc_page_view", "a", 10), ("calc_page_view", "b", 20), ("calc_run", "c", 30), ("calc_run", "d", 40)]
        p = project()  # family rule: calc_run's parent is calc_page_view
        out = p.causal_children(self._tab(rows))
        ev, pid = out.column("event").to_pylist(), out.column("person_id").to_pylist()
        ts = out.column("timestamp").cast(__import__("pyarrow").int64()).to_pylist()
        viewers = {pid[i]: ts[i] for i, e in enumerate(ev) if e == "calc_page_view"}
        for i, e in enumerate(ev):
            if e == "calc_run":
                self.assertIn(pid[i], viewers)
                self.assertGreater(ts[i], viewers[pid[i]])

    def test_family_parent(self):
        names = {"calc_page_view", "calc_run", "calc_reset", "ls_solution_ready", "ls_solution_complete"}
        self.assertEqual(gen2.family_parent("calc_run", names), "calc_page_view")
        self.assertIsNone(gen2.family_parent("calc_page_view", names))
        self.assertEqual(gen2.parent_event("ls_solution_complete", names), "ls_solution_ready")

    def test_lifecycle_repeat_moves_to_new_person(self):
        rows = [("app_used", "a", 10), ("sign_up", "a", 50), ("sign_up", "a", 90), ("app_used", "c", 80)]
        out = project().lifecycle_once(self._tab(rows))
        ev, pid = out.column("event").to_pylist(), out.column("person_id").to_pylist()
        self.assertEqual(sorted(pid[i] for i, e in enumerate(ev) if e == "sign_up"), ["a", "c"])

    def test_lifecycle_once_keeps_time(self):
        rows = [("app_used", "a", 10), ("sign_up", "a", 50), ("sign_up", "a", 90), ("sign_up", "b", 5)]
        out = project().lifecycle_once(self._tab(rows))
        ev, pid = out.column("event").to_pylist(), out.column("person_id").to_pylist()
        self.assertEqual(sum(1 for i, e in enumerate(ev) if e == "sign_up" and pid[i] == "a"), 1)

    def test_lifecycle_once_names(self):
        for e in ("trial_converted", "email_verified", "user_email_verified", "account_activated", "signed_up"):
            self.assertTrue(gen2.LIFECYCLE_ONCE.match(e), e)
        for e in ("payment_succeeded", "page_verified_badge_shown"):
            self.assertFalse(gen2.LIFECYCLE_ONCE.match(e), e)

    def test_lifecycle_child_repeat_is_dropped(self):
        """regress f8f5: onboarding completed repeats went to new persons who never started onboarding."""
        rows = [("onboarding_started", "a", 10), ("onboarding_completed", "a", 50), ("onboarding_completed", "a", 90),
                ("app_used", "c", 80)]
        out = project().lifecycle_once(self._tab(rows))
        ev, pid = out.column("event").to_pylist(), out.column("person_id").to_pylist()
        self.assertEqual([pid[i] for i, e in enumerate(ev) if e == "onboarding_completed"], ["a"])

class WarehouseValues(unittest.TestCase):
    """eval_v1 audit: org ids '' / '_other' (no joins), month column 'month_0'..'month_5'."""

    def test_sentinels_and_dates(self):
        p = project(pre_days=0)
        tr = random.Random(1)
        v = p.wh_values("t", "org_id", {"type": "string", "values": ["", "_other", "org_a1", "org_b2"]}, 50, tr, gen2.UF(), {}, {})
        self.assertTrue(set(v) <= {"org_a1", "org_b2"})
        m = p.wh_values("t", "month", {"type": "string", "values": []}, 20, tr, gen2.UF(), {}, {})
        self.assertTrue(all(re.match(r"^\d{4}-\d\d-01$", x) for x in m))


class WarehouseNameKeys(unittest.TestCase):
    """round 3: org_memberships.organization_id ('orga_...') never matched organizations.id ('id_...')."""

    def test_name_foreign_keys(self):
        tables = {"hv_db_organizations": {"columns": {"id": {}, "name": {}}},
                  "hv_db_org_memberships": {"columns": {"organization_id": {}, "user_email": {}}},
                  "hv_db_applications": {"columns": {"id": {}, "organization_id": {}, "category_id": {}}},
                  "hv_db_categories": {"columns": {"id": {}}}}
        fk = set(gen2.name_foreign_keys(tables))
        self.assertIn((("hv_db_org_memberships", "organization_id"), ("hv_db_organizations", "id")), fk)
        self.assertIn((("hv_db_applications", "organization_id"), ("hv_db_organizations", "id")), fk)
        self.assertIn((("hv_db_applications", "category_id"), ("hv_db_categories", "id")), fk)
        self.assertEqual(len(fk), 3)

    def test_dotted_and_flat_names_are_one_table(self):
        tables = {"harborview_dbneon_organizations": {}}
        self.assertEqual(gen2.Project2.canon_table("neon.harborview_db.organizations", tables),
                         "harborview_dbneon_organizations")
        self.assertEqual(gen2.Project2.canon_table("harborview_dbneon_organizations", {"neon.harborview_db.organizations": {}}),
                         "neon.harborview_db.organizations")
        self.assertEqual(gen2.Project2.canon_table("stripe.acme.charges", {"harborview_dbneon_organizations": {}}),
                         "stripe.acme.charges")


class RoundB13Artifacts(unittest.TestCase):
    """round 3 audit: posthog.com pages for non-PostHog businesses, Application*/mcp* trickle in web twins,
    $entry_utm_term on custom events, userN@example.com event emails."""

    def test_business_events_and_sane_pages(self):
        vp = gen2.valuepools
        spec = {"events": {"$ai_generation": {"sources": ["taxonomy_list"]}, "Application Opened": {"sources": ["taxonomy_list"]},
                           "listing_published": {"sources": ["sql"]}, "$pageview": {"sources": ["sql"]}}}
        self.assertEqual(vp.business_events(spec, 10), ["listing_published", "$pageview"])
        self.assertEqual(vp.sane_pages({"host": "us.posthog.com", "paths": [["/home", 1]]}), {})
        self.assertEqual(vp.sane_pages({"host": "app.acme.com", "paths": [["/project/2/insights", 1], ["/pricing", 2]]}),
                         {"host": "app.acme.com", "paths": [["/pricing", 2]]})

    def test_email_follows_person(self):
        import values
        smp = values.Sampler("email", "String", prior={"values": [["user9@example.com", 5]]})
        self.assertEqual(smp.mode, "person_email")
        self.assertEqual(smp({"person": {"email": "ana@acme.io"}}), "ana@acme.io")  # a fully built, callable sampler

    def test_session_level_and_failed_sql_props_skipped(self):
        import gen
        self.assertTrue("$entry_utm_term".startswith(gen.SESSION_LEVEL))
        self.assertEqual(gen.FAILED_SOURCES, {"sql_failed"})
        self.assertTrue(gen2.STUB_EVENT.match("Deep link opened"))


class RoundB14Coherence(unittest.TestCase):
    """round 4: properties that don't fit their event (filler from other projects, $el_text on views, donor
    pageview props on seeded rows) and platform values contradicting $os/$lib."""

    def test_device_props(self):
        f = gen2.device_props
        self.assertEqual(f({"platform": "iOS", "is_native": True}, "Windows", "web"), {"platform": "Web", "is_native": False})
        self.assertEqual(f({"platform": "android", "is_native": "false"}, "Android", "posthog-android"),
                         {"platform": "android", "is_native": "true"})
        self.assertEqual(f({"platform": "IOS", "os": "x"}, "iOS", "posthog-ios"), {"platform": "IOS", "os": "iOS"})

    def test_channel_referrer(self):
        d = {"utm_source": "newsletter", "utm_medium": "email", "$referring_domain": "www.google.com", "$search_engine": "google"}
        gen2.channel_referrer(d)
        self.assertEqual((d["$referring_domain"], d.get("$search_engine")), ("$direct", None))
        d = {"utm_source": "google", "utm_medium": "cpc", "$referring_domain": "$direct"}
        gen2.channel_referrer(d)
        self.assertEqual((d["$referring_domain"], d["$search_engine"]), ("www.google.com", "google"))
        d = {"utm_source": "facebook", "utm_medium": "paid_social", "$referrer": "https://www.google.com/"}
        gen2.channel_referrer(d)
        self.assertEqual(d["$referring_domain"], "www.facebook.com")

    def test_mobile_tuple(self):
        d = gen2.mobile_tuple({"$lib": "posthog-ios", "$os": "Android", "$device_manufacturer": "Samsung",
                               "$device_model": "Pixel 8", "$browser": "Chrome"})
        self.assertEqual((d["$os"], d["$device_manufacturer"], d["$device_model"]), ("iOS", "Apple", "iPhone 15"))
        self.assertNotIn("$browser", d)
        d = gen2.mobile_tuple({"$lib": "posthog-android", "$os": "iOS", "$device_model": "iPhone"})
        self.assertEqual(d["$os"], "Android")
        self.assertIn(d["$device_manufacturer"], ("Samsung", "Pixel", "OnePlus"))
        self.assertEqual(gen2.mobile_tuple({"$lib": "web", "$os": "Windows"}), {"$lib": "web", "$os": "Windows"})

    def test_donor_other_event_lends_context_only(self):
        p = project()
        donors = ({}, {"p1": ['{"$browser": "Chrome", "collection_id": "c1", "$el_text": "Buy"}']}, [])
        out = p._with_donor({"workflow": "x"}, "$pageleave", "p1", donors, random.Random(0))
        self.assertEqual(out, {"$browser": "Chrome", "workflow": "x"})

    def test_url_coherent(self):
        d = gen2.url_coherent({"$current_url": "https://a.io/play/x?y=1", "$pathname": "/settings", "$host": "b.io"},
                              {"$current_url": 1})
        self.assertEqual((d["$host"], d["$pathname"]), ("a.io", "/play/x"))
        d = gen2.url_coherent({"$current_url": "https://a.io/old", "$pathname": "/new"}, {"$pathname": 1})
        self.assertEqual(d["$current_url"], "https://a.io/new")

    def test_donor_context_from_own_person(self):
        """round 8: rows added by overrides took another person's country and OS from a same-event donor."""
        p = project()
        donors = ({"signup": ['{"$geoip_country_code": "DE", "$os": "Windows", "plan": "pro", "$current_url": "https://x.io/s"}']},
                  {"p1": ['{"$geoip_country_code": "BR", "$os": "Android", "$current_url": "https://x.io/"}']}, [])
        out = p._with_donor({}, "signup", "p1", donors, random.Random(0))
        self.assertEqual((out["$geoip_country_code"], out["$os"], out["plan"], out["$current_url"]),
                         ("BR", "Android", "pro", "https://x.io/s"))

    def test_unscoped_evidence(self):
        p = project(Q={"calls": [{"sql": "select properties.plan_tier from events"}]}, F={}, user_text="")
        self.assertTrue(p.unscoped_evidenced("plan_tier"))
        self.assertFalse(p.unscoped_evidenced("method"))

    def test_custom_string_props_skip_cross_project_values(self):
        import values
        smp = values.Sampler("method", "String", prior={"values": [["POST", 4], ["GET", 3]]})
        self.assertNotIn("POST", [smp({"person": {}}) for _ in range(30)])  # no other project's HTTP verbs


class RoundB15Scenario(unittest.TestCase):
    """round 5: 16 of 40 tasks dropped as twin gaps (missing events/props/journeys) -> curator scenario overrides;
    single-URL page pools, localhost pages, example-N.com person emails, signups by 96% of persons."""

    def test_sample_spec(self):
        r = random.Random(0)
        self.assertIn(gen2.sample_spec({"values": ["a", "b"]}, r), ("a", "b"))
        self.assertEqual(gen2.sample_spec({"values": [["a", 1], ["b", 0]]}, r), "a")
        x = gen2.sample_spec({"range": [20, 2000], "int": True, "log": True}, r)
        self.assertTrue(isinstance(x, int) and 20 <= x <= 2000)
        self.assertEqual(gen2.sample_spec("fixed", r), "fixed")
        a = gen2.scenario_props({"book": {"values": ["x", "y", "z"], "per_person": True}}, r, "p1", "s")
        b = gen2.scenario_props({"book": {"values": ["x", "y", "z"], "per_person": True}}, random.Random(5), "p1", "s")
        self.assertEqual(a, b)

    def test_scenario_seed_rows(self):
        p = project(n_persons=100, ovr={"scenario": [
            {"kind": "new_event", "event": "option_trade_opened", "per_day": 5, "from": "2023-11-01", "to": "2023-11-10",
             "persons": 20, "props": {"notionalUsd": {"range": [100, 5000]}}, "lib": "posthog-ios"},
            {"kind": "sequence", "steps": ["app_opened", "onboarding_started", "onboarding_done"], "persons": 50,
             "from": "2023-11-01", "to": "2023-11-15", "rates": [1, 0.6, 0.5]}]})
        rows = p.scenario_seed_rows()
        opened = [r for r in rows if r["event"] == "option_trade_opened"]
        self.assertGreater(len(opened), 30)
        self.assertTrue(all(100 <= r["props"]["notionalUsd"] <= 5000 and r["props"]["$lib"] == "posthog-ios" for r in opened))
        self.assertLessEqual(len({r["pi"] for r in opened}), 20)
        seq = C.Counter(r["event"] for r in rows if r["event"] != "option_trade_opened")
        self.assertEqual(seq["app_opened"], 50)
        self.assertLess(seq["onboarding_done"], seq["onboarding_started"])
        by = C.defaultdict(list)
        for r in rows:
            by[r["pi"]].append(r)
        for rs in by.values():
            ts = [r["ts"] for r in rs if r["event"] != "option_trade_opened"]
            self.assertEqual(ts, sorted(ts))

    def test_conversation_pages_skip_dev_hosts_with_ports(self):
        urls, _ = gen2.conversation_pages({"tasks": [{"text": "see http://127.0.0.1:3000/a and https://shop.io/b"}]}, {})
        self.assertEqual(urls, ["https://shop.io/b"])

    def test_drop_dev_hosts(self):
        spec = {"events": {"$pageview": {"properties": {"$current_url": {"values": [
            "http://127.0.0.1:3000/x", "https://shop.io/", "localhost:8000/a"]}}}}, "unscoped": {}}
        self.assertEqual(gen2.drop_dev_hosts(spec), 2)
        self.assertEqual(spec["events"]["$pageview"]["properties"]["$current_url"]["values"], ["https://shop.io/"])

    def test_medium_fits(self):
        self.assertTrue(gen2.medium_fits("cpc", "youtube"))
        self.assertTrue(gen2.medium_fits("email", "newsletter"))
        self.assertFalse(gen2.medium_fits("email", "youtube"))
        self.assertFalse(gen2.medium_fits("video", "newsletter"))
        self.assertFalse(gen2.medium_fits("email", "bing"))

    def test_event_props_per_session_and_person(self):
        """round 7: event_props drawn per event paired utm_source/medium at random and switched persons' countries."""
        import pyarrow as pa
        rows = [("$pageview", f"p{i % 20}", f"s{i % 40}") for i in range(400)]
        tab = pa.table({"event": [r[0] for r in rows], "person_id": [r[1] for r in rows], "$session_id": [r[2] for r in rows],
                        "properties": ["{}"] * len(rows)})
        p = project(ovr={"scenario": [
            {"kind": "event_props", "event": "$pageview", "share": 0.5, "props": {"utm_source": {"values": ["youtube", "google"]}}},
            {"kind": "event_props", "event": "$pageview", "share": 1.0, "props": {"$geoip_country_code": {"values": ["CN", "US"]}}}]})
        out = p.scenario_event_props(tab)
        ds = [json.loads(x) for x in out.column("properties").to_pylist()]
        by_s, by_p = C.defaultdict(set), C.defaultdict(set)
        for r, d in zip(rows, ds):
            by_s[r[2]].add(d.get("utm_source"))
            by_p[r[1]].add(d.get("$geoip_country_code"))
        self.assertTrue(all(len(v) == 1 for v in by_s.values()))
        self.assertTrue(all(len(v) == 1 for v in by_p.values()))
        self.assertTrue(all(d.get("$geoip_country_name") for d in ds))

    def test_mobile_seed_row_drops_web_context(self):
        p = project()
        donors = ({}, {"p1": ['{"$browser": "Chrome", "$os": "Windows", "$current_url": "https://x.io/"}']}, [])
        out = p._with_donor({"$lib": "posthog-ios"}, "Application Installed", "p1", donors, random.Random(0))
        self.assertEqual(out, {"$os": "iOS", "$lib": "posthog-ios"})


class RoundB16(unittest.TestCase):
    """round 6 audit: RevenueCat rc_* events from the web SDK; /users/<name> pages viewed by thousands."""

    def test_server_events_get_server_lib(self):
        import pyarrow as pa
        rows = [("rc_initial_purchase", '{"$lib": "web", "$browser": "Chrome", "$os": "Windows", "product_id": "pro"}'),
                ("$pageview", '{"$lib": "web", "$browser": "Chrome", "$os": "Windows"}')]
        tab = pa.table({"event": [r[0] for r in rows], "properties": [r[1] for r in rows]})
        out = project().device_coherence(tab)
        a, b = [json.loads(x) for x in out.column("properties").to_pylist()]
        self.assertEqual(a, {"$lib": "posthog-python", "product_id": "pro"})
        self.assertEqual(b["$browser"], "Chrome")

    def test_llm_pages_drop_profile_paths(self):
        out = gen2.valuepools.sane_pages({"host": "app.x.io", "paths": [["/users/sarah-chen", 5], ["/users", 3], ["/pricing", 2]]})
        self.assertEqual([p for p, _ in out["paths"]], ["/users", "/pricing"])

    def test_entity_pages(self):
        self.assertTrue(gen2.ENTITY_PAGE.search("https://app.x.io/users/amelia-chen"))
        self.assertFalse(gen2.ENTITY_PAGE.search("https://app.x.io/pricing"))


class RoundB12(unittest.TestCase):
    """b12 acceptance audit: everyone fired every custom event, purchases by non-visitors, placeholders, a GitHub PR URL
    and one session URL as the project's pages, campaigns crossed with random sources."""

    def test_is_placeholder(self):
        P = gen2.valuepools.is_placeholder
        self.assertTrue(P("$config_defaults", "config_defaults_c"))
        self.assertTrue(P("tag_name", "Tag 3"))
        self.assertTrue(P("provider", "example company 7"))
        self.assertFalse(P("plan", "pro_annual"))
        self.assertFalse(P("version", "Version 2"))
        self.assertFalse(P("tag_name", "Q3 Launch"))

    def test_campaign_fit(self):
        self.assertTrue(gen2.campaign_fits("search_assinatura_cafe", "google"))
        self.assertFalse(gen2.campaign_fits("search_assinatura_cafe", "twitter"))
        self.assertEqual(gen2.coherent_utm("twitter", [], ["search_brand", "spring_launch"])[1], "spring_launch")

    def test_conversation_pages_hygiene(self):
        spec = {"tasks": [{"text": "see https://github.com/acme/repo/pull/5 and https://sub1.example-1.com/?p=abc&i=2 ok"}]}
        urls, _ = gen2.conversation_pages(spec, {})
        self.assertNotIn("https://github.com/acme/repo/pull/5", urls)
        self.assertIn("https://sub1.example-1.com/", urls)

    def test_postprocess_runs_coherence_without_profiles(self):
        """2.19 regress: postprocess returned early when a twin had no dynamics profiles and no seed rows, so 17 of 33
        twins skipped coherent_sessions (adopters, causal children, lifecycle_once, landing pageview, UTM tuples)."""
        import tempfile
        import pyarrow as pa
        import pyarrow.parquet as pq

        d = tempfile.mkdtemp(prefix="pp_test_")
        pq.write_table(pa.table({"event": ["a", "b"], "uuid": ["u1", "u2"], "properties": ["{}", "{}"],
                                 "timestamp": pa.array([1_700_000_000_000_000, 1_700_000_001_000_000],
                                                       pa.timestamp("us", tz="UTC"))}), f"{d}/events.parquet")
        calls = []

        class Fake:
            S = {"id": "x"}
            now = dt.datetime(2023, 11, 20, tzinfo=dt.timezone.utc)
            tz = dt.timezone.utc
            v2 = C.Counter()
            profiles = staticmethod(lambda: {})
            event_seed_rows = staticmethod(lambda: [])
            override_zeroed_events = staticmethod(lambda: set())
            adopters = staticmethod(lambda tab: tab)

            def coherent_sessions(self, tab):
                calls.append(tab.num_rows)
                return tab

        gen2.Project2.postprocess(Fake(), d)
        self.assertEqual(calls, [2])

    def test_drop_url_values(self):
        """regress f8f5: a replay SDK status property carried the page pool (URLs)."""
        import tempfile
        import pyarrow as pa
        import pyarrow.parquet as pq

        self.assertFalse(gen2.urlish("$sdk_debug_replay_linked_flag_trigger_status"))
        self.assertFalse(gen2.urlish("$sdk_debug_replay_url_trigger_status"))
        self.assertTrue(gen2.urlish("instance_url"))
        d = tempfile.mkdtemp(prefix="url_test_")
        rows = [json.dumps({"trigger_status": "https://a.example/x", "$current_url": "https://a.example/x"})] * 10
        pq.write_table(pa.table({"properties": rows}), f"{d}/events.parquet")

        class Fake:
            v2 = C.Counter()

        gen2.Project2.drop_url_values(Fake(), f"{d}/events.parquet")
        out = [json.loads(x) for x in pq.read_table(f"{d}/events.parquet").column("properties").to_pylist()]
        self.assertTrue(all("trigger_status" not in x and x["$current_url"] for x in out))

    def test_adopters(self):
        import pyarrow as pa
        t0 = 1_700_000_000_000_000
        rows = [("feature_used", f"p{i}", t0 + (i % 3) * 86_400_000_000) for i in range(100)]
        rows += [("$pageview", f"p{i}", t0 + (i % 3) * 86_400_000_000) for i in range(100)]
        tab = pa.table({"event": [r[0] for r in rows], "person_id": [r[1] for r in rows], "distinct_id": [r[1] for r in rows],
                        "person_properties": ["{}"] * len(rows), "$session_id": [f"s{r[1]}" for r in rows],
                        "$window_id": [f"w{r[1]}" for r in rows], "properties": ["{}"] * len(rows),
                        "timestamp": pa.array([r[2] for r in rows], pa.int64()).cast(pa.timestamp("us", tz="UTC"))})
        p = project(targets={"feature_used": [20.0, 10.0]}, D=100.0)
        out = p.adopters(tab)
        ev, pid = out.column("event").to_pylist(), out.column("person_id").to_pylist()
        users = {pid[i] for i, e in enumerate(ev) if e == "feature_used"}
        self.assertLessEqual(len(users), 25)
        self.assertEqual(ev.count("feature_used"), 100)


class FunnelDropoff(unittest.TestCase):
    """r1 card 13: funnel seeds walked every person through every step (twin 30->25 vs production 51->34->1->0->0)."""

    def _rows(self, counts):
        src = {"kind": "FunnelsQuery", "dateRange": {"date_from": "-30d"},
               "series": [{"event": e} for e in ("view", "signup", "login", "share", "buy")]}
        call = {"rows": [["Metric", "view", "signup", "login", "share", "buy"],
                         ["Total person count", *[str(c) for c in counts]]]} if counts else {"rows": []}
        return project().sequence_seed_rows(src, call, random.Random(3))

    def test_follows_production_proportions(self):
        n = C.Counter(r["event"] for r in self._rows([51, 34, 1, 0, 0]))
        self.assertEqual(n["view"], 51)
        self.assertEqual(n["signup"], 34)
        self.assertEqual(n["login"], 1)
        self.assertEqual(n["share"], 0)
        self.assertEqual(n["buy"], 0)

    def test_steps_in_time_order_per_person(self):
        by = C.defaultdict(list)
        for r in self._rows([10, 8, 5, 5, 2]):
            by[r["pi"]].append(r)
        for rs in by.values():
            ts = [r["ts"] for r in rs]
            self.assertEqual(ts, sorted(ts))

    def test_without_counts_keeps_old_behaviour(self):
        n = C.Counter(r["event"] for r in self._rows(None))
        self.assertEqual(set(n.values()), {25})


class DonorProperties(unittest.TestCase):
    """r1 card 01: injected events carried 3 properties and a relative URL, so channel/country/referrer were empty."""

    def setUp(self):
        self.p = project()
        organic = json.dumps({"$current_url": "https://shop.example-1.com/pricing", "utm_source": "google",
                              "$geoip_country_code": "VN", "$session_id": "s-organic", "$browser": "Chrome"})
        self.donors = ({"enrol": [organic]}, {}, [organic])

    def test_seed_props_win_and_profile_is_filled(self):
        out = self.p._with_donor({"utm_source": "newsletter"}, "enrol", "p1", self.donors, random.Random(0))
        self.assertEqual(out["utm_source"], "newsletter")
        self.assertEqual(out["$geoip_country_code"], "VN")
        self.assertEqual(out["$browser"], "Chrome")
        self.assertNotIn("$session_id", out)

    def test_seeded_geo_is_coherent(self):
        """b07: a seeded country name kept the donor's country code (Germany rows coded US)."""
        out = self.p._with_donor({"$geoip_country_name": "Germany"}, "enrol", "p1",
                                 ({"enrol": ['{"$geoip_country_code": "US", "$geoip_city_name": "Austin"}']}, {}, []), random.Random(0))
        self.assertEqual(out["$geoip_country_code"], "DE")
        self.assertNotEqual(out.get("$geoip_city_name"), "Austin")

    def test_relative_url_gets_donor_origin(self):
        out = self.p._with_donor({"$current_url": "/competition?x=1"}, "enrol", "p1", self.donors, random.Random(0))
        self.assertEqual(out["$current_url"], "https://shop.example-1.com/competition?x=1")
        self.assertEqual(out["$pathname"], "/competition")

    def test_no_donor_leaves_props(self):
        out = self.p._with_donor({"a": 1}, "x", "p1", ({}, {}, []), random.Random(0))
        self.assertEqual(out, {"a": 1})


class AgentCreatedObjects(unittest.TestCase):
    """r1 card 16: the 7 insights the production agent created were pre-loaded (answer leak)."""

    def test_objects_after_creation_are_excluded_unless_named(self):
        F = {"created_by_agent": {"upsert_dashboard": [{"turn": 1, "is_error": False}]},
             "calls": [{"k": 0, "turn": 0, "tool": "read_data", "object": "OLDINSIG"},
                       {"k": 1, "turn": 1, "tool": "read_data", "object": "NEWINSIG"},
                       {"k": 2, "turn": 2, "tool": "read_data", "object": "NAMEDINS"}],
             "objects": {"dashboards": {}}}
        made = project(F=F, user_text="please look at insight NAMEDINS").\
            _agent_created()
        self.assertEqual(made, {"NEWINSIG"})

    def test_create_insight_call_counts_as_creation(self):
        F = {"calls": [{"k": 0, "turn": 0, "tool": "create_insight"},
                       {"k": 1, "turn": 0, "tool": "read_data", "object": "MADEHERE"}]}
        self.assertEqual(project(F=F)._agent_created(), {"MADEHERE"})

    def test_context_object_after_creation_excluded(self):
        """b09 card a1b1: the dashboard the production agent created (shown in the next turn's attached context) was
        pre-loaded; one shown in turn 0's context is starting state."""
        F = {"created_by_agent": {"upsert_dashboard": [{"turn": 0, "is_error": False}]}, "calls": [],
             "objects": {"dashboards": {"111": {"from_context": True, "context_turn": 1, "tiles": [{"short_id": "NEWTILE1"}]},
                                        "222": {"from_context": True, "context_turn": 0, "tiles": []}},
                         "insights": {"NEWTILE1": {"from_context": True, "context_turn": 1}}}}
        made = project(F=F)._agent_created()
        self.assertIn("111", made)
        self.assertIn("NEWTILE1", made)
        self.assertNotIn("222", made)

    def test_null_display_labels(self):
        """b11: PostHog's display label "None (i.e. no value)" was stored as a literal value."""
        self.assertIn("None (i.e. no value)", gen2.NULLS)

    def test_no_creation_no_exclusion(self):
        F = {"calls": [{"k": 0, "turn": 0, "tool": "read_data", "object": "X1234567"}]}
        self.assertEqual(project(F=F)._agent_created(), set())


class CompareSections(unittest.TestCase):
    """r1 card 07: compare-mode Trends results were dropped (first section label parsed as the header)."""

    def test_two_sections(self):
        cols = ["Previous period:"]
        rows = [["Date", "$pageview"], ["2026-07-20", "100"], ["2026-07-27", "110"], ["Current period:"],
                ["Date", "$pageview"], ["2026-10-19", "200"], ["2026-10-26 (partial)", "20"], ["Note: partial rows"]]
        secs = qfacts.trend_sections(cols, rows)
        self.assertEqual([s[0] for s in secs], ["previous", "current"])
        self.assertEqual(secs[0][2], [["2026-07-20", "100"], ["2026-07-27", "110"]])
        self.assertEqual(secs[1][2], [["2026-10-19", "200"], ["2026-10-26 (partial)", "20"]])

    def test_plain_table_has_no_sections(self):
        self.assertEqual(qfacts.trend_sections(["Date", "x"], [["2026-10-01", "1"]]), [])


class PeriodUniques(unittest.TestCase):
    """r1 card 07: weekly unique visitors (~60k/week) were ignored, leaving a 260-person default twin."""

    def test_weekly_dau_gives_daily_hint(self):
        pts = [[f"2026-{m:02d}-{d:02d}", 60000.0, False] for m, d in ((9, 7), (9, 14), (9, 21), (9, 28), (10, 5))]
        s = {"event": "$pageview", "math": "dau", "interval": "week", "points": pts}
        lv = project(Q={"series": [s]}, active={"$pageview"}).series_levels()
        level = lv[("$pageview", "dau")][0]
        self.assertAlmostEqual(level, 60000 / 7 ** 0.6, delta=1)

    def test_new_users_weekly_floor(self):
        """r1 card 14: weekly new visitors (first_time_for_user, ~5k/week) were ignored."""
        pts = [[f"2026-09-{d:02d}", 5000.0, False] for d in (7, 14, 21, 28)]
        s = {"event": "$pageview", "math": "first_time_for_user", "interval": "week", "points": pts}
        lv = project(Q={"series": [s]}, active={"$pageview"}).series_levels()
        self.assertAlmostEqual(lv[("$pageview", "dau")][0], 5000 / 7, delta=1)

    def test_weekly_active(self):
        pts = [[f"2026-10-{d:02d}", 7000.0, False] for d in (1, 2, 3, 4)]
        s = {"event": "$pageview", "math": "weekly_active", "interval": "day", "points": pts}
        lv = project(Q={"series": [s]}, active={"$pageview"}).series_levels()
        self.assertAlmostEqual(lv[("$pageview", "dau")][0], 7000 / 7 ** 0.6, delta=1)

    def test_previous_period_never_sets_level(self):
        pts = [["2026-07-20", 9.0, False], ["2026-07-27", 9.0, False], ["2026-08-03", 9.0, False]]
        s = {"event": "$pageview", "math": "total", "interval": "day", "points": pts, "period": "previous"}
        self.assertEqual(project(Q={"series": [s]}, active={"$pageview"}).series_levels(), {})


if __name__ == "__main__":
    unittest.main()
