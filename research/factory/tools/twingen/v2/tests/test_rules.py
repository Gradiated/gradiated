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
        p = project(invented=["mcp organization switched", "Application opened", "$exception"],
                    targets={"mcp organization switched": [200.0, 50.0], "Application opened": [80.0, 20.0],
                             "$exception": [30.0, 5.0]}, ref_text="please look at application opened")
        p.cap_stub_events()
        self.assertEqual(p.targets["mcp organization switched"], [0.2, 0.2])
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
