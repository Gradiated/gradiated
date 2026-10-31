"""twingen v2: a v1 project (gen.Project) plus production facts from the conversation's own trace.

Adds, on top of gen.py (which is unchanged):
- history: extends the window to cover absolute dates used by production queries;
- volumes: per-event daily levels from production Trends series and SQL counts, optional calibration multipliers
  (calib.json, from a replay of production queries against the loaded twin);
- dynamics: per-event daily profiles from production time series (launches, spikes, drops), applied by thinning or
  duplicating the generated events per day;
- named entities: persons with the emails, names, distinct ids and person ids seen in production result rows and
  filters, each on exactly one person (identity values are no longer spread over many persons), plus their events
  from production result rows (shape A queries over events);
- objects: saved insights, notebooks and dashboards with their production short ids/ids and content (insight query
  JSON, notebook markdown);
- warehouse: per-table columns merged across the spec, same-customer specs (cluster members) and every column the
  production SQL attributes to the table (qualified and unqualified); values by type and name (0/1 flags, real dates,
  month starts, enums from production values and literals, shared join-key pools) and seed rows inverted from
  production results (shape A rows verbatim, shape B group counts).

Usage (twingen .venv):
    gen2.py SPEC OUT_DIR [--facts F] [--qfacts Q] [--calib C] [--seed N] [--max-events N]
Defaults read facts_v2/<id>.json and qfacts_v2/<id>.json next to the specs. Prints aggregate counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import collections as C
import datetime as dt
import json
import math
import os
import random
import re
import sys
import uuid

import numpy as np
import orjson
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gen  # noqa: E402
import valuepools  # noqa: E402
import geo_extra  # noqa: E402
import paths as PATHS  # noqa: E402
import specio  # noqa: E402
from gen import UTC, iso, stable_seed, uuid7, wh_column, WH_TYPES  # noqa: E402
from specio import shape_of  # noqa: E402

GEN2_VERSION = "twingen-2.15"
TWINS = PATHS.TWINS
FACTS = PATHS.FACTS
QFACTS = PATHS.QFACTS
CLUSTERS = PATHS.CLUSTERS
OVERRIDES = PATHS.OVERRIDES
XINDEX = PATHS.XINDEX  # cross-trace objects and warehouse schemas (xindex.py)
_XI = None
REF_DASH = re.compile(r"dashboards?[/ #:]*(\d{4,})", re.I)
REF_NB = re.compile(r"notebooks?/([A-Za-z0-9]{8})\b")
REF_INS = re.compile(r"insights?/([A-Za-z0-9]{8,12})\b")
REF_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*_[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*\b")


def xindex() -> dict:
    global _XI
    if _XI is None:
        _XI = load_json(XINDEX) or {"dashboards": {}, "insights": {}, "notebooks": {}, "tables": {}}
    return _XI  # per-twin declarative fixes from the repair pass (<twin_id>.json)
SPECS = PATHS.SPECS
NULLS = {"", "(null)", "null", "None", "nan", "NaN", "NULL", "\\N"}
ISO_D = re.compile(r"^(\d{4}-\d\d-\d\d)(?:[ T](\d\d:\d\d(?::\d\d(?:\.\d+)?)?))?(Z|[+-]\d\d:?\d\d)?$")
FLAG_NAME = re.compile(r"^(is|has|was|did|can|should)_|_(flag|bool)$|^(active|deleted|churned|won|lost|closed|paid|enabled|verified|converted)$", re.I)
MONTH_NAME = re.compile(r"(^|_)(month|period|mon)(_|$)|month_start|_month$|^month", re.I)
MAX_SEED_ROWS_PER_TABLE = 20000
MAX_EVENT_SEEDS = 200000
MAX_DUP = 20.0


def op_eq(op) -> bool:
    """HogQL CompareOperationOp values as serialized by qfacts: '==', 'in' (also tolerate enum names)."""
    o = str(op)
    return o in ("==", "=", "in", "In") or o.endswith(".Eq") or o.endswith(".In")


def op_like(op) -> bool:
    o = str(op).lower()
    return o in ("like", "ilike") or o.endswith(".like") or o.endswith(".ilike")


def parse_when(s) -> dt.datetime | None:
    s = str(s).strip().replace(" (partial)", "")
    m = ISO_D.match(s)
    if not m:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except Exception:  # noqa: BLE001
        try:
            d = dt.datetime.fromisoformat(m.group(1))
        except Exception:  # noqa: BLE001
            return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def numv(x):
    try:
        s = str(x).replace(",", "").strip()
        if s in NULLS:
            return None
        return float(s)
    except Exception:  # noqa: BLE001
        return None


def cell(v):
    s = str(v)
    return None if s.strip() in NULLS else s


def load_json(p):
    try:
        return json.load(open(p))
    except Exception:  # noqa: BLE001
        return None


def cluster_members(cid: str) -> list[str]:
    if not os.path.exists(CLUSTERS):
        return []
    for line in open(CLUSTERS):
        if cid in line:
            r = json.loads(line)
            if cid in (r.get("members") or []):
                return [m for m in r["members"] if m != cid]
    return []


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


class FilterMix:
    """rule (r1c): a property known only from query filters samples its usual values and returns a filter value with
    a minority share (0 when production found none)."""

    def __init__(self, base, values, share, rnd):
        self.base, self.values, self.share, self.rnd = base, list(values), share, rnd

    def __call__(self, ctx):
        if self.values and self.share > 0 and self.rnd.random() < self.share:
            return self.rnd.choice(self.values)
        return self.base(ctx)

    def __getattr__(self, k):
        return getattr(self.base, k)


def clean_null_props(spec: dict) -> C.Counter:
    """rule (r2): drop null display strings from spec property values; remove properties that only ever showed null
    in SQL results (no taxonomy evidence)."""
    n = C.Counter()
    secs = [info.get("properties") or {} for info in (spec.get("events") or {}).values()]
    secs.append(spec.get("unscoped") or {})
    for sec in secs:
        for prop in list(sec):
            d = sec[prop]
            vals = d.get("values") or []
            kept = [v for v in vals if str(v).strip() not in NULLS]
            if len(kept) == len(vals):
                continue
            d["values"] = kept
            n["null_values_dropped"] += len(vals) - len(kept)
            if not kept and "taxonomy_props" not in (d.get("sources") or {}):
                del sec[prop]
                n["null_only_props_removed"] += 1
    return n


def scrub_sampler(smp) -> int:
    """rule (r2): remove null display strings ("(null)", "None", ...) from a choice sampler; fall back to shape values
    when nothing is left. Returns the number of choices removed."""
    if getattr(smp, "mode", None) != "choice" or not getattr(smp, "choices", None):
        return 0
    keep = [(c, w) for c, w in zip(smp.choices, smp.weights) if str(c).strip() not in NULLS]
    removed = len(smp.choices) - len(keep)
    if not removed:
        return 0
    smp.pending = [v for v in (smp.pending or []) if str(v).strip() not in NULLS]
    if keep:
        smp.choices, smp.weights = [c for c, _ in keep], [w for _, w in keep]
        acc, smp._cum = 0.0, []
        for w in smp.weights:
            acc += w
            smp._cum.append(acc)
    else:
        smp.choices, smp.weights = [], []
        smp._setup_shape(None, None)
    return removed


class GroupDist:
    """rule (r5): a property's value distribution from a production grouped result (value -> count); null display
    values mean the property is unset (returns None, so the event omits it)."""

    source = "spec"
    mode = "groupdist"
    pending: list = []

    def plan(self, n_calls):  # sampler interface (values.Sampler.plan): nothing to pre-plan
        return None

    def __init__(self, dist: dict, rnd):
        self.items = [(None if str(v).strip() in NULLS or str(v).strip() == "(none)" else v, float(c)) for v, c in dist.items()]
        self.rnd = rnd
        self.cum, acc = [], 0.0
        for _, c in self.items:
            acc += c
            self.cum.append(acc)

    def __call__(self, ctx):
        import bisect

        x = self.rnd.random() * self.cum[-1]
        return self.items[min(len(self.items) - 1, bisect.bisect_left(self.cum, x))][0]


def group_distributions(qf: dict, min_total: float = 20) -> dict:
    """(event, property) -> {value: count} from production grouped results over events (qfacts event_seeds with
    groups). Dims that the same query filters on are skipped (biased); counts come from the first count aggregate."""
    out: dict = {}
    for sd in qf.get("event_seeds") or []:
        groups = sd.get("groups") or []
        evs = [e for e in sd.get("events") or [] if isinstance(e, str)]
        if not groups or not evs:
            continue
        filtered = {p for _t, p, _l in sd.get("where") or []}
        for dim in {k for g in groups for k in (g.get("dims") or {})}:
            if not dim.startswith("properties.") or dim in filtered:
                continue
            dist = C.Counter()
            for g in groups:
                cnt = next((v for k, v in (g.get("aggs") or {}).items() if k.startswith("count(") and v is not None), None)
                if cnt is None or cnt <= 0 or dim not in (g.get("dims") or {}):
                    continue
                dist[str((g["dims"] or {})[dim])] += float(cnt)
            if sum(dist.values()) < min_total:
                continue
            for e in evs:
                prev = out.get((e, dim[len("properties."):]))
                if prev is None or sum(dist.values()) > sum(prev.values()):
                    out[(e, dim[len("properties."):])] = dict(dist)
    return out


ATTRIBUTION_PRESENCE = [(re.compile(r"^(\$initial_)?utm_(source|medium|campaign|content|term)$"), 0.2),
                        (re.compile(r"^(\$initial_)?(gclid|gbraid|wbraid|fbclid|msclkid|ttclid|li_fat_id|gad_source|"
                                    r"gad_campaignid|dclid|twclid|irclid|mc_cid)$"), 0.05)]


def attribution_presence(prop: str) -> float | None:
    for rx, p in ATTRIBUTION_PRESENCE:
        if rx.match(prop):
            return p
    return None


class SessionAttr:
    """rule (r6): attribution properties (UTM, ad click ids) are set on a minority of sessions and are constant within
    a session (one landing, one campaign); taxonomy value lists say which values exist, not how often."""

    def __init__(self, base, presence: float, salt: str):
        self.base, self.presence, self.salt = base, presence, salt
        self.cache: dict = {}

    def __call__(self, ctx):
        key = str(ctx.get("session_id") or ctx.get("sid") or id(ctx.get("person")))
        if key not in self.cache:
            h = int(hashlib.sha256(f"{self.salt}:{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            self.cache[key] = self.base(ctx) if h < self.presence else None
            if len(self.cache) > 200000:
                self.cache.clear()
        return self.cache[key]

    def __getattr__(self, k):
        return getattr(self.base, k)


ACTIVE_POOLS: dict = {}  # prop -> [[value, weight], ...] for the twin being generated (rule r7, valuepools.py)
_ORIG_SETUP_SHAPE = None


def install_pool_hook() -> None:
    """Placeholder pools ("<prop>_a", "Prop 1") are replaced by the twin's LLM value pool for that property."""
    global _ORIG_SETUP_SHAPE
    import values as V

    if _ORIG_SETUP_SHAPE is not None:
        return
    _ORIG_SETUP_SHAPE = V.Sampler._setup_shape

    def _setup_shape(self, prior, shape_prior):
        pool = ACTIVE_POOLS.get(self.name) if self.type in (None, "String") else None
        if pool and self.shape not in valuepools.SKIP_SHAPES:
            self.mode = "choice"
            self.choices = [v for v, _ in pool]
            self.weights = [float(w) for _, w in pool]
            acc, self._cum = 0.0, []
            for w in self.weights:
                acc += w
                self._cum.append(acc)
            self.jitter = False
            self.source = "llm_pool"
            return
        _ORIG_SETUP_SHAPE(self, prior, shape_prior)

    V.Sampler._setup_shape = _setup_shape


def activate_pools(pools: dict) -> None:
    ACTIVE_POOLS.clear()
    for k, v in pools.items():
        scope, prop = k.split("::", 1)
        if scope == "person" and prop in ACTIVE_POOLS:
            continue
        ACTIVE_POOLS[prop] = v


GEO_PROPS = ("$geoip_country_code", "$geoip_country_name", "$geoip_continent_code", "$geoip_continent_name",
             "$geoip_city_name", "$geoip_subdivision_1_name", "$geoip_subdivision_1_code", "$geoip_postal_code",
             "$geoip_latitude", "$geoip_longitude", "$geoip_time_zone")
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


def geo_catalog() -> dict:
    """code -> catalog tuple (base catalog plus geo_extra)."""
    out = {c[0]: c for c in gen.catalog.COUNTRIES}
    for c in geo_extra.EXTRA:
        out.setdefault(c[0], c)
    return out


BD_COL = re.compile(r"breakdown for the value `([^`]*)`")


def breakdown_prop(bd: dict) -> tuple[str | None, str]:
    """(property, type) of a single-property breakdown, in either schema: breakdown/breakdown_type or the newer
    breakdowns: [{property, type}]."""
    bd = bd or {}
    if isinstance(bd.get("breakdown"), str):
        return bd["breakdown"], bd.get("breakdown_type") or "event"
    bs = bd.get("breakdowns") or []
    if len(bs) == 1 and isinstance(bs[0], dict) and isinstance(bs[0].get("property"), str):
        return bs[0]["property"], bs[0].get("type") or "event"
    return None, ""


def trend_breakdown_distributions(facts: dict) -> dict:
    """(event, property) -> {value: count} from production Trends results broken down by an event property (one
    series): columns "... breakdown for the value `X`", values summed over the rows."""
    out: dict = {}
    for c in (facts or {}).get("calls") or []:
        sch = c.get("schema")
        if c.get("is_error") or not isinstance(sch, dict) or not c.get("rows"):
            continue
        src = sch.get("source") if sch.get("kind") in ("InsightVizNode", "DataVisualizationNode") else sch
        if not isinstance(src, dict) or src.get("kind") != "TrendsQuery":
            continue
        prop, btype = breakdown_prop(src.get("breakdownFilter"))
        ser = src.get("series") or []
        if not prop or len(ser) != 1 or not ser[0].get("event") or btype != "event":
            continue
        cols = c.get("cols") or []
        dist: C.Counter = C.Counter()
        for j, col in enumerate(cols):
            m = BD_COL.search(str(col))
            if not m or m.group(1).startswith("$$_posthog_breakdown_other"):
                continue
            for r in c["rows"]:
                if len(r) == len(cols):
                    v = numv(r[j])
                    if v and v > 0:
                        dist[m.group(1)] += v
        if dist:
            key = (ser[0]["event"], prop)
            if key not in out or sum(dist.values()) > sum(out[key].values()):
                out[key] = dict(dist)
    return out


def geo_tuple(country, rnd) -> dict:
    """Coherent geo properties for a country code or name (catalog city); {} when the country is unknown."""
    cat = geo_catalog()
    v = str(country or "").strip()
    by_name = {c[1].lower(): k for k, c in cat.items()}
    code = v.upper() if v.upper() in cat else by_name.get(re.sub(r"^the ", "", v.lower()))
    if not code:
        return {}
    cc = cat[code]
    city = rnd.choice(cc[5])
    return {"$geoip_country_code": cc[0], "$geoip_country_name": cc[1], "$geoip_continent_code": cc[2],
            "$geoip_continent_name": cc[3], "$geoip_city_name": city[0], "$geoip_subdivision_1_name": city[1],
            "$geoip_subdivision_1_code": city[2], "$geoip_time_zone": city[6]}


def production_countries(spec: dict, qf: dict, facts: dict | None = None) -> dict:
    """code -> weight from production evidence: $geoip_country_code / _name values (spec events, unscoped, person
    properties; earlier values weigh more, as listed) and grouped production results."""
    cat = geo_catalog()
    by_name = {c[1].lower(): k for k, c in cat.items()}
    by_name.update({"the netherlands": "NL", "united states of america": "US", "usa": "US", "uk": "GB",
                    "united kingdom": "GB", "czech republic": "CZ", "türkiye": "TR", "viet nam": "VN"})
    w: C.Counter = C.Counter()

    def add(v, weight):
        v = str(v).strip()
        code = v.upper() if v.upper() in cat else by_name.get(v.lower()) or by_name.get(re.sub(r"^the ", "", v.lower()))
        if code:
            w[code] += weight

    secs = [info.get("properties") or {} for info in (spec.get("events") or {}).values()]
    secs += [spec.get("unscoped") or {}, ((spec.get("entities") or {}).get("person") or {}).get("properties") or {}]
    for sec in secs:
        for p in ("$geoip_country_code", "$geoip_country_name", "$initial_geoip_country_code", "$initial_geoip_country_name"):
            for i, v in enumerate((sec.get(p) or {}).get("values") or []):
                add(v, 1.0 / (1 + i))
    dists = list(group_distributions(qf or {}).items()) + list(trend_breakdown_distributions(facts or {}).items())
    for (e, prop), dist in dists:
        if prop in ("$geoip_country_code", "$geoip_country_name"):
            tot = sum(dist.values()) or 1
            for v, c in dist.items():
                add(v, 5.0 * c / tot)
    return dict(w)


def coherent_utm(src: str, mediums: list, campaigns: list) -> tuple[str, str]:
    """rule (r8): one source -> one consistent medium and a campaign from that source's own small set."""
    h = int(hashlib.sha256(src.encode()).hexdigest()[:8], 16)
    default = gen.catalog.UTM_MEDIUMS.get(src)
    if mediums:
        med = default if default in mediums else mediums[h % len(mediums)]
    else:
        med = default or "referral"
    pool = campaigns or gen.catalog.UTM_CAMPAIGNS
    camp = pool[h % len(pool)]
    return med, camp


URL_RX = re.compile(r"https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s'\"<>)\]`|,]*)?")
PATH_CELL = re.compile(r"^/[A-Za-z0-9_\-./%~]{1,150}$")
SQL_PATH_LIT = re.compile(r"'%?(/[A-Za-z0-9_\-./]{2,120})%?'")


def conversation_pages(spec: dict, facts: dict) -> tuple[list[str], list[str]]:
    """rule (r10): pages the conversation shows (URLs in the user's text, URL/path cells in production results,
    path fragments in production SQL filters, page breakdowns), so the twin's site has the business's own pages and
    host instead of a generic SaaS page set. Returns (urls, paths), most evidenced first."""
    urls: C.Counter = C.Counter()
    paths: C.Counter = C.Counter()
    text = "\n".join(t.get("text") or "" for t in spec.get("tasks") or [])
    for u in URL_RX.findall(text):
        urls[u.rstrip(".")] += 5
    for c in (facts or {}).get("calls") or []:
        for r in (c.get("rows") or [])[:300]:
            for x in r:
                x = str(x).strip()
                if x.startswith(("http://", "https://")) and len(x) < 300 and " " not in x:
                    urls[x] += 1
                elif PATH_CELL.match(x) and not re.match(r"^/\d+(/\d+)*$", x):
                    paths[x] += 1
        for lit in SQL_PATH_LIT.findall(c.get("sql") or ""):
            if not re.search(r"[%*]", lit):
                paths[lit] += 2
    for (e, prop), dist in trend_breakdown_distributions(facts or {}).items():
        for v, n in dist.items():
            v = str(v)
            if prop in ("$current_url", "$initial_current_url") and v.startswith("http"):
                urls[v] += n
            elif prop in ("$pathname", "$initial_pathname") and v.startswith("/"):
                paths[v] += n
    return [u for u, _ in urls.most_common(120)], [p_ for p_, _ in paths.most_common(150)]


MOBILE_PROPS = ("$app_version", "$app_build", "$app_namespace", "$is_testflight", "$app_name", "$device_manufacturer")


def mobile_platform(spec: dict) -> str | None:
    """rule (r13): "ios"/"android" when the conversation's events carry mobile-app properties and no web pageviews,
    else None (a mobile app was generated as a web site: $lib=web, desktop OSes, web URLs)."""
    ev = spec.get("events") or {}
    if "$pageview" in ev:
        return None
    hits, os_names = 0, C.Counter()
    for info in ev.values():
        props = info.get("properties") or {}
        hits += sum(1 for p in MOBILE_PROPS if p in props)
        for p in ("$os_name", "$os"):
            for v in (props.get(p) or {}).get("values") or []:
                os_names[str(v).lower()] += 1
    if "$screen" in ev:
        hits += 2
    if os_names["ios"] + os_names["ipados"] + os_names["android"]:
        hits += 1
    if hits < 2:
        return None
    return "android" if os_names["android"] > os_names["ios"] + os_names["ipados"] else "ios"


CHILD_OF = [  # (child word, parent words): child volume <= parent volume
    (("dismissed", "closed", "clicked", "accepted", "declined"), ("shown", "viewed", "displayed", "opened", "impression")),
    (("completed", "finished", "succeeded", "failed", "abandoned", "submitted"), ("started", "begun", "opened", "initiated")),
    (("created", "saved"), ("opened", "started")),
]
FUNNEL_PAIRS = [("checkout_started", "add_to_cart"), ("checkout_completed", "checkout_started"),
                ("order_completed", "checkout_started"), ("purchase_completed", "checkout_started")]


def parent_event(e: str, names) -> str | None:
    """'paywall_dismissed' -> 'paywall_shown' when present; 'checkout_started' -> 'add_to_cart'."""
    low = e.lower()
    for child, parent in FUNNEL_PAIRS:
        if low == child and parent in names:
            return parent
    for childs, parents in CHILD_OF:
        for c in childs:
            m = re.search(rf"(^|[_ .:-]){c}([_ .:-]|$)", low)
            if not m:
                continue
            for p_ in parents:
                cand = low[:m.start()] + low[m.start():m.end()].replace(c, p_) + low[m.end():]
                for n in names:
                    if n.lower() == cand and n != e:
                        return n
    return None


FAIL_EV = re.compile(r"(^|[_ .:-])(fail(ed|ure)?|error(ed)?|declined|rejected)([_ .:-]|$)", re.I)
OK_WORDS = ("succeeded", "success", "successful", "completed", "complete", "created", "sent", "submitted", "started",
            "paid", "placed")


def success_sibling(e: str, names) -> str | None:
    """'payment_failed' -> 'payment_succeeded' (or completed/created/...) if present in names."""
    m = FAIL_EV.search(e)
    if not m:
        return None
    stem = (e[:m.start()] + e[m.end():]).strip("_ .:-")
    for w in OK_WORDS:
        for cand in (f"{stem}_{w}", f"{stem} {w}", f"{stem}.{w}", f"{w}_{stem}"):
            if cand in names and cand != e:
                return cand
    return None


STUB_EVENT = re.compile(r"^(mcp |application )", re.I)


class Project2(gen.Project):
    def __init__(self, spec, facts=None, qfacts=None, calib=None, member_specs=None, overrides=None, **kw):
        _null_stats = clean_null_props(spec)
        # the loaded spec has no user turns; the raw spec file does (pages and value pools need the user's words)
        _raw = load_json(os.path.join(SPECS, f"{spec['id']}.json")) if spec.get("kind") == "conversation" else None
        _tasks = (_raw or {}).get("tasks") or spec.get("tasks") or []
        _urls, _paths = conversation_pages({"tasks": _tasks}, facts or {})
        if _urls or _paths:  # rule (r10): feed the conversation's pages to the base page pool (via spec values)
            un = spec.setdefault("unscoped", {})
            for key, vals in (("$current_url", _urls), ("$pathname", _paths)):
                d = un.setdefault(key, {"type": "String", "values": [], "more_values": None, "description": None,
                                        "standard": True, "values_status": None, "sources": {}})
                d["values"] = list(dict.fromkeys(list(vals) + list(d.get("values") or [])))
        _null_stats["conversation_urls"] = len(_urls)
        _null_stats["conversation_paths"] = len(_paths)
        install_pool_hook()
        _text = "\n".join(t.get("text") or "" for t in _tasks)
        _keys = valuepools.candidates(spec, shape_of, gen.VOCAB, gen.stem_of)
        _pools, _pool_status = valuepools.get_pools(spec, PATHS.ROOT, _keys, _text) if _keys else ({}, "none")
        activate_pools({k: v for k, v in _pools.items() if k in set(_keys)})
        super().__init__(spec, **kw)
        # overrides: {"history_days", "events": {e: multiplier}, "spikes": [{event, from, to, factor}],
        #             "warehouse": {table: {col: {type, values}}}, "persons": [{email, name, props}], "notes"}
        self.ovr = overrides or {}
        if self.ovr.get("history_days"):
            self.history_override = int(self.ovr["history_days"])
        self.F = facts or {"calls": [], "objects": {}, "emails": {}, "query_dates": [], "url_refs": []}
        self.Q = qfacts or {"dw": {}, "joins": [], "dw_seeds": {}, "event_seeds": [], "entity_literals": [],
                            "volume": [], "series": []}
        self.calib = calib or {}
        self.member_specs = member_specs or []
        self.v2 = C.Counter()
        self.v2.update(_null_stats)
        self.v2["value_pool_candidates"] = len(_keys)
        self.v2["value_pools_applied"] = sum(1 for k in _keys if k in _pools)
        self.v2[f"value_pools_{_pool_status}"] += 1
        self.v2_info: dict = {}
        raw = load_json(os.path.join(SPECS, f"{spec['id']}.json")) if spec.get("kind") == "conversation" else None
        self.user_text = "\n".join(t.get("text") or "" for t in (raw or {}).get("tasks") or [])
        self.ref_text = self.user_text + "\n" + "\n".join(c.get("sql") or "" for c in self.F.get("calls") or [] if isinstance(c.get("sql"), str))

    # ------------------------------------------------------------------ time
    FILTER_VALUE_SHARE = 0.1

    def zero_filter_values(self) -> set[tuple[str, str]]:
        """(property, value) pairs that a production SQL equality filter on events returned a count of 0 for."""
        rows_by_k = {c.get("k"): c.get("rows") for c in self.F.get("calls") or []}
        out = set()
        for qc in self.Q.get("calls") or []:
            rows = rows_by_k.get(qc.get("k"))
            if not qc.get("ok") or not rows or len(rows) != 1:
                continue
            n = next((numv(x) for x in rows[0] if numv(x) is not None), None)
            if n is None or n >= 1:
                continue
            for t, prop, lits in qc.get("literals") or []:
                if t == "events" and prop.startswith("properties."):
                    for lit in lits:
                        if op_eq(lit.get("op")):
                            out.update((prop[len("properties."):], str(v)) for v in lit.get("values") or [])
        return out

    def _wrap_attribution(self):
        """Apply SessionAttr to attribution properties of every event and context sampler (not GroupDist ones, which
        carry production's own presence)."""
        for e, samplers in self.ev_samplers.items():
            for prop in list(samplers):
                pr = attribution_presence(prop)
                if pr is not None and not isinstance(samplers[prop], (GroupDist, SessionAttr)):
                    samplers[prop] = SessionAttr(samplers[prop], pr, f"{self.S['id']}:{prop}")
                    self.v2["attribution_props_wrapped"] += 1
        ctx = getattr(self, "ctx_samplers", None) or {}
        for prop in list(ctx):
            pr = attribution_presence(prop)
            if pr is not None and not isinstance(ctx[prop], SessionAttr):
                ctx[prop] = SessionAttr(ctx[prop], pr, f"{self.S['id']}:ctx:{prop}")
                self.v2["attribution_ctx_wrapped"] += 1

    def make_profile(self, rnd):
        """rule (r8): 85% of visitors get a country from production's own mix (whole geo tuple, coherent)."""
        p = super().make_profile(rnd)
        if not hasattr(self, "_geo_mix"):
            mix = production_countries(self.S, self.Q, self.F)
            cat = geo_catalog()
            self._geo_mix = [(cat[k], w) for k, w in sorted(mix.items(), key=lambda kv: -kv[1])]
            self.v2["geo_production_countries"] = len(self._geo_mix)
        if self._geo_mix and rnd.random() < 0.85:
            tot = sum(w for _, w in self._geo_mix)
            x, acc = rnd.random() * tot, 0.0
            for cc, w in self._geo_mix:
                acc += w
                if x <= acc:
                    break
            city = rnd.choice(cc[5])
            p.update({"$geoip_country_code": cc[0], "$geoip_country_name": cc[1], "$geoip_continent_code": cc[2],
                      "$geoip_continent_name": cc[3], "$geoip_city_name": city[0], "$geoip_subdivision_1_name": city[1],
                      "$geoip_subdivision_1_code": city[2], "$geoip_postal_code": city[3],
                      "$geoip_latitude": round(city[4] + rnd.uniform(-0.05, 0.05), 4),
                      "$geoip_longitude": round(city[5] + rnd.uniform(-0.05, 0.05), 4), "$geoip_time_zone": city[6],
                      "$timezone": city[6]})
        return p

    def build_event_samplers(self):
        super().build_event_samplers()
        for samplers in self.ev_samplers.values():
            for smp in samplers.values():
                self.v2["prior_null_choices_scrubbed"] += scrub_sampler(getattr(smp, "base", smp))
        for smp in (getattr(self, "ctx_samplers", None) or {}).values():
            self.v2["prior_null_choices_scrubbed"] += scrub_sampler(smp)
        zero = self.zero_filter_values()
        for samplers in self.ev_samplers.values():  # rule (r8): geo and UTM come from the visitor profile / session
            for prop in list(samplers):
                if prop in GEO_PROPS or prop in UTM_KEYS or prop.startswith("$initial_utm_"):
                    samplers.pop(prop)
                    self.v2["geo_utm_event_samplers_removed"] += 1
        ctxs = getattr(self, "ctx_samplers", None) or {}
        for prop in list(ctxs):
            if prop in GEO_PROPS or prop in UTM_KEYS:
                ctxs.pop(prop)
        self._wrap_attribution()
        # rule (r9): a property the spec records on specific events is not attached to other events by the base
        # generator's "common props" filler (amount_usd belongs to the revenue event, not to signups)
        owned = C.defaultdict(set)
        for e2, info in (self.S.get("events") or {}).items():
            for p_ in (info.get("properties") or {}):
                owned[p_].add(e2)
        for e2, samplers in self.ev_samplers.items():
            for p_ in list(samplers):
                if not p_.startswith("$") and owned.get(p_) and e2 not in owned[p_] and not isinstance(samplers[p_], GroupDist):
                    samplers.pop(p_)
                    self.v2["foreign_props_removed"] += 1
        for (e, prop), dist in group_distributions(self.Q).items():  # rule (r5): production value distributions
            if e in self.ev_samplers:
                self.ev_samplers[e][prop] = GroupDist(dist, random.Random(stable_seed(self.S["id"], "gdist", e, prop)))
                self.v2["group_dist_props"] += 1
        for e, samplers in self.ev_samplers.items():
            props = ((self.S.get("events") or {}).get(e) or {}).get("properties") or {}
            for prop, d in props.items():
                if prop not in samplers or d.get("values_status") != "filter_values" or not d.get("values") \
                        or isinstance(samplers[prop], GroupDist):
                    continue
                pri = getattr(gen, "PRI", {}) or {}
                prior = ((pri.get("custom_props_common") or {}).get("properties") or {}).get(prop) or \
                    (pri.get("dollar_props_any") or {}).get(prop)
                base = gen.Sampler(prop, d.get("type"), [], None, prior, (pri.get("name_shape_priors") or {}).get(shape_of(prop)),
                                   random.Random(stable_seed(self.S["id"], "fmix", e, prop)), self)
                vals = [v for v in d["values"] if (prop, str(v)) not in zero]
                share = self.FILTER_VALUE_SHARE if vals else 0.0
                samplers[prop] = FilterMix(base, vals, share, random.Random(stable_seed(self.S["id"], "fmixr", e, prop)))
                self.v2["filter_only_props_mixed"] += 1
                if len(vals) < len(d["values"]):
                    self.v2["filter_only_values_zeroed"] += 1

    def required_days_v2(self) -> int:
        now = self.now
        best = 0
        dates = list(self.F.get("query_dates") or [])
        for s in self.Q.get("series") or []:
            dates.extend(p[0] for p in s["points"][:1])
        for d in dates:
            w = parse_when(d)
            if w is None:
                continue
            days = (now - w).days
            if 0 < days < 800:
                best = max(best, days)
        for v in self.Q.get("volume") or []:
            best = max(best, int((v.get("window") or {}).get("interval_days") or 0))
        return best

    def cap_stub_events(self):
        """rule (r2): invented PostHog-internal stub events stay a trickle unless the evidence names them."""
        named = self.ref_text.lower() if hasattr(self, "ref_text") else ""
        for e in list(getattr(self, "invented", [])):
            if STUB_EVENT.match(e) and e.lower() not in named and e in self.targets:
                # rule (r14): PostHog-internal stub events never appear unless the conversation names them
                self.targets.pop(e, None)
                self.active.pop(e, None)
                self.invented.remove(e)
                self.v2["stub_events_removed"] += 1

    def failure_ratios(self):
        """rule (r13): without production volume evidence a failure event is a minority of its success sibling
        (payment_failed 737 vs payment_succeeded 7 was implausible)."""
        hinted = getattr(self, "_volume_hinted", set())
        for e in list(self.targets):
            if e in hinted:
                continue
            sib = success_sibling(e, self.targets)
            if sib and self.targets[e][0] > 0.25 * self.targets[sib][0]:
                T, U = self.targets[sib]
                self.targets[e] = [0.1 * T, min(self.targets[e][1], max(0.1 * U, 0.05))]
                self.v2["failure_events_capped"] += 1

    def sibling_order(self):
        """rule (r14): without volume evidence a child event (dismissed, completed, checkout_started) does not exceed
        its parent (shown, started, add_to_cart): paywall_dismissed 919 vs paywall_shown 61 was implausible.
        $groupidentify fires at most once per person per day, for a minority of people (was 46% of all events)."""
        hinted = getattr(self, "_volume_hinted", set())
        for e in list(self.targets):
            if e in hinted:
                continue
            par = parent_event(e, self.targets)
            if par and self.targets[e][0] > 0.8 * self.targets[par][0]:
                T, U = self.targets[par]
                f = 0.6 if not FAIL_EV.search(e) else 0.1
                self.targets[e] = [f * T, min(self.targets[e][1], max(f * U, 0.05))]
                self.v2["child_events_capped"] += 1
        if "$groupidentify" in self.targets and "$groupidentify" not in hinted:
            T, U = self.targets["$groupidentify"]
            U2 = min(U, 0.3 * max(self.D, 1.0))
            self.targets["$groupidentify"] = [min(T, U2), U2]
            self.v2["groupidentify_capped"] += 1

    def needs_background_population(self) -> bool:
        """rule (r12): a web project whose conversation names only custom events still has visitors who never do them;
        without background activity every person does every named event ("users who did X vs didn't" inverts)."""
        ev = self.S.get("events") or {}
        if any(e in ev for e in ("$pageview", "$screen", "$autocapture", "Application Opened", "Application opened")):
            return False
        if mobile_platform(self.S):
            return False
        if not any(not (info or {}).get("standard") for info in ev.values()):
            return False
        libs = " ".join(str(v) for info in ev.values() for v in
                        ((info.get("properties") or {}).get("$lib") or {}).get("values") or []).lower()
        return not any(k in libs for k in ("ios", "android", "react-native", "flutter"))

    def plan(self):
        mob = mobile_platform(self.S)
        if mob:  # the base planner detects mobile from $lib values
            un = self.S.setdefault("unscoped", {})
            d = un.setdefault("$lib", {"type": "String", "values": [], "more_values": None, "description": None,
                                        "standard": True, "values_status": None, "sources": {}})
            d["values"] = [f"posthog-{mob}"] + [v for v in d.get("values") or [] if "web" not in str(v).lower()]
            self.v2["mobile_platform_" + mob] += 1
        if self.needs_background_population():
            self.S["events"]["$pageview"] = self._blank_event("$pageview", True)
            self.v2["background_pageviews_added"] += 1
        req = self.required_days_v2()
        self.v2_info["required_days_v2"] = req
        if self.history_override is None and req > 85:
            self.history_override = int(min(400, req + 7))
            self.v2["history_extended"] += 1
        super().plan()
        self.apply_volumes()
        self.cap_stub_events()
        self.failure_ratios()
        self.sibling_order()

    def series_levels(self):
        """event -> (daily level over the last 30 covered days, math, filtered) from production Trends series."""
        out = {}
        for s in self.Q.get("series") or []:
            e = s["event"]
            if e not in self.active:
                continue
            L = {"day": 1, "week": 7, "month": 30, "hour": 1 / 24}.get(s.get("interval"), None)
            math_ = s.get("math")
            if not L or math_ not in ("total", "dau", "weekly_active", "monthly_active", "first_time_for_user") \
                    or s.get("period") == "previous":
                continue
            pts = [(parse_when(p[0]), p[1]) for p in s["points"] if not p[2]]
            pts = [(d, v) for d, v in pts if d is not None]
            if not pts:
                continue
            last = max(d for d, _ in pts)
            recent = [v for d, v in pts if (last - d).days < max(30, 2 * L)]
            level = sum(recent) / max(1, len(recent)) / max(L, 1)
            if math_ == "dau" and L > 1:
                # rule (r1b): weekly/monthly uniques -> daily uniques, sublinear (users return within the period)
                level = sum(recent) / max(1, len(recent)) / (L ** 0.6)
                self.v2["dau_from_period_uniques"] += 1
            elif math_ in ("weekly_active", "monthly_active"):
                # rule (r4): rolling WAU/MAU values -> daily uniques with the same sublinear rule
                W = 7 if math_ == "weekly_active" else 30
                level = sum(recent) / max(1, len(recent)) / (W ** 0.6)
                self.v2["dau_from_rolling_active"] += 1
            elif math_ == "first_time_for_user":
                # rule (r4): new users per interval -> a floor on daily uniques (each new user is active that day)
                level = sum(recent) / max(1, len(recent)) / max(L, 1)
                self.v2["dau_floor_from_new_users"] += 1
            if math_ != "total":
                math_ = "dau"
            key = (e, math_)
            prev = out.get(key)
            cand = (level, bool(s.get("filtered")), len(pts))
            if prev is None or (prev[1] and not cand[1]) or (prev[1] == cand[1] and cand[2] > prev[2]):
                out[key] = cand
        return out

    def apply_volumes(self):
        hints_T, hints_U, lower = {}, {}, {}
        for (e, math_), (level, filtered, _) in self.series_levels().items():
            if level <= 0:
                continue
            if filtered:
                lower[e] = max(lower.get(e, 0), level)
            elif math_ == "total":
                hints_T[e] = level
            else:
                hints_U[e] = level
        for v in self.Q.get("volume") or []:
            days = (v.get("window") or {}).get("interval_days")
            if not days:
                w = v.get("window") or {}
                a, b = parse_when(w.get("min_date") or ""), parse_when(w.get("max_date") or "")
                if a and b and (b - a).days >= 1:
                    days = (b - a).days
            if not days or days < 1:
                continue
            if v["kind"] == "by_event":
                for g in v.get("groups") or []:
                    e = (g.get("dims") or {}).get("event")
                    cnt = next((x for k, x in (g.get("aggs") or {}).items() if k.startswith("count(") and x), None)
                    if e in self.active and cnt:
                        (lower if v.get("filtered") else hints_T)[e] = max((lower if v.get("filtered") else hints_T).get(e, 0), cnt / days)
            elif v["kind"] == "total" and len(v.get("events") or []) == 1:
                e = v["events"][0]
                cnt = next((x for k, x in (v.get("aggs") or {}).items() if k.startswith("count(") and x), None)
                if e in self.active and cnt:
                    (lower if v.get("filtered") else hints_T)[e] = max((lower if v.get("filtered") else hints_T).get(e, 0), cnt / days)
        changed = 0
        for e, (T, U) in list(self.targets.items()):
            ratio = max(1.0, T / max(U, 1e-9))
            nT, nU = T, U
            if e in hints_T:
                nT = hints_T[e]
                nU = hints_U.get(e, nT / ratio)
            elif e in hints_U:
                nU = hints_U[e]
                nT = nU * ratio
            if e in lower and nT < lower[e]:
                nT = lower[e]
                nU = max(nU, nT / ratio)
            if (nT, nU) != (T, U):
                changed += 1
                self.targets[e] = [nT, min(nU, nT)]
        cal = dict(self.calib.get("events") or {})
        for e, m in (self.ovr.get("events") or {}).items():
            cal[e] = cal.get(e, 1.0) * float(m)
        for e, m in cal.items():
            if e in self.targets and m and m > 0:
                T, U = self.targets[e]
                self.targets[e] = [T * m, U * m]
                self.v2["calibrated_events"] += 1
        D = self.D
        maxU = max((u for _, u in self.targets.values()), default=0)
        if changed or cal:
            D = max(D, maxU)
        if self.calib.get("dau"):
            D *= float(self.calib["dau"])
        # re-apply the event cap (history first, then volume scale)
        daily = sum(t for t, _ in self.targets.values())
        H = self.H
        if daily * H > self.max_events:
            f = self.max_events / (daily * H) * 0.95
            for e in self.targets:
                self.targets[e] = [self.targets[e][0] * f, self.targets[e][1] * f]
            D *= f
            self.volume_scale *= f
        for e in self.targets:
            self.targets[e][1] = min(self.targets[e][1], D)
        self.D = max(D, 1.0)
        self.v2["volume_hints_applied"] = changed
        self._volume_hinted = set(hints_T) | set(hints_U) | set(lower)
        self.v2_info["volume_hint_events"] = sorted(set(hints_T) | set(hints_U) | set(lower))[:50]

    # ------------------------------------------------------------------ named entities
    def collect_entities(self) -> list[dict]:
        ents: dict[str, dict] = {}

        def ent_for(email=None, name=None, did=None, pid=None):
            key = (email or "").lower() or (did and f"did:{did}") or (pid and f"pid:{pid}") or (name and f"name:{name.lower()}")
            if not key:
                return None
            e = ents.setdefault(key, {"email": None, "name": None, "distinct_id": None, "person_id": None,
                                      "props": {}, "events": []})
            if email and not e["email"]:
                e["email"] = email
            if name and not e["name"]:
                e["name"] = name
            if did and not e["distinct_id"]:
                e["distinct_id"] = did
            if pid and not e["person_id"]:
                e["person_id"] = pid
            return e

        for seed in self.Q.get("event_seeds") or []:
            for row in seed.get("rows") or []:
                email = cell(row.get("person.properties.email") or row.get("person.properties.$email") or "")
                name = cell(row.get("person.properties.name") or row.get("person.properties.$name") or "")
                did = cell(row.get("distinct_id") or "")
                pid = cell(row.get("person_id") or row.get("person.id") or "")
                e = ent_for(email, name, did, pid if pid and _is_uuid(pid) else None)
                if e is None:
                    continue
                for k, v in row.items():
                    if k.startswith("person.properties.") and cell(v) is not None:
                        e["props"].setdefault(k[len("person.properties."):], cell(v))
        for lit in self.Q.get("entity_literals") or []:
            path = lit["path"]
            for l in lit["lit"]:
                if not op_eq(l.get("op")):
                    continue
                for v in l.get("values") or []:
                    if not isinstance(v, str) or not v:
                        continue
                    if path in ("person.properties.email", "person.properties.$email") or (path.endswith("email") and "@" in v):
                        ent_for(email=v)
                    elif path in ("distinct_id",):
                        ent_for(did=v)
                    elif (path in ("person_id", "person.id") or (lit["table"] == "persons" and path == "id")) and _is_uuid(v):
                        ent_for(pid=v)
                    elif path in ("person.properties.name", "person.properties.$name"):
                        ent_for(name=v)
        for em, _n in sorted((self.F.get("emails") or {}).items(), key=lambda x: -x[1])[:150]:
            ent_for(email=em)
        for p in self.ovr.get("persons") or []:
            e = ent_for(p.get("email"), p.get("name"), p.get("distinct_id"), p.get("person_id"))
            if e is not None:
                e["props"].update(p.get("props") or {})
        return list(ents.values())

    def build_persons(self):
        super().build_persons()
        self.entities = self.collect_entities()
        # most active identified persons carry the named entities (they have event histories)
        if not self.persons:
            return
        act = np.bincount(self.ud_p, minlength=self.n_persons) if len(self.ud_p) else np.zeros(self.n_persons)
        order = [int(i) for i in np.argsort(-act)]
        self.entity_person = {}
        used = set()
        j = 0
        for k, e in enumerate(self.entities):
            while j < len(order) and order[j] in used:
                j += 1
            if j >= len(order):
                break
            pi = order[j]
            used.add(pi)
            per = self.persons[pi]
            per["identified"] = True
            if e["email"]:
                per["email"] = e["email"]
            if e["name"]:
                per["name"] = e["name"] if " " in e["name"] else f"{e['name']} {per['name'].split()[-1]}"
            if e["distinct_id"]:
                per["user_id"] = e["distinct_id"]
            elif per["user_id"] == per["anon_id"] or per["user_id"] is None:
                per["user_id"] = e["email"] or per["anon_id"]
            if e["person_id"]:
                per["id"] = e["person_id"]
            per["entity"] = k
            self.entity_person[k] = pi
        self.v2["named_entities"] = len(self.entity_person)

    def build_groups(self):
        """rule: group keys and names that production filtered on ($group_N = key, groups.key / properties.name)
        exist in the twin: the first groups of that type take those keys/names (memberships follow)."""
        super().build_groups()
        if not getattr(self, "group_types", None):
            return
        by_idx = {idx: name for idx, name, _ in self.group_types}
        keys_for, names_for = C.defaultdict(list), C.defaultdict(list)
        for lit in self.Q.get("entity_literals") or []:
            path, table = lit["path"], lit["table"]
            vals = [v for l in lit["lit"] if op_eq(l.get("op")) for v in l.get("values") or [] if isinstance(v, (str, int))]
            m = re.search(r"\$group_(\d)", path)
            if m:
                keys_for[int(m.group(1))].extend(str(v) for v in vals)
            elif table == "groups" and path in ("key", "group_key"):
                keys_for[0].extend(str(v) for v in vals)
            elif table == "groups" and path in ("properties.name", "properties.$name"):
                names_for[0].extend(str(v) for v in vals)
        n = 0
        for idx, keys in keys_for.items():
            if idx not in self.groups:
                continue
            name = by_idx[idx]
            remap = {}
            for g, k in zip(self.groups[idx], dict.fromkeys(keys)):
                remap[g["key"]] = k
                g["key"] = k
                n += 1
            for pg in self.person_groups:
                if pg.get(name) in remap:
                    pg[name] = remap[pg[name]]
        for idx, names in names_for.items():
            for g, nm in zip(self.groups.get(idx) or [], dict.fromkeys(names)):
                g["props"]["name"] = nm
                n += 1
        self.v2["groups_from_filters"] = n

    def person_properties(self):
        super().person_properties()
        ent_vals = set()
        for e in getattr(self, "entities", []):
            for v in (e.get("email"), e.get("name")):
                if v:
                    ent_vals.add(str(v).lower())
        changed = 0
        despread = 0
        for i, per in enumerate(self.persons):
            props = per.get("props") or {}
            dirty = False
            k = per.get("entity")
            if k is not None:
                e = self.entities[k]
                for p, v in e["props"].items():
                    props[p] = v
                if e["email"]:
                    for p in list(props) or ["email"]:
                        if p.lower() in ("email", "$email", "user_email", "email_address"):
                            props[p] = e["email"]
                    props.setdefault("email", e["email"])
                if e["name"]:
                    props.setdefault("name", per["name"])
                    for p in list(props):
                        if p.lower() in ("name", "$name", "full_name", "display_name"):
                            props[p] = per["name"]
                dirty = True
                changed += 1
            else:
                # identity values from the spec (anonymizer placeholders, named people) stay on their own person
                for p, v in list(props.items()):
                    if isinstance(v, str) and v.lower() in ent_vals and ("email" in p.lower() or "name" in p.lower()):
                        if "email" in p.lower():
                            props[p] = per["email"] or f"{per['name'].split()[0].lower()}.{i}@{self.company}.io"
                        else:
                            props[p] = per["name"]
                        despread += 1
                        dirty = True
            if dirty:
                per["props"] = props
                self.person_props_json[i] = orjson.dumps(props).decode()
        self.v2["entity_persons_props"] = changed
        self.v2["identity_values_despread"] = despread

    # ------------------------------------------------------------------ objects
    def _agent_created(self) -> set[str]:
        """rule (r1): ids of insights/dashboards/notebooks first seen at or after a creation call by the production
        agent and never named in a user turn (they are the conversation's output, not its starting state)."""
        created_turns = sorted(x["turn"] for v in (self.F.get("created_by_agent") or {}).values() for x in v if not x.get("is_error"))
        created_turns += [c["turn"] for c in self.F.get("calls") or [] if c.get("tool") == "create_insight" and not c.get("is_error")]
        if not created_turns:
            return set()
        first_create = min(created_turns)
        first_seen = {}
        for c in self.F.get("calls") or []:
            ids = []
            if c.get("object"):
                ids.append(str(c["object"]))
            for i in ids:
                first_seen.setdefault(i, c["turn"])
        for kind in ("insights", "dashboards"):  # rule (r11): objects first shown in a later turn's attached context
            for oid, o in ((self.F.get("objects") or {}).get(kind) or {}).items():
                if o.get("from_context") and o.get("context_turn") is not None:
                    # attached context arrives with the user message, before the agent acts in that turn
                    first_seen[str(oid)] = min(first_seen.get(str(oid), 10**6), int(o["context_turn"]) - 0.5)
        for did, d in ((self.F.get("objects") or {}).get("dashboards") or {}).items():
            for t in d.get("tiles") or []:
                if t.get("short_id"):
                    first_seen.setdefault(str(t["short_id"]), first_seen.get(str(did), 10**6))
        text = self.user_text
        return {i for i, t in first_seen.items() if t >= first_create and i not in text}

    def objects(self):
        objs, excluded = super().objects()
        fo = {k: dict(v) for k, v in (self.F.get("objects") or {}).items()}
        made = self._agent_created()
        if made:
            for kind in ("insights", "notebooks", "dashboards"):
                for i in list((fo.get(kind) or {}).keys()):
                    if str(i) in made:
                        fo[kind].pop(i)
                        self.v2[f"agent_created_{kind}_skipped"] += 1
                objs[kind] = [o for o in objs.get(kind, []) if str(o.get("short_id") or o.get("key")) not in made]
        by_key = {kind: {str(o.get("key")): o for o in objs.get(kind, [])} for kind in ("insights", "notebooks", "dashboards")}
        n = C.Counter()
        for sid, fi in (fo.get("insights") or {}).items():
            if not sid:
                continue
            o = by_key["insights"].get(sid)
            if o is None:
                o = {"key": sid, "name": fi.get("name"), "sources": None}
                objs.setdefault("insights", []).append(o)
                n["insights_added"] += 1
            o["short_id"] = sid
            if fi.get("name"):
                o["name"] = fi["name"]
            if fi.get("description"):
                o["description"] = fi["description"]
            q = fi.get("query")
            if isinstance(q, dict) and q.get("kind"):
                if q["kind"] in ("InsightVizNode", "DataVisualizationNode", "DataTableNode"):
                    o["query_full"] = q
                elif q["kind"] == "HogQLQuery":
                    o["query_full"] = {"kind": "DataVisualizationNode", "source": q}
                else:
                    o["query_full"] = {"kind": "InsightVizNode", "source": q}
                n["insights_with_query"] += 1
        for sid, nb in (fo.get("notebooks") or {}).items():
            o = by_key["notebooks"].get(sid)
            if o is None:
                o = {"key": sid}
                objs.setdefault("notebooks", []).append(o)
                n["notebooks_added"] += 1
            o["short_id"] = sid
            o["title"] = nb.get("title") or o.get("title")
            o["content_markdown"] = nb.get("content_markdown")
            o["created_at_prod"] = nb.get("created_at")
            n["notebooks_with_content"] += 1
        for did, d in (fo.get("dashboards") or {}).items():
            o = by_key["dashboards"].get(str(did))
            if o is None:
                o = {"key": str(did), "name": d.get("name")}
                objs.setdefault("dashboards", []).append(o)
                n["dashboards_added"] += 1
            if str(did).isdigit():
                o["dashboard_id"] = int(did)
            o["name"] = d.get("name") or o.get("name")
            if d.get("description"):
                o["description"] = d["description"]
            o["tile_short_ids"] = [t.get("short_id") for t in d.get("tiles") or [] if t.get("short_id")]
        # rule: same-customer completion. Objects referenced by id in the user text or URLs that this trace never read
        # come from the cross-trace index (another conversation of the customer read them).
        xi = xindex()
        have = {k: {str(o.get("short_id") or o.get("key")) for o in objs.get(k, [])} for k in ("insights", "notebooks", "dashboards")}
        refs = {"dashboards": set(REF_DASH.findall(self.user_text)), "notebooks": set(REF_NB.findall(self.user_text)),
                "insights": set(REF_INS.findall(self.user_text))}
        for r in self.F.get("url_refs") or []:
            k = {"dashboard": "dashboards"}.get(r.get("kind"), r.get("kind"))
            if k in refs and r.get("id"):
                refs[k].add(r["id"])
        for did in sorted(refs["dashboards"] - have["dashboards"]):
            d = (xi.get("dashboards") or {}).get(did)
            if not d:
                continue
            o = {"key": did, "name": d.get("name"), "description": d.get("description"), "dashboard_id": int(did) if did.isdigit() else None,
                 "tile_short_ids": [t.get("short_id") for t in d.get("tiles") or [] if t.get("short_id")], "from_xindex": True}
            objs.setdefault("dashboards", []).append(o)
            have["dashboards"].add(did)
            n["xindex_dashboards"] += 1
            for t in d.get("tiles") or []:
                if t.get("short_id"):
                    refs["insights"].add(t["short_id"])
        for sid in sorted(refs["insights"] - have["insights"]):
            i = (xi.get("insights") or {}).get(sid)
            if not i:
                continue
            o = {"key": sid, "short_id": sid, "name": i.get("name"), "description": i.get("description"), "from_xindex": True}
            q = i.get("query")
            if isinstance(q, dict) and q.get("kind"):
                o["query_full"] = q if q["kind"] in ("InsightVizNode", "DataVisualizationNode", "DataTableNode") else (
                    {"kind": "DataVisualizationNode", "source": q} if q["kind"] == "HogQLQuery" else {"kind": "InsightVizNode", "source": q})
            objs.setdefault("insights", []).append(o)
            have["insights"].add(sid)
            n["xindex_insights"] += 1
        for sid in sorted(refs["notebooks"] - have["notebooks"]):
            nb = (xi.get("notebooks") or {}).get(sid)
            if not nb:
                continue
            objs.setdefault("notebooks", []).append({"key": sid, "short_id": sid, "title": nb.get("title"),
                                                     "content_markdown": nb.get("content_markdown"), "from_xindex": True})
            have["notebooks"].add(sid)
            n["xindex_notebooks"] += 1
        for did in sorted(refs["dashboards"] - have["dashboards"]):
            if did.isdigit():  # rule (r1): a dashboard named by id in the text exists (as a stub) even if never read
                objs.setdefault("dashboards", []).append({"key": did, "name": None, "dashboard_id": int(did), "text_stub": True})
                have["dashboards"].add(did)
                n["text_stub_dashboards"] += 1
        # URL references in the user text whose object the trace never read: create a titled stub with that id
        for r in self.F.get("url_refs") or []:
            kind = {"notebooks": "notebooks", "insights": "insights", "dashboard": "dashboards", "dashboards": "dashboards"}.get(r.get("kind"))
            rid = r.get("id")
            if not kind or not rid or rid in {str(o.get("short_id") or o.get("key")) for o in objs.get(kind, [])}:
                continue
            if kind == "dashboards" and not rid.isdigit():
                continue
            stub = {"key": rid, "name": None, "url_stub": True}
            if kind == "dashboards":
                stub["dashboard_id"] = int(rid)
            else:
                stub["short_id"] = rid
            objs.setdefault(kind, []).append(stub)
            n[f"url_stub_{kind}"] += 1
        self.v2.update(n)
        return objs, excluded

    # ------------------------------------------------------------------ warehouse
    def warehouse(self, out_dir):
        tables = self.merged_tables()
        if not tables:
            return {}
        os.makedirs(os.path.join(out_dir, "warehouse"), exist_ok=True)
        uf = UF()
        for a, b in self.Q.get("joins") or []:
            ta, ca = self.canon_table(a[0], tables), a[1]
            tb, cb = self.canon_table(b[0], tables), b[1]
            if ta in tables or tb in tables:
                uf.union((ta, ca), (tb, cb))
        pools: dict = {}
        schema_out = {}
        for tname, tb in tables.items():
            tr = random.Random(stable_seed(self.S["id"], "wh2", tname))
            seeds = self.seed_rows(tname, tb, tr)
            nfill = tr.randint(200, 3000)
            if re.search(r"user|person|customer|account|contact|member", tname, re.I):
                nfill = max(50, min(20000, int(self.n_persons * tr.uniform(0.3, 0.9))))
            if seeds:
                nfill = max(50, min(nfill, len(seeds) // 4 + 50))
            n = nfill + len(seeds)
            data, cols_out = {}, []
            for cname, col in tb["columns"].items():
                ctype = col["type"]
                arr = self.wh_values(tname, cname, col, nfill, tr, uf, pools, tables)
                vals = [self.cast(s.get(cname), ctype) if cname in s else None for s in seeds]
                if seeds:
                    # seed rows lacking this column get filler values
                    fill = self.wh_values(tname, cname, col, len(seeds), random.Random(tr.random()), uf, pools, tables)
                    vals = [v if (cname in s and v is not None) else f for v, s, f in zip(vals, seeds, fill)]
                at = WH_TYPES.get(ctype, pa.string())
                try:
                    data[cname] = pa.array(vals + arr, at)
                except Exception:  # noqa: BLE001
                    data[cname] = pa.array([None if x is None else str(x) for x in vals + arr], pa.string())
                    ctype = "string"
                cols_out.append({"name": cname, "type": ctype, "description": col.get("description"), "origin": col["origin"]})
            fn = re.sub(r"[^A-Za-z0-9_.-]+", "_", tname) + ".parquet"
            if data:
                pq.write_table(pa.table(data), os.path.join(out_dir, "warehouse", fn), compression="zstd")
            schema_out[tname] = {"file": f"warehouse/{fn}", "kind": tb.get("kind"), "description": tb.get("description"),
                                 "columns_inferred": tb.get("inferred", False), "rows": n if data else 0,
                                 "seed_rows": len(seeds), "columns": cols_out, "joins": tb.get("joins") or []}
            self.v2["wh_seed_rows"] += len(seeds)
            self.v2["wh_columns"] += len(cols_out)
            self.v2["wh_columns_from_sql"] += sum(1 for c in cols_out if c["origin"] == "sql")
            self.v2["wh_columns_from_members"] += sum(1 for c in cols_out if c["origin"] == "member")
        return schema_out

    @staticmethod
    def canon_table(name, tables):
        if name in tables:
            return name
        flat = name.replace(".", "_")
        for t in tables:
            if t.replace(".", "_") == flat or t.split(".")[-1] == name.split(".")[-1] and len(name.split(".")) > 1:
                return t
        return name

    def merged_tables(self) -> dict:
        out: dict = {}

        def add_spec_tables(tabs, origin):
            for tn, tb in (tabs or {}).items():
                t = out.setdefault(self.canon_table(tn, out), {"columns": {}, "joins": [], "kind": tb.get("kind"),
                                                                "description": tb.get("description")})
                for f in tb.get("fields") or []:
                    nm, ty = f.get("name"), (f.get("type") or "").lower()
                    if not nm:
                        continue
                    if ty in ("lazy_table", "virtual_table", "view"):
                        if all(j["name"] != nm for j in t["joins"]):
                            t["joins"].append({"name": nm, "type": f.get("type"), "description": f.get("description")})
                        continue
                    if nm not in t["columns"]:
                        t["columns"][nm] = {"type": norm_type(ty), "origin": origin, "description": f.get("description"),
                                            "spec_type": ty}
        add_spec_tables(self.S["warehouse"], "spec")
        for ms in self.member_specs:
            add_spec_tables(((ms.get("warehouse") or {}).get("tables")), "member")
        for tn, cols in (self.Q.get("dw") or {}).items():
            t = out.setdefault(self.canon_table(tn, out), {"columns": {}, "joins": [], "kind": "table", "description": None})
            for cname, info in cols.items():
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", cname) or cname.lower() in ("properties", "person"):
                    continue
                col = t["columns"].get(cname)
                ty = infer_type(cname, info)
                if col is None:
                    t["columns"][cname] = col = {"type": ty, "origin": "sql", "description": None, "spec_type": None}
                elif not col.get("spec_type") or col["type"] == "string" and ty in ("datetime", "date") and col["origin"] != "spec":
                    col["type"] = ty if col["type"] == "string" else col["type"]
                col["values"] = info.get("values") or []
                col["literals"] = info.get("literals") or []
        for tn, cols in (self.ovr.get("warehouse") or {}).items():
            t = out.setdefault(self.canon_table(tn, out), {"columns": {}, "joins": [], "kind": "table", "description": None})
            for cname, info in cols.items():
                col = t["columns"].setdefault(cname, {"type": info.get("type") or "string", "origin": "override",
                                                      "description": None, "spec_type": None})
                if info.get("type"):
                    col["type"] = info["type"]
                if info.get("values"):
                    col["values"] = list(info["values"])
        # rule: same-customer schema completion. Tables this conversation names (user text or its SQL) that are
        # missing, or present only as a thin stub (<= 7 columns), take the richest schema any trace or spec showed.
        xt = xindex().get("tables") or {}
        flat = {k.replace(".", "_"): k for k in xt}
        named = {m.group(0) for m in REF_TOKEN.finditer(self.ref_text)}
        cand = set()
        for tok in named:
            k = tok if tok in xt else flat.get(tok.replace(".", "_"))
            if k and not k.startswith(("events", "persons", "sessions")):
                cand.add(k)
        for tn in list(out) + sorted(cand):
            k = tn if tn in xt else flat.get(tn.replace(".", "_"))
            if not k:
                continue
            t = out.get(self.canon_table(tn, out))
            if t is not None and len(t["columns"]) > 7:
                continue
            if t is None:
                if tn not in cand:
                    continue
                t = out.setdefault(tn, {"columns": {}, "joins": [], "kind": "table", "description": None})
                self.v2["xindex_tables_added"] += 1
            added = 0
            for fdef in xt[k].get("fields") or []:
                nm, ty = fdef.get("name"), (fdef.get("type") or "").lower()
                if nm and nm not in t["columns"] and ty not in ("lazy_table", "virtual_table", "view"):
                    t["columns"][nm] = {"type": norm_type(ty), "origin": "customer", "description": None, "spec_type": ty}
                    added += 1
            if added:
                self.v2["xindex_table_columns"] += added
        for tn, t in out.items():
            if not t["columns"]:
                for c, ty, _ in gen.infer_columns(tn, [x.get("sql") for x in self.F.get("calls") or [] if x.get("sql")]):
                    t["columns"][c] = {"type": norm_type(ty), "origin": "inferred", "description": None, "spec_type": None}
                t["inferred"] = True
        return out

    def seed_rows(self, tname, tb, tr) -> list[dict]:
        rows = []
        for key, sets in (self.Q.get("dw_seeds") or {}).items():
            if self.canon_table(key, {tname: 1}) != tname and key != tname:
                continue
            for s in sets:
                fixed = {}
                for t, p, lits in s.get("where") or []:
                    col = p.split(".")[0]
                    for l in lits:
                        vals = l.get("values") or []
                        if vals and op_eq(l.get("op")):
                            fixed.setdefault(col, vals)
                if s.get("rows"):
                    for r in s["rows"]:
                        d = {k.split(".")[0]: v for k, v in r.items()}
                        for c, vals in fixed.items():
                            d.setdefault(c, vals[0])
                        rows.append(d)
                elif s.get("groups"):
                    total = sum((next(iter(g["aggs"].values()), None) or 0) for g in s["groups"] if any(k.startswith("count") for k in g["aggs"]))
                    scale = min(1.0, MAX_SEED_ROWS_PER_TABLE / 2 / total) if total else 1.0
                    for g in s["groups"]:
                        cnt = next((v for k, v in g["aggs"].items() if k.startswith("count(") or k.startswith("uniq(")), None)
                        k_rows = max(1, int(round((cnt or 1) * scale)))
                        sums = {k[4:-1]: v for k, v in g["aggs"].items() if k.startswith("sum(") and v is not None and k[4:-1]}
                        avgs = {k[4:-1]: v for k, v in g["aggs"].items() if k.startswith("avg(") and v is not None and k[4:-1]}
                        for _ in range(k_rows):
                            d = {k.split(".")[0]: v for k, v in g["dims"].items()}
                            for c, vals in fixed.items():
                                d.setdefault(c, tr.choice(vals))
                            for c, v in sums.items():
                                d[c.split(".")[0]] = round(v / k_rows, 4) if cnt else v
                            for c, v in avgs.items():
                                d[c.split(".")[0]] = v
                            rows.append(d)
                if len(rows) > MAX_SEED_ROWS_PER_TABLE:
                    break
        rows.extend(self.literal_rows(tname, tr))
        return rows[:MAX_SEED_ROWS_PER_TABLE]

    def literal_rows(self, tname, tr) -> list[dict]:
        """rule: warehouse queries that production answered find rows here. For each such uncorrupted query that
        reads this table, add rows satisfying its literal predicates on this table, and give the columns of its
        join pairs a shared key per row (the joined table gets the same keys)."""
        out = []
        fc = {c["k"]: c for c in self.F.get("calls") or []}
        for qc in self.Q.get("calls") or []:
            if not qc.get("ok") or qc.get("is_error") or qc.get("corrupted"):
                continue
            tabs = [t for t in qc.get("tables") or [] if self.canon_table(t, {tname: 1}) == tname or t == tname]
            if not tabs:
                continue
            call = fc.get(qc["k"]) or {}
            n_prod = call.get("n_rows") or len(call.get("rows") or [])
            if not n_prod:
                continue
            k = int(min(50, max(3, n_prod)))
            preds = C.defaultdict(list)
            for t, p, lits in qc.get("literals") or []:
                if t in tabs:
                    preds[p.split(".")[0]].extend(lits)
            joins = []
            for a_, b_ in qc.get("join_pairs") or []:
                for (t1, c1), (t2, c2) in ((a_, b_), (b_, a_)):
                    if t1 in tabs:
                        joins.append(c1)
            if not preds and not joins:
                continue
            for i in range(k):
                row = {}
                for col, lits in preds.items():
                    v = self._satisfy(lits, tr)
                    if v is not None:
                        row[col] = v
                for col in joins:
                    row[col] = 900000000 + qc["k"] * 1000 + i  # numeric, valid as string or integer key
                out.append(row)
            self.v2["wh_literal_rows"] += k
        return out

    @staticmethod
    def _satisfy(lits, tr):
        val = None
        for l in lits:
            op = str(l.get("op")).lower()
            vals = [v for v in l.get("values") or [] if v is not None]
            if not vals:
                continue
            v = vals[0]
            d = parse_when(v) if isinstance(v, str) else None
            x = numv(v) if not isinstance(v, bool) else None
            if op in ("==", "=", "in"):
                val = tr.choice(vals)
            elif op in (">", ">="):
                val = (d + dt.timedelta(days=15)).isoformat() if d else (x * 1.5 + 1 if x is not None else val)
            elif op in ("<", "<="):
                val = (d - dt.timedelta(days=15)).isoformat() if d else ((x * 0.5 if x > 0 else x - 1) if x is not None else val)
            elif op in ("!=", "not in"):
                if val is None:
                    val = (x + 1) if x is not None else f"{v}_other"
            elif op in ("like", "ilike"):
                val = str(v).replace("%", "")
        return val

    def cast(self, v, ctype):
        if v is None:
            return None
        s = str(v).strip()
        if s in NULLS:
            return None
        try:
            if ctype == "integer":
                return int(float(s.replace(",", "")))
            if ctype in ("float", "decimal"):
                return float(s.replace(",", ""))
            if ctype == "boolean":
                return s.lower() in ("true", "1", "t", "yes")
            if ctype == "datetime":
                d = parse_when(s)
                return int(d.timestamp() * 1e6) if d else None
            if ctype == "date":
                d = parse_when(s)
                return d.date() if d else None
        except Exception:  # noqa: BLE001
            return None
        return s

    def wh_values(self, tname, cname, col, n, tr, uf, pools, tables):
        ctype = col["type"]
        lc = cname.lower()
        obs = [cell(v) for v in col.get("values") or []]
        obs = [v for v in obs if v is not None]
        lits = []
        for l in col.get("literals") or []:
            lits.extend(x for x in l.get("values") or [] if x is not None and not isinstance(x, (list, dict)))
        root = uf.find((tname, cname)) if (tname, cname) in uf.p else None
        if root is not None:
            pool = pools.get(root)
            if pool is None:
                pool = self.key_pool(root, uf, tr, ctype, obs + [str(x) for x in lits])
                pools[root] = pool
            is_primary = lc == "id" or (root[0] == tname and root[1] == cname)
            if is_primary:
                return [self.cast(pool[i % len(pool)], ctype) for i in range(n)]
            return [self.cast(tr.choice(pool), ctype) for _ in range(n)]
        if ctype in ("datetime", "date"):
            dates = [parse_when(v) for v in obs + [str(x) for x in lits]]
            dates = [d for d in dates if d]
            hi = self.now
            lo = self.now - dt.timedelta(days=self.H + self.pre_days)
            if dates:
                lo = min(lo, min(dates) - dt.timedelta(days=3))
                hi = max(min(dates), min(hi, max(dates) + dt.timedelta(days=30)))
            month = bool(MONTH_NAME.search(cname)) or (dates and all(d.day == 1 and d.hour == 0 for d in dates))
            out = []
            span = max(1.0, (hi - lo).total_seconds())
            for _ in range(n):
                d = lo + dt.timedelta(seconds=tr.uniform(0, span))
                if month:
                    d = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                out.append(d.date() if ctype == "date" else int(d.timestamp() * 1e6))
            return out
        if FLAG_NAME.search(cname) and ctype in ("integer", "float", "boolean", "string"):
            vals = set(str(v).lower() for v in obs + [str(x) for x in lits])
            p = tr.uniform(0.2, 0.6)
            if ctype == "boolean":
                return [tr.random() < p for _ in range(n)]
            if ctype == "string" and vals and not vals <= {"0", "1"}:
                pool = sorted(vals)
                return [tr.choice(pool) for _ in range(n)]
            if ctype == "string":
                return [("true" if tr.random() < p else "false") if "true" in vals or not vals else str(int(tr.random() < p)) for _ in range(n)]
            return [int(tr.random() < p) if ctype == "integer" else float(tr.random() < p) for _ in range(n)]
        if ctype in ("integer", "float", "decimal"):
            nums = [numv(v) for v in obs] + [float(x) for x in lits if isinstance(x, (int, float)) and not isinstance(x, bool)]
            nums = [x for x in nums if x is not None]
            if nums:
                nums.sort()
                lo, hi = nums[0], nums[-1]
                med = nums[len(nums) // 2]
                out = []
                for _ in range(n):
                    if tr.random() < 0.5:
                        v = tr.choice(nums)
                    else:
                        v = med * math.exp(tr.gauss(0, 0.8)) if med > 0 else tr.uniform(lo, hi if hi > lo else lo + 1)
                    out.append(int(round(v)) if ctype == "integer" else round(v, 2))
                return out
            arr, _ = wh_column(cname, ctype, n, tr, self)
            return arr
        if ctype == "boolean":
            p = tr.uniform(0.2, 0.8)
            return [tr.random() < p for _ in range(n)]
        if ctype in ("json", "array"):
            arr, _ = wh_column(cname, ctype, n, tr, self)
            return arr
        # strings: production values and literals first (an enum), then v1 heuristics
        pool = [v for v in obs if v] + [str(x) for x in lits if isinstance(x, str) and "%" not in x]
        if pool:
            cnt = C.Counter(pool)
            vals = list(cnt)
            w = [cnt[v] for v in vals]
            if len(vals) >= 0.8 * len(pool) and len(vals) > 30:  # unique-ish (ids, names): keep them + similar tail
                arr, _ = wh_column(cname, "string", n, tr, self)
                return [tr.choice(vals) if tr.random() < 0.6 else a for a in arr]
            return [tr.choices(vals, w)[0] for _ in range(n)]
        arr, _ = wh_column(cname, "string", n, tr, self)
        return arr

    def key_pool(self, root, uf, tr, ctype, extra):
        members = [k for k in uf.p if uf.find(k) == root]
        names = " ".join(c.lower() for _, c in members)
        if re.search(r"email", names) and self.persons:
            pool = [p["email"] for p in self.persons if p["email"]][:20000]
        elif re.search(r"distinct_id|user_id|external_id", names) and self.persons:
            pool = [p["user_id"] for p in self.persons][:20000]
        elif re.search(r"person_id", names) and self.persons:
            pool = [p["id"] for p in self.persons][:20000]
        else:
            k = tr.randint(150, 2500)
            if ctype in ("integer", "float"):
                pool = [str(1000 + i) for i in range(k)]
            else:
                pre = re.sub(r"[^a-z]", "", root[1].lower().replace("_id", ""))[:4] or "key"
                pool = [f"{pre}_{stable_seed(self.S['id'], root[0], root[1], i) % 10**10:010d}" for i in range(k)]
        pool = list(dict.fromkeys([x for x in extra if x] + pool))
        return pool or ["1"]

    # ------------------------------------------------------------------ dynamics and seeds (post-processing)
    def profiles(self) -> dict:
        """event -> (np.array factor per local date ordinal offset, first_ordinal). Factor 1 = recent level."""
        out = {}
        best = {}
        for s in self.Q.get("series") or []:
            if s["event"] not in self.ev_counts or s.get("math") not in ("total", "dau"):
                continue
            L = {"day": 1, "week": 7, "month": 30}.get(s.get("interval"))
            if not L:
                continue
            pts = [(parse_when(p[0]), p[1], p[2]) for p in s["points"]]
            pts = [(d.date(), v, part) for d, v, part in pts if d is not None]
            if len(pts) < 4:
                continue
            score = (not s.get("filtered"), len(pts))
            if s["event"] in best and best[s["event"]][0] >= score:
                continue
            best[s["event"]] = (score, pts, L)
        for sp in self.ovr.get("spikes") or []:
            e = sp.get("event")
            a, b = parse_when(sp.get("from") or ""), parse_when(sp.get("to") or sp.get("from") or "")
            if e in self.ev_counts and a and b:
                n = (b.date() - a.date()).days + 1
                pts = [(a.date() + dt.timedelta(days=i), float(sp.get("factor", 3.0)), False) for i in range(n)]
                before = [(a.date() - dt.timedelta(days=i), 1.0, False) for i in range(28, 0, -1)]
                best[e] = ((True, 10**6), before + pts + [(b.date() + dt.timedelta(days=1), 1.0, False)], 1)
        for e, (_, pts, L) in best.items():
            d0 = min(d for d, _, _ in pts)
            d1 = max(d for d, _, _ in pts) + dt.timedelta(days=L - 1)
            n = (d1 - d0).days + 1
            lvl = np.full(n, np.nan)
            for d, v, part in pts:
                i = (d - d0).days
                span = L
                if part:
                    span = max(1, min(L, (self.now.date() - d).days + 1))
                lvl[i:i + span] = v / span
            ok = ~np.isnan(lvl)
            if ok.sum() < 3 or np.nanmax(lvl) <= 0:
                continue
            ref = np.nanmean(lvl[-30:]) if np.isfinite(np.nanmean(lvl[-30:])) else np.nanmean(lvl)
            if not ref or ref <= 0:
                ref = np.nanmean(lvl[lvl > 0])
            f = lvl / ref
            # interpolate gaps
            idx = np.arange(n)
            f = np.interp(idx, idx[ok], f[ok])
            out[e] = (f, d0)
        return out

    def coherent_sessions(self, tab):
        """rule (r8): (1) a session's UTM medium/campaign follow its source (one consistent tuple); (2) web sessions
        start with their landing $pageview: when another event comes first, the session's first pageview moves to 1 s
        before it (bounce, entry page and entry UTM metrics need the landing pageview first)."""
        props = tab.column("properties").to_pylist()
        mediums = list(self.utm_vals.get("utm_medium") or []) if hasattr(self, "utm_vals") else []
        campaigns = list(self.utm_vals.get("utm_campaign") or []) if hasattr(self, "utm_vals") else []
        changed = 0
        for i, pr in enumerate(props):
            if pr and '"utm_source"' in pr:
                d = orjson.loads(pr)
                src = d.get("utm_source")
                if isinstance(src, str) and src:
                    med, camp = coherent_utm(src, mediums, campaigns)
                    if d.get("utm_medium") != med or d.get("utm_campaign") != camp:
                        d["utm_medium"], d["utm_campaign"] = med, camp
                        props[i] = orjson.dumps(d).decode()
                        changed += 1
        if changed:
            tab = tab.set_column(tab.schema.get_field_index("properties"), "properties",
                                 pa.array(props, tab.schema.field("properties").type))
        self.v2["utm_tuples_made_coherent"] = changed
        if not getattr(self, "web", False) or "$session_id" not in tab.schema.names:
            return tab
        sid = tab.column("$session_id").to_pylist()
        ev = tab.column("event").to_pylist()
        ts = tab.column("timestamp").cast(pa.int64()).to_numpy().copy()
        first: dict = {}
        first_pv: dict = {}
        for i, (s_, e) in enumerate(zip(sid, ev)):
            if not s_:
                continue
            if s_ not in first or ts[i] < ts[first[s_]]:
                first[s_] = i
            if e == "$pageview" and (s_ not in first_pv or ts[i] < ts[first_pv[s_]]):
                first_pv[s_] = i
        moved = 0
        for s_, i0 in first.items():
            j = first_pv.get(s_)
            if j is not None and j != i0 and ts[j] > ts[i0]:
                ts[j] = ts[i0] - 1_000_000
                moved += 1
        if moved:
            tab = tab.set_column(tab.schema.get_field_index("timestamp"), "timestamp",
                                 pa.array(ts, pa.int64()).cast(tab.schema.field("timestamp").type))
        self.v2["sessions_landing_pageview_moved"] = moved
        return tab

    def _event_props(self, e: str) -> set:
        return set((((self.S.get("events") or {}).get(e) or {}).get("properties") or {}).keys())

    def override_zeroed_events(self) -> set:
        """Events an override spike sets to factor 0 (curation: the event stops firing from that date)."""
        return {sp.get("event") for sp in self.ovr.get("spikes") or [] if float(sp.get("factor", 1)) == 0}

    def postprocess(self, out_dir):
        path = os.path.join(out_dir, "events.parquet")
        profs = self.profiles()
        seeds = self.event_seed_rows()
        if not profs and not seeds:
            return
        tab = pq.read_table(path)
        big = pa.schema([pa.field(f.name, pa.large_string()) if f.type == pa.string() else f for f in tab.schema])
        tab = tab.cast(big)
        n0 = tab.num_rows
        rng = np.random.default_rng(stable_seed(self.S["id"], "v2post"))
        ts_us = tab.column("timestamp").cast(pa.int64()).to_numpy()
        events = tab.column("event").to_numpy(zero_copy_only=False)
        off = self.now.astimezone(self.tz).utcoffset().total_seconds()
        local_day = ((ts_us / 1e6 + off) // 86400).astype(np.int64)  # days since epoch (local, fixed offset)
        keep = np.ones(n0, dtype=bool)
        dup_idx = []
        dyn_events = 0
        zeroed = self.override_zeroed_events()  # rule (r3): an override that stops an event is not undone
        for e, (f, d0) in profs.items():
            m = events == e
            if not m.any():
                continue
            dyn_events += 1
            ep = (d0 - dt.date(1970, 1, 1)).days
            rel = local_day[m] - ep
            fac = np.where(rel < 0, f[0] if f[:3].max() > 0 else 0.0, np.where(rel >= len(f), 1.0, f[np.clip(rel, 0, len(f) - 1)]))
            fac = np.minimum(fac, MAX_DUP)
            ii = np.nonzero(m)[0]
            u = rng.random(len(ii))
            keep[ii[(fac < 1) & (u >= fac)]] = False
            if keep[ii].sum() < min(3, len(ii)) and e not in zeroed:  # rule: dynamics never wipes out an event
                keep[ii[np.argsort(ts_us[ii])[-min(3, len(ii)):]]] = True
                self.v2["dynamics_min_kept"] += 1
            extra = rng.poisson(np.maximum(fac - 1, 0))
            if extra.sum():
                dup_idx.append(np.repeat(ii, extra))
        parts = [tab.filter(pa.array(keep))]
        if dup_idx:
            di = np.concatenate(dup_idx)
            dup = tab.take(pa.array(di))
            jitter = rng.integers(-3 * 3600 * 10**6, 3 * 3600 * 10**6, len(di))
            new_ts = np.minimum(ts_us[di] + jitter, int((self.now.timestamp() - 1) * 1e6))
            dup = dup.set_column(dup.schema.get_field_index("timestamp"), "timestamp",
                                 pa.array(new_ts, pa.int64()).cast(pa.timestamp("us", tz="UTC")))
            dup = dup.set_column(dup.schema.get_field_index("uuid"), "uuid",
                                 pa.array([str(uuid.UUID(int=int(x), version=4)) for x in rng.integers(0, 2**63, len(di))] if len(di) else [], pa.string()))
            parts.append(dup)
        if seeds:
            parts.append(self.seed_table(seeds, tab.schema, donor_tab=tab))
        out = pa.concat_tables([p.cast(tab.schema) for p in parts], promote_options="none")
        out = out.unify_dictionaries().combine_chunks()
        out = self.coherent_sessions(out)
        order = pc.sort_indices(out, sort_keys=[("timestamp", "ascending")])
        out = out.take(order)
        pq.write_table(out, path + ".tmp", compression="zstd", row_group_size=100_000)
        os.replace(path + ".tmp", path)
        self.v2["dynamics_events"] = dyn_events
        self.v2["dynamics_dropped"] = int((~keep).sum())
        self.v2["dynamics_duplicated"] = int(sum(len(x) for x in dup_idx))
        self.v2["event_seed_rows"] = len(seeds)
        self.n_events = out.num_rows
        ec = pc.value_counts(out.column("event"))
        self.ev_counts = C.Counter({x["values"].as_py(): x["counts"].as_py() for x in ec})

    def _entity_index(self) -> dict:
        idx = {}
        for k, pi in getattr(self, "entity_person", {}).items():
            e = self.entities[k]
            for v in (e.get("email"), e.get("distinct_id"), e.get("person_id"), e.get("name")):
                if v:
                    idx[str(v).lower()] = pi
        return idx

    def event_seed_rows(self) -> list[dict]:
        rows = []
        ent_by = {}
        for k, pi in getattr(self, "entity_person", {}).items():
            e = self.entities[k]
            for v in (e.get("email"), e.get("distinct_id"), e.get("person_id"), e.get("name")):
                if v:
                    ent_by[str(v).lower()] = pi
        rnd = random.Random(stable_seed(self.S["id"], "evseed"))
        known = set(self.ev_counts)
        for s in self.Q.get("event_seeds") or []:
            if not s.get("rows"):
                continue
            ev_lit = None
            fixed_props = {}
            for t, p, lits in s.get("where") or []:
                for l in lits:
                    vals = l.get("values") or []
                    if not vals or not op_eq(l.get("op")):
                        continue
                    if p == "event":
                        ev_lit = vals
                    elif p.startswith("properties."):
                        fixed_props[p[len("properties."):]] = vals[0]
            w = s.get("window") or {}
            days = w.get("interval_days") or 30
            for r in s["rows"]:
                ev = cell(r.get("event") or "") or (rnd.choice(ev_lit) if ev_lit else None)
                if not ev or not isinstance(ev, str):
                    continue
                when = parse_when(r.get("timestamp") or "") if r.get("timestamp") else None
                if when is None:
                    when = self.now - dt.timedelta(seconds=rnd.uniform(60, days * 86400))
                if when > self.now:
                    continue
                pi = None
                for key in ("person.properties.email", "distinct_id", "person_id", "person.properties.name"):
                    v = cell(r.get(key) or "")
                    if v and v.lower() in ent_by:
                        pi = ent_by[v.lower()]
                        break
                if pi is None:
                    pi = rnd.randrange(self.n_persons) if self.n_persons else None
                if pi is None:
                    continue
                props = dict(fixed_props)
                for k, v in r.items():
                    if k.startswith("properties.") and cell(v) is not None:
                        props[k[len("properties."):]] = cell(v)
                rows.append({"event": ev, "ts": when, "pi": pi, "props": props})
                if len(rows) >= MAX_EVENT_SEEDS:
                    return rows
        self.v2["event_seed_new_event_names"] = len({r["event"] for r in rows} - known)
        rows.extend(self.filter_seed_rows(rnd))
        return rows

    # rule: filter-consistent seeding. Production queries with exact event-property filters that returned data must
    # find matching events in the twin: inject events with the filter values (Trends: per production date and count;
    # SQL: inside the query window, production's single number when visible). Capped per query.
    FILTER_SEED_CAP = 3000

    @staticmethod
    def _exact_filters(props) -> dict | None:
        out = {}
        stack = [props] if isinstance(props, dict) else list(props or [])
        while stack:
            p = stack.pop()
            if not isinstance(p, dict):
                continue
            if "values" in p and p.get("type") in ("AND", "OR"):
                if p.get("type") == "OR" and len(p.get("values") or []) > 1:
                    stack.append((p.get("values") or [None])[0])
                else:
                    stack.extend(p.get("values") or [])
                continue
            if p.get("type") not in ("event", None) or not p.get("key"):
                return None  # person/cohort/group filters cannot be satisfied by event properties
            op = p.get("operator") or "exact"
            v = p.get("value")
            if isinstance(v, list):
                v = v[0] if v else None
            if op in ("exact", "is") and v is not None:
                out[p["key"]] = v
            elif op == "icontains" and isinstance(v, str):
                out[p["key"]] = v
            elif op == "is_set":
                out.setdefault(p["key"], "1")
            elif op == "is_not" and v is not None:
                sv = str(v).lower()
                out.setdefault(p["key"], {"true": "false", "false": "true"}.get(sv, f"other_{v}"))
            elif op in ("is_not_set", "not_icontains", "not_regex", "is_date_after", "is_date_before"):
                continue  # satisfied by leaving the property unset (or not constrained)
            elif op in ("gt", "gte", "lt", "lte") and numv(v) is not None:
                x = numv(v)
                out[p["key"]] = x + 1 if op.startswith("gt") else max(0, x - 1)
            else:
                return None
        return out

    def _date_from(self, src) -> dt.datetime:
        df = str(((src.get("dateRange") or {}).get("date_from")) or "-30d")
        m = re.match(r"^-(\d+)([hdwmy])", df)
        if m:
            n, u = int(m.group(1)), m.group(2)
            return self.now - dt.timedelta(days=n * {"h": 1 / 24, "d": 1, "w": 7, "m": 30, "y": 365}[u])
        return parse_when(df) or self.now - dt.timedelta(days=30)

    def sequence_seed_rows(self, src, call, rnd) -> list[dict]:
        """rule: funnels and retention that production answered need persons doing the steps in order (funnel
        steps within the window; retention target event then returning events on later periods)."""
        rows = []
        start = max(self._date_from(src), self.now - dt.timedelta(days=self.H - 1))
        span = max(3600.0, (self.now - start).total_seconds() - 3600)
        if src["kind"] == "FunnelsQuery":
            steps = []
            for sr in src.get("series") or []:
                f = self._exact_filters(sr.get("properties") or [])
                if not sr.get("event") or f is None:
                    return rows
                steps.append((sr["event"], f))
            if len(steps) < 2:
                return rows
            counts = None  # rule (r1): production step counts ("Total person count" row) set the drop-off
            for r in call.get("rows") or []:
                if r and str(r[0]).strip().lower() == "total person count":
                    vals = [numv(x) for x in r[1:1 + len(steps)]]
                    if len(vals) == len(steps) and all(v is not None for v in vals) and vals[0] and vals[0] > 0:
                        counts = vals
                    break
            k = 25 if counts is None else max(1, min(60, int(counts[0])))
            reach = [1.0] * len(steps) if counts is None else [min(1.0, v / counts[0]) for v in counts]
            if counts is not None:
                self.v2["sequence_seed_funnel_dropoff"] += 1
            for i in range(k):
                pi = rnd.randrange(self.n_persons)
                t = start + dt.timedelta(seconds=rnd.uniform(0, span * 0.7))
                for j, (e, f) in enumerate(steps):
                    if i >= round(k * reach[j]):
                        break
                    rows.append({"event": e, "ts": t, "pi": pi, "props": dict(f)})
                    t = t + dt.timedelta(seconds=rnd.uniform(30, 3600))
            self.v2["sequence_seed_funnels"] += 1
        else:
            rf = src.get("retentionFilter") or {}
            te = (rf.get("targetEntity") or {}).get("id") or (rf.get("targetEntity") or {}).get("name")
            re_ = (rf.get("returningEntity") or {}).get("id") or (rf.get("returningEntity") or {}).get("name") or te
            if not isinstance(te, str) or not isinstance(re_, str) or te == "All events":
                return rows
            per = {"Day": 1, "Week": 7, "Month": 30, "Hour": 1 / 24}.get(rf.get("period") or "Day", 1)
            k = 40
            for _ in range(k):
                pi = rnd.randrange(self.n_persons)
                t = start + dt.timedelta(seconds=rnd.uniform(0, span * 0.5))
                rows.append({"event": te, "ts": t, "pi": pi, "props": {}})
                for j in range(1, rnd.randint(2, 4)):
                    t2 = t + dt.timedelta(days=per * j, seconds=rnd.uniform(0, 3600))
                    if t2 < self.now:
                        rows.append({"event": re_, "ts": t2, "pi": pi, "props": {}})
            self.v2["sequence_seed_retention"] += 1
        return rows

    def filter_seed_rows(self, rnd) -> list[dict]:
        rows = []
        if not self.n_persons:
            return rows
        nowd = self.now
        for call in self.F.get("calls") or []:
            sch = call.get("schema")
            if call.get("is_error") or not isinstance(sch, dict) or not call.get("rows"):
                continue
            src = sch.get("source") if sch.get("kind") in ("InsightVizNode", "DataVisualizationNode") else sch
            if isinstance(src, dict) and src.get("kind") in ("FunnelsQuery", "RetentionQuery"):
                rows.extend(self.sequence_seed_rows(src, call, rnd))
                continue
            if not isinstance(src, dict) or src.get("kind") != "TrendsQuery":
                continue
            glob_f = self._exact_filters(src.get("properties") or [])
            bd = src.get("breakdownFilter") or {}
            bkey, _bt = breakdown_prop(bd)
            bd = bd if (bd.get("breakdown") or bd.get("breakdowns")) else {}
            if bd and bkey and len(src.get("series") or []) == 1 and glob_f is not None:
                # breakdown columns "<label> breakdown for the value `v`": one seeded series per value
                sr = src["series"][0]
                f = self._exact_filters(sr.get("properties") or [])
                if f is None or not sr.get("event") or sr.get("math") not in (None, "total", "dau"):
                    continue
                cols = call.get("cols") or []
                vals = [re.search(r"for the value `([^`]*)`", str(c)) for c in cols[1:]]
                pts_all = []
                for j, m in enumerate(vals):
                    if not m:
                        continue
                    for r in call["rows"]:
                        if len(r) != len(cols):
                            continue
                        d = parse_when(str(r[0]).split(" ")[0])
                        v = numv(r[j + 1])
                        if d and v and v > 0:
                            pts_all.append((d, v, m.group(1)))
                tot = sum(v for _, v, _ in pts_all)
                scale = min(1.0, self.FILTER_SEED_CAP / tot) if tot else 0
                for d, v, bv in pts_all:
                    k = int(round(v * scale)) or (1 if rnd.random() < v * scale else 0)
                    for _ in range(k):
                        when = min(d + dt.timedelta(seconds=rnd.uniform(0, 86399)), nowd - dt.timedelta(seconds=60))
                        rows.append({"event": sr["event"], "ts": when, "pi": rnd.randrange(self.n_persons),
                                     "props": {**glob_f, **f, bkey: bv}})
                if pts_all:
                    self.v2["filter_seed_breakdowns"] += 1
                continue
            if bd:
                continue
            ser = src.get("series") or []
            cols = call.get("cols") or []
            if glob_f is None or len(cols) != len(ser) + 1:
                continue
            for j, sr in enumerate(ser):
                e = sr.get("event")
                f = self._exact_filters(sr.get("properties") or [])
                if not e or f is None or not (f or glob_f) or sr.get("math") not in (None, "total", "dau"):
                    continue
                props = {**glob_f, **f}
                pts = []
                for r in call["rows"]:
                    if len(r) != len(cols):
                        continue
                    d = parse_when(str(r[0]).split(" ")[0])
                    v = numv(r[j + 1])
                    if d and v and v > 0:
                        pts.append((d, v))
                tot = sum(v for _, v in pts)
                if not tot:
                    continue
                scale = min(1.0, self.FILTER_SEED_CAP / tot)
                L = {"day": 1, "week": 7, "month": 30, "hour": 1 / 24}.get(src.get("interval") or "day", 1)
                for d, v in pts:
                    k = int(round(v * scale)) or (1 if rnd.random() < v * scale else 0)
                    for _ in range(k):
                        when = d + dt.timedelta(seconds=rnd.uniform(0, max(1, L) * 86400 - 1))
                        if when >= nowd:
                            when = nowd - dt.timedelta(seconds=rnd.uniform(60, 3600))
                        rows.append({"event": e, "ts": when, "pi": rnd.randrange(self.n_persons), "props": dict(props)})
                self.v2["filter_seed_series"] += 1
        # SQL: event + equality property filters, production non-empty
        for qc in self.Q.get("calls") or []:
            if not qc.get("ok") or qc.get("is_error") or qc.get("corrupted"):
                continue
            evs = qc.get("events") or []
            if not evs or len(evs) > 8:
                continue
            props = {}
            bad = False
            person_fixed = None
            for t, p, lits in qc.get("literals") or []:
                if t != "events":
                    continue
                if p.startswith("properties."):
                    for l in lits:
                        op = str(l.get("op"))
                        vals = l.get("values") or []
                        if vals and op_eq(op):
                            props[p[len("properties."):]] = vals[0]
                        elif vals and op_like(op):
                            v = str(vals[0]).strip("%").replace("%", "")
                            if v:
                                props[p[len("properties."):]] = v
                elif p.startswith("person.") or p in ("distinct_id", "person_id"):
                    vals = [x for l in lits if op_eq(l.get("op")) for x in l.get("values") or []]
                    if vals and isinstance(vals[0], str) and str(vals[0]).lower() in self._entity_index():
                        person_fixed = self._entity_index()[str(vals[0]).lower()]
                    else:
                        bad = True
            if bad or (not props and person_fixed is None):
                continue
            call = next((c for c in self.F.get("calls") or [] if c["k"] == qc["k"]), None)
            if not call or not call.get("rows"):
                continue
            n = None
            if len(call["rows"]) == 1:
                nums = [numv(x) for x in call["rows"][0] if numv(x) is not None]
                if len(nums) > 1:  # rule (r1c): conditional aggregates, the literals are per-column conditions
                    self.v2["filter_seed_sql_multi_agg_skipped"] += 1
                    continue
                n = nums[0] if nums else None
            if n is not None and n < 1:  # rule (r1): production found nothing -> seed nothing
                self.v2["filter_seed_sql_zero_skipped"] += 1
                continue
            k = int(min(self.FILTER_SEED_CAP, n)) if n and n >= 1 else 25
            # rule (r9): filter properties go only to the query's events that carry them (amount_usd belongs to the
            # revenue event, not to every event in "event IN (...)")
            owners = [e for e in evs if props and all(p_ in self._event_props(e) for p_ in props)]
            days = (qc.get("window") or {}).get("interval_days") or 30
            w = qc.get("window") or {}
            a, b = parse_when(w.get("min_date") or ""), parse_when(w.get("max_date") or "")
            if a and b and b == a:  # rule: a single absolute date means that whole day
                b = a + dt.timedelta(days=1) - dt.timedelta(seconds=1)
            for _ in range(k):
                if a and b and b > a:
                    when = a + dt.timedelta(seconds=rnd.uniform(0, (b - a).total_seconds()))
                else:
                    when = nowd - dt.timedelta(seconds=rnd.uniform(60, max(1, days) * 86400))
                if when >= nowd:
                    continue
                ev_pick = rnd.choice(owners) if owners else rnd.choice(evs)
                rows.append({"event": ev_pick, "ts": when, "pi": person_fixed if person_fixed is not None else rnd.randrange(self.n_persons),
                             "props": {k: v for k, v in props.items() if not owners or k in self._event_props(ev_pick)}})
            self.v2["filter_seed_sql"] += 1
            if person_fixed is not None:
                self.v2["filter_seed_sql_person"] += 1
        self.v2["filter_seed_rows"] = len(rows)
        return rows

    DONOR_SKIP = {"$session_id", "$window_id", "$insert_id", "$uuid", "token", "$time", "$sent_at"}

    def _donors(self, tab, rnd):
        """rule (r1): seeded events look like organic ones. Per event name up to 50 organic property dicts; $pageview
        dicts per person; generic $pageview dicts as the fallback."""
        if tab is None or not tab.num_rows:
            return {}, {}, []
        ev = tab.column("event").to_pylist()
        pr = tab.column("properties").to_pylist()
        pid = tab.column("person_id").to_pylist()
        by_ev, by_person_pv, pv = C.defaultdict(list), C.defaultdict(list), []
        for i in rnd.sample(range(len(ev)), min(len(ev), 60000)):
            e = ev[i]
            if len(by_ev[e]) < 50:
                by_ev[e].append(pr[i])
            if e == "$pageview":
                if len(pv) < 400:
                    pv.append(pr[i])
                if len(by_person_pv[pid[i]]) < 3:
                    by_person_pv[pid[i]].append(pr[i])
        return by_ev, by_person_pv, pv

    def _with_donor(self, props, ev, pid, donors, rnd):
        by_ev, by_person_pv, pv = donors
        src = by_ev.get(ev) or by_person_pv.get(pid) or pv
        if not src:
            return props
        try:
            d = orjson.loads(rnd.choice(src))
        except Exception:  # noqa: BLE001
            return props
        out = {k: v for k, v in d.items() if k not in self.DONOR_SKIP}
        if any(k in GEO_PROPS for k in props):  # rule (r8): a seeded geo value brings its whole coherent tuple
            for k in GEO_PROPS:
                out.pop(k, None)
            out.update(geo_tuple(props.get("$geoip_country_code") or props.get("$geoip_country_name"), rnd))
        out.update(props)
        cu, du = out.get("$current_url"), d.get("$current_url")
        if isinstance(cu, str) and cu.startswith("/") and isinstance(du, str) and "://" in du:
            origin = du.split("://", 1)[0] + "://" + du.split("://", 1)[1].split("/", 1)[0]
            out["$current_url"] = origin + cu
            out.setdefault("$pathname", cu.split("?")[0])
        self.v2["seed_donor_props"] += 1
        return out

    def seed_table(self, rows, schema, donor_tab=None):
        cols = {f.name: [] for f in schema}
        rnd = random.Random(stable_seed(self.S["id"], "seedtab"))
        donors = self._donors(donor_tab, random.Random(stable_seed(self.S["id"], "donors")))
        for r in rows:
            per = self.persons[r["pi"]]
            ms = int(r["ts"].timestamp() * 1000)
            sid = uuid7(ms - rnd.randint(0, 600000), rnd)
            props = {"$session_id": sid, "$lib": "web", **self._with_donor(r["props"], r["event"], per["id"], donors, rnd)}
            cols["uuid"].append(str(uuid.UUID(int=rnd.getrandbits(128), version=4)))
            cols["event"].append(r["event"])
            cols["properties"].append(orjson.dumps(props).decode())
            cols["timestamp"].append(int(r["ts"].timestamp() * 1e6))
            cols["distinct_id"].append(per["user_id"] if per["identified"] else per["anon_id"])
            cols["person_id"].append(per["id"])
            cols["$session_id"].append(sid)
            cols["$window_id"].append(sid)
            cols["elements_chain"].append("")
            cols["person_properties"].append(self.person_props_json[r["pi"]])
            for g in range(5):
                cols[f"$group_{g}"].append(None)
            # groups of the person
            for idx, name, _ in getattr(self, "group_types", []):
                key = self.person_groups[r["pi"]].get(name) if hasattr(self, "person_groups") else None
                if key is not None:
                    cols[f"$group_{idx}"][-1] = key
        arrays = []
        for f in schema:
            v = cols[f.name]
            if f.name == "timestamp":
                arrays.append(pa.array(v, pa.int64()).cast(f.type))
            elif pa.types.is_dictionary(f.type):
                arrays.append(pa.array(v, pa.string()).dictionary_encode().cast(f.type))
            else:
                arrays.append(pa.array(v, f.type))
        return pa.Table.from_arrays(arrays, schema=schema)

    # ------------------------------------------------------------------ driver
    def run(self, out_dir):
        man = super().run(out_dir)
        self.postprocess(out_dir)
        man["generator"] = GEN2_VERSION
        man["counts"]["events"] = self.n_events
        man["counts"]["event_names"] = len(self.ev_counts)
        man["v2"] = {**dict(self.v2), **self.v2_info, "calibration": self.calib or None}
        with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
            json.dump(man, fh, indent=1, default=str)
        return man


def _is_uuid(x) -> bool:
    try:
        uuid.UUID(str(x))
        return True
    except Exception:  # noqa: BLE001
        return False


def norm_type(t) -> str:
    t = (t or "").lower()
    if t in ("string", "varchar", "text", "str"):
        return "string"
    if t in ("integer", "int", "int64", "bigint", "int32"):
        return "integer"
    if t in ("float", "double", "decimal", "numeric", "float64", "number"):
        return "float"
    if t in ("boolean", "bool"):
        return "boolean"
    if t in ("datetime", "timestamp", "datetime64"):
        return "datetime"
    if t == "date":
        return "date"
    if t in ("json", "array", "map"):
        return "json" if t != "array" else "array"
    return "string"


def infer_type(cname: str, info: dict) -> str:
    h = C.Counter(info.get("types") or {})
    vals = [cell(v) for v in info.get("values") or []]
    vals = [v for v in vals if v is not None]
    if vals:
        if all(parse_when(v) for v in vals[:50]):
            return "date" if all(len(v.strip()) == 10 for v in vals[:50]) else "datetime"
        nums = [numv(v) for v in vals[:50]]
        if all(x is not None for x in nums):
            return "integer" if all(float(x).is_integer() for x in nums) and not re.search(r"amount|price|rate|pct|revenue|mrr|arr", cname, re.I) else "float"
        if all(v.lower() in ("true", "false") for v in vals[:50]):
            return "boolean"
    if h:
        top = h.most_common(1)[0][0]
        if top == "datetime":
            sh = shape_of(cname)
            return "date" if re.search(r"date$|_date|day$", cname, re.I) and sh != "datetime" else "datetime"
        if top == "numeric":
            return "float" if re.search(r"amount|price|rate|pct|revenue|mrr|arr|value|score|avg", cname, re.I) else "integer"
        if top == "boolean":
            return "boolean"
        if top == "json":
            return "json"
    sh = shape_of(cname)
    return {"datetime": "datetime", "count": "integer", "money": "float", "duration": "float", "bool": "boolean"}.get(sh, "string")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--facts")
    ap.add_argument("--qfacts")
    ap.add_argument("--calib")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-events", type=int, default=6_000_000)
    ap.add_argument("--no-members", action="store_true")
    a = ap.parse_args()
    spec = specio.load(a.spec)
    cid = spec["id"]
    facts = load_json(a.facts or os.path.join(FACTS, f"{cid}.json"))
    qf = load_json(a.qfacts or os.path.join(QFACTS, f"{cid}.json"))
    calib = load_json(a.calib) if a.calib and os.path.exists(a.calib) else None
    members = [] if a.no_members else [s for s in (load_json(os.path.join(SPECS, f"{m}.json")) for m in cluster_members(cid)) if s]
    p = Project2(spec, facts=facts, qfacts=qf, calib=calib, member_specs=members, seed=a.seed, max_events=a.max_events)
    man = p.run(a.out)
    c = man["counts"]
    print(json.dumps({"events": c["events"], "persons": c["persons"], "history_days": man["history_days"],
                      "volume_scale": round(man["volume_scale"], 4), "v2": {k: v for k, v in man["v2"].items() if isinstance(v, (int, float))}}))


if __name__ == "__main__":
    main()
