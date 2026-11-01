"""Generate a synthetic PostHog project from a twin spec (conversation or cluster).

Usage: gen.py SPEC_PATH OUT_DIR [--seed N] [--now ISO] [--max-events N] [--history-days N]
Prints only aggregate counts.
"""
import argparse, bisect, hashlib, json, math, os, random, re, sys, time, uuid
import datetime as dt
from collections import Counter, defaultdict
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import numpy as np
import orjson
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchors, catalog, specio
from specio import num, shape_of
from values import Sampler, VOCAB, stem_of

GEN_VERSION = "twingen-1"
HERE = os.path.dirname(os.path.abspath(__file__))
UTC = dt.timezone.utc


def load_priors():
    P = {}
    for f in os.listdir(os.path.join(HERE, "priors")):
        if f.endswith(".json"):
            P[f[:-5]] = json.load(open(os.path.join(HERE, "priors", f)))
    return P


PRI = None

# $ properties that are computed per page/event rather than per person
PAGE_PROPS = {"$current_url", "$pathname", "$host", "$referrer", "$referring_domain", "$search_engine", "$title",
              "$session_id", "$window_id", "$pageview_id", "$user_id", "$is_identified", "$device_id", "$time",
              "$insert_id", "$session_entry_url", "$session_entry_pathname", "$session_entry_host",
              "$session_entry_referrer", "$session_entry_referring_domain", "$raw_user_agent",
              "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "$groups", "$set", "$set_once",
              "$feature_flag", "$feature_flag_response", "$active_feature_flags", "$exception_list",
              "$prev_pageview_pathname", "$prev_pageview_duration", "$prev_pageview_last_scroll",
              "$prev_pageview_last_scroll_percentage", "$prev_pageview_max_scroll",
              "$prev_pageview_max_scroll_percentage", "$prev_pageview_last_content",
              "$prev_pageview_last_content_percentage", "$prev_pageview_max_content",
              "$prev_pageview_max_content_percentage", "$prev_pageview_id"}
PROFILE_PROPS = {"$browser", "$browser_version", "$os", "$os_version", "$device_type", "$device", "$device_model",
                 "$screen_width", "$screen_height", "$viewport_width", "$viewport_height", "$browser_language",
                 "$browser_language_prefix", "$geoip_country_code", "$geoip_country_name", "$geoip_city_name",
                 "$geoip_continent_code", "$geoip_continent_name", "$geoip_subdivision_1_name",
                 "$geoip_subdivision_1_code", "$geoip_postal_code", "$geoip_latitude", "$geoip_longitude",
                 "$geoip_time_zone", "$geoip_accuracy_radius", "$lib", "$lib_version", "$timezone",
                 "$timezone_offset", "$device_manufacturer", "$app_name", "$app_version", "$app_build",
                 "$app_namespace", "$locale", "$network_wifi", "$network_carrier"}
CORE_WEB_CONTEXT = ["$browser", "$browser_version", "$os", "$os_version", "$device_type", "$screen_width",
                    "$screen_height", "$viewport_width", "$viewport_height", "$browser_language", "$lib",
                    "$lib_version", "$geoip_country_code", "$geoip_country_name", "$geoip_city_name",
                    "$geoip_subdivision_1_name", "$geoip_continent_name", "$geoip_time_zone", "$timezone"]
CORE_MOBILE_CONTEXT = ["$os", "$os_version", "$device_type", "$device_model", "$device_manufacturer",
                       "$app_name", "$app_version", "$app_build", "$app_namespace", "$lib", "$lib_version",
                       "$screen_width", "$screen_height", "$locale", "$timezone", "$network_wifi",
                       "$geoip_country_code", "$geoip_country_name", "$geoip_city_name"]
SERVER_CONTEXT = ["$lib", "$lib_version", "$geoip_disable"]
VIRTUAL_PREFIXES = ("$virt_",)
# session-level properties PostHog computes per session (round 3: $entry_utm_term stamped on custom events)
SESSION_LEVEL = ("$entry_", "$session_entry_", "$exit_", "$end_")
FAILED_SOURCES = {"sql_failed"}  # a property only seen in failed SQL is not evidence that events carry it
# typical per-active-user-day multiplicity for standard events without anchors
STD_PER_DAU = {"$pageview": 4.0, "$autocapture": 9.0, "$pageleave": 2.5, "$web_vitals": 2.0, "$identify": 1.0,
               "$feature_flag_called": 3.0, "$exception": 1.5, "$rageclick": 1.2, "$dead_click": 1.3,
               "$screen": 5.0, "$set": 1.0, "$groupidentify": 1.0, "$ai_generation": 4.0, "$ai_span": 6.0,
               "$ai_trace": 1.5, "$ai_embedding": 3.0}
STD_DAU_FRAC = {"$pageview": 0.95, "$autocapture": 0.8, "$pageleave": 0.7, "$web_vitals": 0.6, "$identify": 0.05,
                "$feature_flag_called": 0.6, "$exception": 0.04, "$rageclick": 0.03, "$dead_click": 0.04,
                "$screen": 0.9, "$set": 0.08, "$groupidentify": 0.1, "$ai_generation": 0.2, "$ai_span": 0.15,
                "$ai_trace": 0.2, "$ai_embedding": 0.05, "$feature_flag_called_v2": 0.5}


def stable_seed(*parts):
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:15], 16)


def uuid7(ms, rnd):
    r = rnd.getrandbits(74)
    v = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | (r >> 62) << 64 | 0b10 << 62 | (r & ((1 << 62) - 1))
    return str(uuid.UUID(int=v))


def iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def wchoice(rnd, items):
    """items: [(value, weight, ...)]"""
    tot = sum(x[1] for x in items)
    x = rnd.random() * tot
    for it in items:
        x -= it[1]
        if x <= 0:
            return it
    return items[-1]


class Project:
    def __init__(self, spec, seed=0, now=None, max_events=5_000_000, history_days=None, pre_days=120):
        global PRI
        if PRI is None:
            PRI = load_priors()
        self.t0 = time.time()
        self.S = spec
        self.seed = seed
        self.rnd = random.Random(stable_seed(spec["id"], seed))
        self.np = np.random.default_rng(stable_seed(spec["id"], seed, "np"))
        self.max_events = max_events
        self.notes = Counter()
        default_now = dt.datetime.fromtimestamp(PRI["project"]["default_now_utc_epoch"], UTC)
        self.now = now or spec["now_utc"] or default_now
        self.now = self.now.replace(second=0, microsecond=0)
        self.tzname = spec["tz"]
        self.tz = ZoneInfo(self.tzname)
        self.history_override = history_days
        self.pre_days = pre_days
        self.company = self.rnd.choice(catalog.COMPANY_WORDS) + self.rnd.choice(["", "hq", "app", "labs", "ly"])

    # ------------------------------------------------------------------ planning
    def plan(self):
        S, rnd = self.S, self.rnd
        ev = S["events"]
        self.active = {n: e for n, e in ev.items() if e["not_seen_days"] is None}
        self.inactive = {n: e for n, e in ev.items() if e["not_seen_days"] is not None}
        self.invented = []
        all_names = set(ev)
        has_tax_list = any("taxonomy_list" in e["sources"] for e in ev.values())
        dollar_vals = self._all_prop_values()
        libs = " ".join(dollar_vals.get("$lib", [])).lower()
        self.mobile = ("$screen" in self.active and "$pageview" not in self.active) or (
            ("ios" in libs or "android" in libs or "react-native" in libs or "flutter" in libs) and "web" not in libs)
        self.web = not self.mobile or "$pageview" in self.active
        if not self.active:
            base = ["$screen", "$identify", "$exception"] if self.mobile else \
                ["$pageview", "$pageleave", "$autocapture", "$identify", "$web_vitals", "$rageclick", "$exception"]
            for n in base:
                self.active[n] = self._blank_event(n, True)
                self.invented.append(n)
            if not any(not e["standard"] for e in ev.values()):
                gen = PRI["project"]["generic_custom_events"]
                names = sorted(gen, key=lambda k: -gen[k]["n_specs"])
                k = rnd.randint(3, 8)
                picks = set()
                while names and len(picks) < min(k, len(names)):
                    picks.add(rnd.choices(names, [gen[n]["n_specs"] for n in names])[0])
                for n in sorted(picks):
                    self.active[n] = self._blank_event(n, False)
                    self.invented.append(n)
        elif not has_tax_list and self.web and "$pageview" in self.active:
            for n in ["$pageleave", "$autocapture", "$identify"]:
                if n not in all_names:
                    self.active[n] = self._blank_event(n, True)
                    self.invented.append(n)
        if self.S["objects"].get("error_tracking_issues") and "$exception" not in self.active:
            self.active["$exception"] = self._blank_event("$exception", True)
            self.invented.append("$exception")
        if (S["group_types"] or S["group_indices"]) and "$groupidentify" not in ev:
            pass  # groups are attached to events; $groupidentify only when the spec lists it
        # ---- volumes
        hints = anchors.volume_hints(S)
        tot, dau, lb = {}, {}, {}
        for e, metric, val, src, lower in hints:
            if e not in self.active:
                continue
            if lower:
                lb[e] = max(lb.get(e, 0), val)
                continue
            if metric == "total":
                tot[e] = max(tot.get(e, 0), val)
            else:
                dau[e] = max(dau.get(e, 0), val)
        for e, v in lb.items():
            tot[e] = max(tot.get(e, 0), v * 1.2)
        self.hints = hints
        cand = [v for v in dau.values()] + [S["scale"].get("all_events_day_dau") or 0]
        for e, v in tot.items():
            per = STD_PER_DAU.get(e, 1.35) if e.startswith("$") else 1.35
            if e not in dau:
                cand.append(v / per / (STD_DAU_FRAC.get(e, 0.5) if e.startswith("$") else 0.5))
        D = max(cand) if cand else 0
        self.dau_source = "anchors" if D > 0 else "prior"
        if D <= 0:
            q = PRI["volume"]["project_dau_log10"]
            # inverse-CDF sample from the quantile table
            pts = sorted((float(k[1:]) / 100, v) for k, v in q.items() if k.startswith("p"))
            u = rnd.uniform(pts[0][0], pts[-1][0])
            for (p0, v0), (p1, v1) in zip(pts, pts[1:]):
                if p0 <= u <= p1:
                    D = 10 ** (v0 + (v1 - v0) * (u - p0) / max(1e-9, p1 - p0))
                    break
            D = min(max(D, 3.0), 20000)
        D = max(D, 1.0)
        # per-event targets for events without anchors
        pv_tot = tot.get("$pageview")
        if pv_tot is None and "$pageview" in self.active:
            pv_tot = D * STD_DAU_FRAC["$pageview"] * STD_PER_DAU["$pageview"] * math.exp(rnd.gauss(0, 0.3))
        anchored_custom = [v for e, v in tot.items() if not e.startswith("$")]
        cust_base = (sorted(anchored_custom)[len(anchored_custom) // 2] if anchored_custom else None)
        rel = PRI["volume"]["custom_rel_to_pageview"]
        self.targets = {}
        for e in self.active:
            T, U = tot.get(e), dau.get(e)
            if T is None and U is not None:
                per = STD_PER_DAU.get(e, 1.35) if e.startswith("$") else 1.35
                T = U * per
            if T is None:
                if e.startswith("$") or e in ("survey sent", "survey shown", "survey dismissed"):
                    r = PRI["volume"]["std_rel_to_pageview"].get(e, {}).get("p50")
                    if e == "$pageview":
                        T = pv_tot
                    elif r and pv_tot:
                        T = pv_tot * r * math.exp(rnd.gauss(0, 0.4))
                    else:
                        T = D * STD_DAU_FRAC.get(e, 0.1) * STD_PER_DAU.get(e, 1.5) * math.exp(rnd.gauss(0, 0.4))
                else:
                    if cust_base:
                        T = cust_base * math.exp(rnd.gauss(0, 1.0))
                    else:
                        base = pv_tot or D * 3.0
                        lo, hi = math.log(max(rel["p25"], 0.003)), math.log(max(rel["p90"], 0.05))
                        T = base * math.exp(rnd.uniform(lo, hi))
                        T = max(T, 0.05 * D)
            if U is None:
                per = STD_PER_DAU.get(e, 1.35) if e.startswith("$") else 1.35
                U = T / per
                if e.startswith("$") and e not in tot:
                    cap = STD_DAU_FRAC.get(e, 0.3) * D
                    if U > cap:
                        U = cap
                        T = min(T, cap * per * 1.5)
            U = min(U, D)
            T = max(T, U)
            self.targets[e] = [T, U]
        # ---- history and cap
        req = anchors.required_history_days(S)
        H = self.history_override or int(min(365, max(90, req if req >= 100 else 0)))
        daily = sum(t for t, _ in self.targets.values())
        self.volume_scale = 1.0
        if daily * H > self.max_events and not self.history_override:
            H = int(max(35, self.max_events / max(daily, 1e-9)))
        if daily * H > self.max_events:
            self.volume_scale = self.max_events / (daily * H) * 0.95
            for e in self.targets:
                self.targets[e] = [self.targets[e][0] * self.volume_scale, self.targets[e][1] * self.volume_scale]
            D *= self.volume_scale
        self.H = H
        self.D = max(D, 1.0)
        self.required_days = req

    def _blank_event(self, n, standard):
        return {"standard": standard, "description": None, "not_seen_days": None, "evidence": "invented",
                "sources": {}, "properties": {}, "volume": {}}

    def _all_prop_values(self):
        """prop -> list of spec values from any section (event props, unscoped, person, session)."""
        S = self.S
        out = defaultdict(list)
        secs = [e["properties"] for e in S["events"].values()] + [S["unscoped"], S["person_props"], S["session_props"]]
        secs += list(S["group_types"].values())
        for sec in secs:
            for pn, p in sec.items():
                out[pn].extend(p["values"])
        return out

    # ------------------------------------------------------------------ context: pages, profiles
    def build_pages(self):
        vals = self._all_prop_values()
        urls = []
        for k in ("$current_url", "$initial_current_url", "$entry_current_url", "$session_entry_url"):
            urls += [u for u in vals.get(k, []) if isinstance(u, str) and u.startswith("http")]
        hosts_extra = []
        hosts = [h for h in vals.get("$host", []) + vals.get("$initial_host", []) + vals.get("$entry_hostname", [])
                 if h and "/" not in h]
        paths = []
        for k in ("$pathname", "$prev_pageview_pathname", "$initial_pathname", "$entry_pathname", "$exit_pathname"):
            paths += [p for p in vals.get(k, []) if isinstance(p, str) and p.startswith("/")]
        # agent filter literals (often icontains fragments): turn into concrete pages that contain them
        for k in ("$pathname", "$current_url"):
            for v in vals.get(k, []):
                if not isinstance(v, str) or not v or v.startswith("http") or v.startswith("/"):
                    continue
                if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", v, re.I) and k == "$current_url":
                    hosts_extra.append(v)
                elif " " not in v and len(v) < 120:
                    paths.append("/" + v.lstrip("/"))
        pages = []
        seen = set()
        for u in urls:
            try:
                pu = urlparse(u)
            except Exception:
                continue
            if pu.netloc and u not in seen:
                seen.add(u)
                pages.append((u, pu.netloc, pu.path or "/"))
        hosts += hosts_extra
        if not hosts:
            hosts = sorted(set(p[1] for p in pages)) or [f"{self.rnd.choice(['app', 'www'])}.{self.company}.com"]
        self.hosts = list(dict.fromkeys(hosts))
        if not paths and not pages:
            paths = list(catalog.DEFAULT_PATHS)
        for p in dict.fromkeys(paths):
            u = f"https://{self.hosts[0]}{p}"
            if u not in seen:
                seen.add(u)
                pages.append((u, self.hosts[0], p))
        # spread extra hosts over pages
        if len(self.hosts) > 1:
            extra = []
            for i, h in enumerate(self.hosts[1:]):
                for p in list(dict.fromkeys(paths))[:20] or ["/"]:
                    u = f"https://{h}{p}"
                    if u not in seen:
                        seen.add(u)
                        extra.append((u, h, p))
            pages += extra
        self.pages = pages
        self.page_pending = list(range(len(pages))) if (urls or paths) else []
        self.page_p_force = 0.05
        w = [1.0 / (i + 1) ** 0.8 for i in range(len(pages))]
        acc, self.page_cum = 0.0, []
        for x in w:
            acc += x
            self.page_cum.append(acc)
        # referrers
        refs = [r for r in vals.get("$referrer", []) if r]
        self.referrers = [(r, 1.0) for r in refs[:30]] or list(catalog.REFERRERS)
        self.ref_pending = list(dict.fromkeys(refs[:30]))
        utm = {k: [v for v in vals.get(k, []) + vals.get("$initial_" + k, []) if v] for k in
               ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")}
        self.utm_vals = utm
        emails = [e for e in vals.get("email", []) + vals.get("$email", []) if isinstance(e, str) and "@" in e]
        # r21: anonymized domains (example.com, example-3.com) are placeholders, not the customer's user domains
        doms = Counter(e.split("@")[-1].lower() for e in emails
                       if not re.fullmatch(r"example(-\d+)?\.(com|org|net)", e.split("@")[-1].lower()))
        self.email_domains = [(d, c) for d, c in doms.most_common(20)] or \
            [(d if d != "company" else f"{self.company}.com", w) for d, w in catalog.EMAIL_DOMAINS]

    def page(self):
        if self.page_pending and self.rnd.random() < self.page_p_force:
            return self.pages[self.page_pending.pop(self.rnd.randrange(len(self.page_pending)))]
        x = self.rnd.random() * self.page_cum[-1]
        return self.pages[min(len(self.pages) - 1, bisect.bisect_left(self.page_cum, x))]

    def build_context_props(self):
        """Decide which $ props ride on every event (per-person context)."""
        S = self.S
        spec_pv = set(S["events"].get("$pageview", {}).get("properties", {}).keys())
        if self.mobile and not self.web:
            ctx = list(CORE_MOBILE_CONTEXT)
        else:
            ctx = list(CORE_WEB_CONTEXT)
            pri = PRI["std_event_props"].get("$pageview", {}).get("properties", {})
            if spec_pv:
                ctx += [p for p in spec_pv if p.startswith("$")]
            else:
                ctx += [p for p, d in pri.items() if d["frac"] >= 0.6]
        ctx = [p for p in dict.fromkeys(ctx) if p not in PAGE_PROPS and not p.startswith(VIRTUAL_PREFIXES)
               and not p.startswith("$prev_pageview")]
        self.context_props = ctx
        # samplers for context props that the builtin profile does not cover
        vals = self._all_prop_values()
        self.ctx_samplers = {}
        anyp = PRI["dollar_props_any"]
        for p in ctx:
            sv = [v for v in vals.get(p, []) if v != ""]
            prior = anyp.get(p) or PRI["std_event_props"].get("$pageview", {}).get("properties", {}).get(p)
            if sv or p not in PROFILE_PROPS:
                typ = None
                for sec in [e["properties"] for e in S["events"].values()] + [S["unscoped"]]:
                    if p in sec and sec[p]["type"]:
                        typ = sec[p]["type"]
                        break
                self.ctx_samplers[p] = Sampler(p, typ, sv, None, prior, None, random.Random(stable_seed(self.S["id"], p)),
                                               self)

    def make_profile(self, rnd):
        if self.mobile and not self.web:
            dtp = wchoice(rnd, [("Mobile", 0.9), ("Tablet", 0.1)])[0]
        else:
            dtp = wchoice(rnd, catalog.DEVICE_TYPES)[0]
        os_, _, osv = wchoice(rnd, catalog.OS_BY_DEVICE[dtp])
        if dtp == "Desktop":
            br = wchoice(rnd, [b for b in catalog.BROWSERS if b[0] not in ("Mobile Safari", "Chrome iOS", "Samsung Internet",
                                                                             "Facebook Mobile", "Android Mobile")])
        elif os_ == "iOS":
            br = wchoice(rnd, [b for b in catalog.BROWSERS if b[0] in ("Mobile Safari", "Chrome iOS", "Facebook Mobile")])
        else:
            br = wchoice(rnd, [b for b in catalog.BROWSERS if b[0] in ("Chrome", "Samsung Internet", "Android Mobile")])
        bv = f"{rnd.randint(*br[2])}.0"
        sw, sh = rnd.choice(catalog.SCREENS[dtp])
        tilt = catalog.TZ_COUNTRY_TILT.get(self.tzname)
        countries = [(c[0], c[4] * (6 if c[0] == tilt else 1), c) for c in catalog.COUNTRIES]
        cc = wchoice(rnd, countries)[2]
        city = rnd.choice(cc[5])
        lang = wchoice(rnd, catalog.LANGS)[0]
        if self.mobile and not self.web:
            lib, _, lv = wchoice(rnd, [l for l in catalog.MOBILE_LIBS if ("ios" in l[0]) == (os_ == "iOS") or "react" in l[0]])
        else:
            lib, lv = "web", "1.2" + str(rnd.randint(10, 99))
        ua = (f"Mozilla/5.0 ({'Macintosh; Intel Mac OS X 10_15_7' if os_ == 'Mac OS X' else 'Windows NT 10.0; Win64; x64' if os_ == 'Windows' else 'iPhone; CPU iPhone OS 18_1 like Mac OS X' if os_ == 'iOS' else 'Linux; Android 14' if os_ == 'Android' else 'X11; Linux x86_64'}) "
              f"AppleWebKit/537.36 (KHTML, like Gecko) {br[0].split()[0]}/{bv} Safari/537.36")
        p = {"$browser": br[0], "$browser_version": float(bv), "$os": os_, "$os_version": osv, "$device_type": dtp,
             "$screen_width": sw, "$screen_height": sh, "$viewport_width": sw - rnd.choice([0, 0, 15, 120]),
             "$viewport_height": sh - rnd.choice([80, 120, 160]), "$browser_language": lang,
             "$browser_language_prefix": lang.split("-")[0], "$geoip_country_code": cc[0], "$geoip_country_name": cc[1],
             "$geoip_continent_code": cc[2], "$geoip_continent_name": cc[3], "$geoip_city_name": city[0],
             "$geoip_subdivision_1_name": city[1], "$geoip_subdivision_1_code": city[2], "$geoip_postal_code": city[3],
             "$geoip_latitude": round(city[4] + rnd.uniform(-0.05, 0.05), 4),
             "$geoip_longitude": round(city[5] + rnd.uniform(-0.05, 0.05), 4), "$geoip_time_zone": city[6],
             "$geoip_accuracy_radius": rnd.choice([5, 10, 20, 50, 100]), "$timezone": city[6],
             "$timezone_offset": 0, "$lib": lib, "$lib_version": lv, "$raw_user_agent": ua}
        if dtp != "Desktop":
            # r22: the model follows the OS (round 5: Android events with manufacturer "iPhone")
            model = rnd.choice([m for m in catalog.DEVICES_MOBILE if m.startswith("iPhone") == (os_ == "iOS")]
                               or catalog.DEVICES_MOBILE)
            p["$device"] = "iPhone" if os_ == "iOS" else "Android"
            p["$device_model"] = model
            p["$device_manufacturer"] = "Apple" if os_ == "iOS" else model.split()[0]
        if lib != "web":  # r31: app metadata only on native-app profiles (v4 pilot: every web person had $app_*)
            p["$app_name"] = self.company.title()
            p["$app_version"] = f"{rnd.randint(1, 4)}.{rnd.randint(0, 20)}.{rnd.randint(0, 9)}"
            p["$app_build"] = str(rnd.randint(100, 900))
            p["$app_namespace"] = f"com.{self.company}.app"
        p["$locale"] = lang
        p["$network_wifi"] = rnd.random() < 0.7
        return p

    # ------------------------------------------------------------------ persons and activity
    def simulate_activity(self):
        npr = self.np
        H, P = self.H, self.pre_days
        T = H + P
        day = PRI["funnel_retention"]["retention"].get("day", {})
        curve = [day[str(i)]["mean"] if str(i) in day else None for i in range(13)]
        curve = [c for c in curve if c is not None] or [1, 0.2, 0.15, 0.12, 0.11, 0.1, 0.1]
        r = np.zeros(T + 1)
        for k in range(T + 1):
            r[k] = curve[k] if k < len(curve) else max(0.01, curve[-1] * (k / (len(curve) - 1)) ** -0.6)
        stick = float(np.exp(npr.normal(0, 0.35)))
        r[1:] = np.minimum(1.0, r[1:] * stick)
        self.retention_curve = r
        weekend = float(npr.uniform(0.55, 1.0))
        # local calendar for each day index (0 = first pre-window day)
        start_local = (self.now.astimezone(self.tz).date() - dt.timedelta(days=T - 1))
        self.day_dates = [start_local + dt.timedelta(days=i) for i in range(T)]
        w = np.array([weekend if d.weekday() >= 5 else 1.0 for d in self.day_dates])
        g = float(npr.uniform(-0.001, 0.006))
        lam_shape = np.exp(g * (np.arange(T) - T))
        sig = 0.8
        bs = np.exp(npr.normal(-sig * sig / 2, sig, 4000))
        rbar = np.array([1.0] + [float(np.minimum(1.0, bs * r[k]).mean()) for k in range(1, T + 1)])
        exp_dau = np.convolve(lam_shape, rbar[:T])[:T] * np.where(np.arange(T) >= 0, 1, 1)
        exp_dau = exp_dau * np.maximum(w, 0)  # approx (day-0 activity also weighted)
        last = exp_dau[-30:].mean() if T >= 30 else exp_dau.mean()
        lam = lam_shape * (self.D / max(last, 1e-9))
        n_new = npr.poisson(lam)
        n_persons = int(n_new.sum())
        f = np.repeat(np.arange(T), n_new)
        b = np.exp(npr.normal(-sig * sig / 2, sig, n_persons))
        ud_p, ud_d = [], []
        B = 50000
        for s in range(0, n_persons, B):
            fi, bi = f[s:s + B], b[s:s + B]
            days = np.arange(P, T)
            age = days[None, :] - fi[:, None]
            prob = np.where(age >= 0, np.minimum(1.0, bi[:, None] * r[np.clip(age, 0, T)]) * w[None, days], 0.0)
            prob = np.where(age == 0, 1.0, prob)
            act = npr.random(prob.shape) < prob
            pi, di = np.nonzero(act)
            ud_p.append(pi + s)
            ud_d.append(days[di])
        ud_p = np.concatenate(ud_p) if ud_p else np.zeros(0, int)
        ud_d = np.concatenate(ud_d) if ud_d else np.zeros(0, int)
        # keep only persons active in window, re-index
        keep = np.unique(ud_p)
        remap = -np.ones(max(n_persons, 1), dtype=np.int64)
        remap[keep] = np.arange(len(keep))
        self.p_first_day = f[keep]
        self.n_persons = len(keep)
        order = np.lexsort((ud_p, ud_d))
        self.ud_p = remap[ud_p[order]]
        self.ud_d = ud_d[order] - P  # 0..H-1 window day index
        self.day_dates = self.day_dates[P:]
        self.p_first_window_day = np.full(self.n_persons, H, dtype=np.int64)
        np.minimum.at(self.p_first_window_day, self.ud_p, self.ud_d)
        last30 = self.ud_d >= H - 30
        self.realized_dau = float(last30.sum() / min(30, H))
        self.notes["weekend_factor_x100"] = int(weekend * 100)

    def build_persons(self):
        rnd = self.rnd
        n = self.n_persons
        S = self.S
        style = rnd.choice(["uuid", "int", "email", "prefixed"])
        has_identify = "$identify" in self.active
        p_ident = rnd.uniform(0.35, 0.85)
        self.persons = []
        P = self.pre_days
        first_dates = self.day_dates_full_start = self.now.astimezone(self.tz).date() - dt.timedelta(days=self.H + P - 1)
        for i in range(n):
            pr = random.Random(stable_seed(S["id"], self.seed, "p", i))
            prof = self.make_profile(pr)
            fn, ln = pr.choice(catalog.FIRST_NAMES), pr.choice(catalog.LAST_NAMES)
            dom = wchoice(pr, self.email_domains)[0]
            email = f"{fn.lower()}.{ln.lower()}{pr.randint(1, 999)}@{dom}".replace("ü", "u")
            ident = pr.random() < p_ident or not has_identify
            uid = {"uuid": lambda: str(uuid.UUID(int=pr.getrandbits(128), version=4)),
                   "int": lambda: str(100000 + i * 7 + pr.randint(0, 6)), "email": lambda: email,
                   "prefixed": lambda: f"user_{pr.getrandbits(64):016x}"}[style]()
            fday = first_dates + dt.timedelta(days=int(self.p_first_day[i]))
            created = dt.datetime.combine(fday, dt.time(pr.randint(0, 23), pr.randint(0, 59)), self.tz).astimezone(UTC)
            pid = str(uuid.UUID(int=pr.getrandbits(128), version=4))
            anon = uuid7(int(created.timestamp() * 1000), pr)
            self.persons.append({"id": pid, "anon_id": anon, "user_id": uid if ident else anon, "email": email if ident else None,
                                 "name": f"{fn} {ln}", "identified": ident, "profile": prof, "created_at": created,
                                 "rnd": pr, "plan": wchoice(pr, catalog.PLANS)[0]})

    def person_properties(self):
        """Fill person property dicts (spec props first, then priors), as JSON strings."""
        S, rnd = self.S, self.rnd
        spec_pp = dict(S["person_props"])
        if not spec_pp:
            pri = PRI["person_props"]["properties"]
            spec_pp = {p: {"type": d["type"], "values": [], "more_values": None, "description": None,
                           "standard": True, "values_status": None, "sources": {}}
                       for p, d in pri.items() if p.startswith("$") and d["frac"] >= 0.6}
            spec_pp["email"] = {"type": "String", "values": [], "more_values": None, "description": None,
                                "standard": False, "values_status": None, "sources": {}}
            spec_pp["name"] = dict(spec_pp["email"])
        self.person_prop_specs = spec_pp
        samplers = {}
        pri_pp = PRI["person_props"]["properties"]
        for p, d in spec_pp.items():
            if p.startswith(VIRTUAL_PREFIXES):
                continue
            samplers[p] = Sampler(p, d["type"], d["values"], d["more_values"], pri_pp.get(p),
                                  PRI["name_shape_priors"].get("person:" + shape_of(p)),
                                  random.Random(stable_seed(S["id"], "pp", p)), self)
        self.person_samplers = samplers
        for smp in samplers.values():
            smp.plan(max(1, int(self.n_persons * 0.6)))
        out = []
        for per in self.persons:
            prof = per["profile"]
            props = {}
            init_page = self.page()
            ref = wchoice(per["rnd"], self.referrers)[0]
            for p, smp in samplers.items():
                base = p[len("$initial_"):] if p.startswith("$initial_") else p.lstrip("$")
                key = "$" + base
                lp = p.lower()
                if key in prof and (p.startswith("$") or p.startswith("$initial_")) and smp.source != "spec":
                    v = prof[key]
                elif p in ("$initial_current_url", "$current_url"):
                    v = init_page[0]
                elif p in ("$initial_pathname", "$pathname"):
                    v = init_page[2]
                elif p in ("$initial_host", "$host"):
                    v = init_page[1]
                elif p in ("$initial_referrer", "$referrer"):
                    v = ref
                elif p in ("$initial_referring_domain", "$referring_domain"):
                    v = "$direct" if ref == "$direct" else (urlparse(ref).netloc or ref)
                elif lp in ("email", "$email", "user_email", "email_address"):
                    v = per["email"]
                    if v is None:
                        continue
                elif lp in ("name", "$name", "full_name", "display_name", "username"):
                    if not per["identified"]:
                        continue
                    v = per["name"] if "user" not in lp else per["name"].split()[0].lower() + str(per["rnd"].randint(1, 99))
                elif lp in ("first_name", "firstname"):
                    v = per["name"].split()[0]
                elif lp in ("last_name", "lastname"):
                    v = per["name"].split()[1]
                elif shape_of(p) == "datetime" and smp.source != "spec":
                    v = iso(per["created_at"] + dt.timedelta(minutes=per["rnd"].randint(0, 600)))
                elif lp in ("plan", "plan_name", "subscription_plan", "tier") and smp.source != "spec":
                    v = per["plan"]
                elif lp in ("user_id", "userid", "external_id", "$user_id", "distinct_id"):
                    v = per["user_id"]
                elif p.startswith("$initial_utm") or p.startswith("$initial_") and p[9:] in ("gclid", "fbclid", "gad_source", "msclkid"):
                    if per["rnd"].random() < 0.75:
                        continue
                    v = smp({"ts": per["created_at"], "person": per})
                else:
                    if not per["identified"] and not p.startswith("$") and per["rnd"].random() < 0.7:
                        continue
                    v = smp({"ts": per["created_at"], "person": per})
                if v is None:
                    continue
                props[p] = v
            per["props"] = props
            out.append(orjson.dumps(props).decode())
        self.person_props_json = out

    # ------------------------------------------------------------------ groups
    def build_groups(self):
        S, rnd = self.S, self.rnd
        self.group_types = []  # [(index, name, props_spec)]
        if not (S["group_types"] or S["group_indices"] or "$groupidentify" in self.active):
            return
        used_idx = set()
        named = []
        for key, props in S["group_types"].items():
            nm = key.split(":", 1)[-1]
            if re.fullmatch(r"\d+", nm):
                used_idx.add(int(nm))
                named.append((int(nm), None, props))
            else:
                named.append((None, nm, props))
        for x in S["group_indices"]:
            if re.fullmatch(r"\d+", x):
                used_idx.add(int(x))
        free_names = [n for n in catalog.GROUP_TYPE_NAMES if n not in {nm for _, nm, _ in named if nm}]
        types = {}
        nxt = 0
        for idx, nm, props in named:
            if idx is None:
                while nxt in types:
                    nxt += 1
                idx = nxt
            if nm is None:
                nm = free_names.pop(0) if free_names else f"group_{idx}"
            types[idx] = (nm, props)
        for idx in sorted(used_idx):
            if idx not in types:
                types[idx] = (free_names.pop(0) if free_names else f"group_{idx}", {})
        if not types:
            types[0] = ("organization", {})
        self.group_types = [(i, types[i][0], types[i][1]) for i in sorted(types) if i <= 4]
        # groups per type and membership
        self.groups = {}
        self.person_groups = [dict() for _ in range(self.n_persons)]
        gp_pri = PRI["group_props"]
        for idx, name, props in self.group_types:
            n_g = max(1, int(self.n_persons / rnd.uniform(3, 12)))
            keys = []
            for j in range(n_g):
                keys.append(f"{name[:3]}_{stable_seed(S['id'], idx, j) % 10**10:010d}" if rnd.random() < 0.5 or True else str(j))
            samplers = {}
            for p, d in (props or {}).items():
                samplers[p] = Sampler(p, d["type"], d["values"], d["more_values"], gp_pri.get(p), None,
                                      random.Random(stable_seed(S["id"], "g", idx, p)), self)
            if "name" not in samplers:
                samplers["name"] = None
            rows = []
            for j, k in enumerate(keys):
                gpr = random.Random(stable_seed(S["id"], "gr", idx, j))
                gprops = {}
                for p, smp in samplers.items():
                    if smp is None:
                        gprops[p] = f"{gpr.choice(catalog.COMPANY_WORDS).title()} {gpr.choice(['Inc', 'Labs', 'Co', 'GmbH', 'Ltd', 'Group'])}"
                    else:
                        v = smp({"ts": self.now, "person": self.persons[0] if self.persons else {}})
                        if v is not None:
                            gprops[p] = v
                created = self.now - dt.timedelta(days=gpr.randint(1, self.H + self.pre_days))
                rows.append({"key": k, "props": gprops, "created_at": created})
            self.groups[idx] = rows
            w = np.array([1.0 / (j + 1) ** 0.7 for j in range(n_g)])
            assign = self.np.choice(n_g, size=self.n_persons, p=w / w.sum()) if self.n_persons else []
            for pi, gj in enumerate(assign):
                self.person_groups[pi][name] = keys[gj]

    # ------------------------------------------------------------------ event-level samplers
    def build_event_samplers(self):
        S, rnd = self.S, self.rnd
        std_pri = PRI["std_event_props"]
        common = PRI["custom_props_common"]["properties"]
        common_names = sorted(common, key=lambda k: -common[k]["n_projects"])
        unscoped = {p: d for p, d in S["unscoped"].items() if not p.startswith(VIRTUAL_PREFIXES + SESSION_LEVEL)
                    and not (d.get("sources") and set(d["sources"]) <= FAILED_SOURCES)}
        custom_events = [e for e in self.active if not self.active[e]["standard"]]
        top_custom = sorted(custom_events, key=lambda e: -self.targets[e][0])[:5]
        ctxset = set(self.context_props)
        self.ev_samplers = {}
        self.server_events = set()
        dollar_any = PRI["dollar_props_any"]
        # unscoped props that no custom event picks up go to the busiest event
        attached_unscoped = set()
        for e in custom_events:
            etoks = set(re.split(r"[^a-z0-9]+", e.lower()))
            for p in unscoped:
                ptoks = set(re.split(r"[^a-z0-9]+", p.lower().lstrip("$"))) - {"id", "at", "type", "name", ""}
                if ptoks & etoks:  # r20: name evidence only (not "every top-5 custom event")
                    attached_unscoped.add(p)
        fallback_event = max(self.active, key=lambda x: self.targets[x][0]) if self.active else None
        for e, info in list(self.active.items()) + [(n, i) for n, i in self.inactive.items()]:
            props = {}
            for p, d in info["properties"].items():
                if p in ctxset or (p in PAGE_PROPS and p.startswith("$")) or p.startswith(VIRTUAL_PREFIXES):
                    continue
                props[p] = d
            if info["properties"] and not info["standard"]:
                if not any(p in ctxset or p in PAGE_PROPS for p in info["properties"]) and \
                        any("taxonomy_props" in d["sources"] for d in info["properties"].values()):
                    self.server_events.add(e)
            if e.startswith("$") and e in std_pri:
                for p, d in std_pri[e]["properties"].items():
                    if d["frac"] >= 0.5 and p not in props and p not in ctxset and p not in PAGE_PROPS \
                            and not p.startswith(VIRTUAL_PREFIXES):
                        props[p] = {"type": d["type"], "values": [], "more_values": None, "description": None,
                                    "standard": True, "values_status": None, "sources": {}}
            if not info["standard"]:
                # unscoped props: attach to top custom events and to events sharing a name token
                etoks = set(re.split(r"[^a-z0-9]+", e.lower()))
                for p, d in unscoped.items():
                    ptoks = set(re.split(r"[^a-z0-9]+", p.lower().lstrip("$"))) - {"id", "at", "type", "name", ""}
                    if p in props or p in ctxset or p in PAGE_PROPS:
                        continue
                    if ptoks & etoks:
                        props[p] = d
                # r20: no "common props" filler for events without listed properties (round 4: 0-3 random names from
                # other projects, e.g. 'method' = POST/GET/google, on 1,527 event/prop pairs in 28 of 40 twins)
            if e == fallback_event:
                for p, d in unscoped.items():
                    if p not in props and p not in ctxset and p not in PAGE_PROPS and p not in attached_unscoped \
                            and self.unscoped_evidenced(p):
                        props[p] = d
            samplers = {}
            for p, d in props.items():
                prior = common.get(p) or dollar_any.get(p) or (std_pri.get(e, {}).get("properties", {}).get(p))
                samplers[p] = Sampler(p, d["type"], d["values"], d["more_values"], prior,
                                      PRI["name_shape_priors"].get(shape_of(p)),
                                      random.Random(stable_seed(S["id"], "ep", e, p)), self)
            self.ev_samplers[e] = samplers

    def unscoped_evidenced(self, prop: str) -> bool:
        """Whether an unscoped property is used by this conversation (Project2 overrides; base: always)."""
        return True

    # ------------------------------------------------------------------ objects needed while generating events
    def prepare_special(self):
        S, rnd = self.S, self.rnd
        objs = S["objects"]
        vals = self._all_prop_values()
        flags = [k for k, o in (objs.get("feature_flags") or {}).items() if not self._created(o)]
        flag_keys = [v for v in vals.get("$feature_flag", []) if v] or flags
        if not flag_keys and "$feature_flag_called" in self.active:
            flag_keys = ["new-onboarding", "beta-dashboard", "pricing-test"]
        self.flag_variants = {}
        for k, o in (objs.get("feature_flags") or {}).items():
            vs = [v.get("key") for v in o.get("variants") or [] if v.get("key")]
            self.flag_variants[k] = vs
        for k, o in (objs.get("experiments") or {}).items():
            fk = o.get("feature_flag_key")
            if fk and fk not in self.flag_variants:
                self.flag_variants[fk] = [v.get("key") for v in o.get("variants") or [] if v.get("key")] or ["control", "test"]
                if fk not in flag_keys:
                    flag_keys.append(fk)
        self.flag_keys = flag_keys
        self.issues = []
        for k, o in (objs.get("error_tracking_issues") or {}).items():
            title = o.get("title") or "Error"
            et = (o.get("exception_types") or [None])[0] or (title.split(":")[0] if ":" in title else "Error")
            msg = title.split(":", 1)[1].strip() if ":" in title else title
            self.issues.append({"id": o.get("id") or k, "type": et, "message": msg,
                                "w": max(1.0, float(num(o.get("occurrences")) or 1))})
        if not self.issues:
            for et, msg, w in catalog.EXCEPTION_TYPES:
                self.issues.append({"id": str(uuid.UUID(int=rnd.getrandbits(128), version=4)), "type": et,
                                    "message": msg, "w": w, "invented": True})
        self.surveys = [(k, o.get("name") or "Survey") for k, o in (objs.get("surveys") or {}).items()
                        if not self._created(o)]
        if "$exception" in self.active and not anchors_has(self.hints, "$exception") and \
                any(not i.get("invented") for i in self.issues):
            occ = sum(i["w"] for i in self.issues if not i.get("invented"))
            t = max(self.targets["$exception"][0], occ / 30.0 * self.volume_scale)
            self.targets["$exception"] = [t, max(self.targets["$exception"][1], min(self.D, t / 3))]

    @staticmethod
    def _created(o):
        return bool(o.get("created_in_conversation")) or o.get("first_source") in ("created_by_agent", "upsert_dashboard")

    # ------------------------------------------------------------------ event occurrence plan
    def plan_occurrences(self):
        npr = self.np
        H, D = self.H, max(self.realized_dau, 1e-6)
        names = list(self.active)
        # funnel order: anchor/insight funnels first, then by decreasing DAU
        order_hint = {}
        pos = 0
        funnels = []
        for a in self.S["anchors"]:
            if a.get("result_kind") == "FunnelsQuery":
                fr = anchors.funnel_from_anchor(a)
                if fr:
                    funnels.append(fr[0])
        for o in (self.S["objects"].get("insights") or {}).values():
            q = o.get("query") or {}
            if isinstance(q, dict) and q.get("kind") == "FunnelsQuery":
                funnels.append([s.get("event") for s in q.get("series") or []])
        rank = {}
        for i, e in enumerate(sorted(names, key=lambda e: -self.targets[e][1])):
            rank[e] = i / max(1, len(names))
        for steps in funnels:
            steps = [s for s in steps if s in self.active]
            for k, s in enumerate(steps):
                rank[s] = min(rank.get(s, 1), 0.05 + 0.9 * k / max(1, len(steps)))
        self.rank = rank
        # reach thresholds: nested on a latent u per person
        u = npr.random(self.n_persons)
        reach, pday, mult = {}, {}, {}
        for e in names:
            T, U = self.targets[e]
            q = min(1.0, U / D)
            rr = min(1.0, math.sqrt(q) * 1.05)
            reach[e], pday[e] = rr, min(1.0, q / max(rr, 1e-9))
            mult[e] = max(1.0, T / max(U, 1e-9))
        # funnel steps: keep reach non-increasing along each funnel
        for steps in funnels:
            steps = [s for s in steps if s in self.active]
            for a, b in zip(steps, steps[1:]):
                if reach[b] > reach[a]:
                    reach[b] = reach[a]
        self.reach = reach
        N_ud = len(self.ud_p)
        occ_ud, occ_ev = [], []
        ud_u = u[self.ud_p] if N_ud else np.zeros(0)
        for ei, e in enumerate(names):
            if e == "$identify":
                continue
            m = (ud_u < reach[e]) & (npr.random(N_ud) < pday[e])
            idx = np.nonzero(m)[0]
            extra = mult[e] - 1
            if extra > 0:
                lamb = npr.gamma(1.5, extra / 1.5, len(idx))
                cnt = 1 + npr.poisson(lamb)
            else:
                cnt = np.ones(len(idx), dtype=np.int64)
            occ_ud.append(np.repeat(idx, cnt))
            occ_ev.append(np.full(int(cnt.sum()), ei))
        if "$identify" in self.active:
            ei = names.index("$identify")
            # one $identify on each identified new person's first window day + re-identifications at the target rate
            ident = np.array([p["identified"] for p in self.persons], dtype=bool)
            first_day = self.p_first_window_day
            new_in_window = self.p_first_day >= self.pre_days
            first_ud = np.full(self.n_persons, -1, dtype=np.int64)
            # first ud index per person (ud sorted by day)
            rev = np.arange(N_ud)[::-1]
            first_ud[self.ud_p[rev]] = rev
            sel = np.nonzero(ident & new_in_window & (first_ud >= 0))[0]
            forced = first_ud[sel]
            T, U = self.targets["$identify"]
            rest = max(0.0, T * H - len(forced))
            pr = min(1.0, rest / max(1, N_ud))
            extra = np.nonzero(npr.random(N_ud) < pr * 0.5)[0]
            ids = np.concatenate([forced, extra])
            occ_ud.append(ids)
            occ_ev.append(np.full(len(ids), ei))
            self.identify_first_ud = set(forced.tolist())
        else:
            self.identify_first_ud = set()
        occ_ud = np.concatenate(occ_ud) if occ_ud else np.zeros(0, np.int64)
        occ_ev = np.concatenate(occ_ev) if occ_ev else np.zeros(0, np.int64)
        # every active event appears at least a few times
        present = np.bincount(occ_ev, minlength=len(names)) if len(occ_ev) else np.zeros(len(names), int)
        add_ud, add_ev = [], []
        for ei, e in enumerate(names):
            if present[ei] == 0 and N_ud:
                k = int(min(N_ud, npr.integers(1, 4)))
                add_ud.append(npr.choice(N_ud, size=k, replace=False))
                add_ev.append(np.full(k, ei))
                self.notes["events_forced_min"] += 1
        if add_ud:
            occ_ud = np.concatenate([occ_ud] + add_ud)
            occ_ev = np.concatenate([occ_ev] + add_ev)
        if len(occ_ud) > self.max_events:
            keep = np.sort(npr.choice(len(occ_ud), self.max_events, replace=False))
            occ_ud, occ_ev = occ_ud[keep], occ_ev[keep]
            self.notes["hard_capped"] += 1
        self.names = names
        self.occ_ud, self.occ_ev = occ_ud, occ_ev

    def schedule(self):
        """Assign sessions and timestamps to occurrences."""
        npr = self.np
        names = self.names
        occ_ud, occ_ev = self.occ_ud, self.occ_ev
        n = len(occ_ud)
        N_ud = len(self.ud_p)
        pv_idx = names.index("$pageview") if "$pageview" in names else (names.index("$screen") if "$screen" in names else -1)
        is_pv = occ_ev == pv_idx
        pv_per_ud = np.bincount(occ_ud[is_pv], minlength=N_ud) if n else np.zeros(N_ud, int)
        per_ud = np.bincount(occ_ud, minlength=N_ud) if n else np.zeros(N_ud, int)
        n_sess = 1 + npr.poisson(0.25 + per_ud / 30.0)
        n_sess = np.minimum(n_sess, np.maximum(1, np.where(pv_per_ud > 0, pv_per_ud, 1)))
        n_sess = np.minimum(n_sess, 6)
        sess = (npr.random(n) * n_sess[occ_ud]).astype(np.int64)
        # spread pageviews round-robin over sessions so each session starts with one
        if pv_idx >= 0 and n:
            pvi = np.nonzero(is_pv)[0]
            ordp = pvi[np.argsort(occ_ud[pvi], kind="stable")]
            uds = occ_ud[ordp]
            j = np.arange(len(ordp)) - np.searchsorted(uds, uds, side="left")
            sess[ordp] = j % n_sess[uds]
        # ordering key within session
        rank = np.array([self.rank[e] for e in names])
        key = rank[occ_ev] * 0.8 + npr.random(n) * 0.5
        if pv_idx >= 0:
            key = np.where(is_pv, npr.random(n) * 1.2 - 0.1, key)
        ident_i = names.index("$identify") if "$identify" in names else -2
        key = np.where(occ_ev == ident_i, 0.02, key)
        # session start seconds-of-day (local), diurnal profile
        hours = np.arange(24)
        prof = 0.25 + np.exp(-0.5 * ((hours - 14) / 4.0) ** 2) + 0.3 * np.exp(-0.5 * ((hours - 20) / 2.0) ** 2)
        prof = prof / prof.sum()
        n_sess_tot = int(n_sess.sum())
        sess_off = np.concatenate([[0], np.cumsum(n_sess)[:-1]])
        sh = npr.choice(24, size=n_sess_tot, p=prof)
        sstart = sh * 3600 + npr.integers(0, 3600, n_sess_tot)
        gsess = sess_off[occ_ud] + sess
        o = np.lexsort((key, gsess))
        gaps = np.exp(npr.normal(math.log(12), 1.2, n))
        gaps_sorted = gaps[o]
        gs = gsess[o]
        first = np.r_[True, gs[1:] != gs[:-1]]
        gaps_sorted[first] = 0.0
        c = np.cumsum(gaps_sorted)
        grp_start = np.maximum.accumulate(np.where(first, np.arange(n), 0))
        within = c - c[grp_start]
        sec = np.empty(n)
        sec[o] = sstart[gs] + within
        sec = np.minimum(sec, 86399.0)
        # local day -> UTC epoch
        day_epoch = np.array([dt.datetime.combine(d, dt.time(0), self.tz).timestamp() for d in self.day_dates])
        ts = day_epoch[self.ud_d[occ_ud]] + sec
        nowe = self.now.timestamp()
        ok = ts <= nowe - 1
        self.notes["dropped_future"] += int((~ok).sum())
        self.occ_ud, self.occ_ev, self.occ_ts, self.occ_sess = occ_ud[ok], occ_ev[ok], ts[ok], gsess[ok]
        self.sess_start = sstart

    # ------------------------------------------------------------------ write events
    def plan_coverage(self):
        cnt = np.bincount(self.occ_ev, minlength=len(self.names)) if len(self.occ_ev) else np.zeros(len(self.names), int)
        for ei, e in enumerate(self.names):
            for smp in self.ev_samplers.get(e, {}).values():
                smp.plan(int(cnt[ei]))
        for smp in self.ctx_samplers.values():
            smp.plan(self.n_persons)
        pv = sum(int(cnt[i]) for i, e in enumerate(self.names) if e in ("$pageview", "$screen"))
        n_calls = pv + len(np.unique(self.occ_sess))
        if self.page_pending:
            self.page_p_force = min(1.0, 3.0 * len(self.page_pending) / max(1, n_calls))

    def write_events(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        self.plan_coverage()
        names = self.names
        order = np.argsort(self.occ_ts, kind="stable")
        o_ud, o_ev, o_ts, o_ss = self.occ_ud[order], self.occ_ev[order], self.occ_ts[order], self.occ_sess[order]
        n = len(o_ud)
        # per person context fragment (JSON without braces)
        frags = []
        for per in self.persons:
            prof = per["profile"]
            d = {}
            pr = per["rnd"]
            for p in self.context_props:
                smp = self.ctx_samplers.get(p)
                if smp is not None and (p not in prof or pr.random() < 0.85):
                    v = smp({"ts": per["created_at"], "person": per})
                elif p in prof:
                    v = prof[p]
                else:
                    continue
                if v is not None:
                    d[p] = v
            frags.append(orjson.dumps(d).decode()[1:-1])
        server_frag = orjson.dumps({"$lib": "posthog-node", "$lib_version": "4.2.1", "$geoip_disable": False}).decode()[1:-1]
        group_names = {name: idx for idx, name, _ in self.group_types}
        schema = pa.schema([("uuid", pa.string()), ("event", pa.string()), ("properties", pa.string()),
                            ("timestamp", pa.timestamp("us", tz="UTC")), ("distinct_id", pa.string()),
                            ("person_id", pa.string()), ("$session_id", pa.string()), ("$window_id", pa.string()),
                            ("elements_chain", pa.string()),
                            ("person_properties", pa.dictionary(pa.int32(), pa.string())),
                            ("$group_0", pa.string()), ("$group_1", pa.string()), ("$group_2", pa.string()),
                            ("$group_3", pa.string()), ("$group_4", pa.string())])
        writer = pq.ParquetWriter(os.path.join(out_dir, "events.parquet"), schema, compression="zstd")
        pp_dict = pa.array(self.person_props_json, pa.string())
        sess_state = {}
        rnd = self.rnd
        ev_counts = Counter()
        prop_seen = defaultdict(Counter)   # event -> prop -> n
        prop_types = {}
        last_seen = {}
        dau_days = defaultdict(set)
        identified_at = {}
        trace_ids = {}
        CH = 100000
        chunk = defaultdict(list)
        pidx_list = []
        written = 0
        ident_i = names.index("$identify") if "$identify" in names else -2

        def flush():
            nonlocal chunk, pidx_list, written
            if not pidx_list:
                return
            cols = dict(chunk)
            cols["person_properties"] = pa.DictionaryArray.from_arrays(pa.array(pidx_list, pa.int32()), pp_dict)
            tbl = pa.table({f.name: (cols[f.name] if f.name == "person_properties" else pa.array(cols[f.name], f.type))
                            for f in schema}, schema=schema)
            writer.write_table(tbl, row_group_size=CH)
            written += len(pidx_list)
            chunk = defaultdict(list)
            pidx_list = []

        for i in range(n):
            ud = int(o_ud[i])
            pi = int(self.ud_p[ud])
            per = self.persons[pi]
            e = names[int(o_ev[i])]
            tsf = float(o_ts[i])
            ts = dt.datetime.fromtimestamp(tsf, UTC)
            gs = int(o_ss[i])
            st = sess_state.get(gs)
            if st is None:
                ms = int(tsf * 1000)
                if self.ref_pending and rnd.random() < 0.3:
                    ref = self.ref_pending.pop()
                else:
                    ref = wchoice(per["rnd"], self.referrers)[0]
                utm = None
                if per["rnd"].random() < 0.2:
                    src = per["rnd"].choice(self.utm_vals["utm_source"]) if self.utm_vals["utm_source"] else \
                        wchoice(per["rnd"], catalog.UTM_SOURCES)[0]
                    utm = {"utm_source": src,
                           "utm_medium": per["rnd"].choice(self.utm_vals["utm_medium"]) if self.utm_vals["utm_medium"]
                           else catalog.UTM_MEDIUMS.get(src, "referral"),
                           "utm_campaign": per["rnd"].choice(self.utm_vals["utm_campaign"]) if self.utm_vals["utm_campaign"]
                           else per["rnd"].choice(catalog.UTM_CAMPAIGNS)}
                st = sess_state[gs] = {"sid": uuid7(ms, rnd), "wid": uuid7(ms, rnd), "ref": ref, "utm": utm,
                                       "page": self.page(), "pv": 0, "pv_ts": tsf, "trace": None}
                if len(sess_state) > 200000:
                    sess_state.clear()
                    sess_state[gs] = st
            d = {}
            ctx = {"ts": ts, "person": per, "session_id": st["sid"], "pi": pi}
            # distinct id: anonymous until the person's first $identify
            if per["identified"]:
                ia = identified_at.get(pi)
                if ia is None and (ud not in self.identify_first_ud):
                    identified_at[pi] = ia = 0.0  # identified earlier / server-side
                if e == "$identify" and ia is None:
                    identified_at[pi] = ia = tsf
                did = per["user_id"] if (ia is not None and tsf >= ia) else per["anon_id"]
            else:
                did = per["anon_id"]
            server = e in self.server_events or e.startswith("$ai_")
            if not server and self.web:
                if e in ("$pageview", "$screen"):
                    if st["pv"] > 0:
                        prev_pageview_props(d, st, tsf, rnd)
                        st["page"] = self.page()
                    st["pv"] += 1
                    st["pv_ts"] = tsf
                    if st["pv"] == 1 and st["utm"]:
                        d.update(st["utm"])
                page = st["page"]
                ctx["url"], ctx["path"] = page[0], page[2]
                if not self.mobile or self.web:
                    d["$current_url"], d["$host"], d["$pathname"] = page[0], page[1], page[2]
                    d["$referrer"] = st["ref"]
                    d["$referring_domain"] = "$direct" if st["ref"] == "$direct" else (urlparse(st["ref"]).netloc or st["ref"])
                    se = catalog.SEARCH_ENGINES.get(d["$referring_domain"])
                    if se:
                        d["$search_engine"] = se
                    d["$raw_user_agent"] = per["profile"]["$raw_user_agent"]
                if e == "$screen":
                    d["$screen_name"] = page[2].strip("/").split("/")[0].replace("-", " ").title() or "Home"
                d["$session_id"] = st["sid"]
                d["$window_id"] = st["wid"]
                d["$device_id"] = per["anon_id"]
                d["$is_identified"] = did != per["anon_id"]
                if d["$is_identified"]:
                    d["$user_id"] = did
            elif not server:
                d["$session_id"] = st["sid"]
                d["$screen_name"] = page_name(st["page"])
            else:
                d["$session_id"] = st["sid"]
            # structural standard-event props
            self._special_props(e, d, per, st, ts, ctx, did)
            for p, smp in self.ev_samplers.get(e, {}).items():
                if p in d and smp.source != "spec":
                    continue
                v = smp(ctx)
                if v is not None:
                    d[p] = v
            pg = self.person_groups[pi] if self.group_types else None
            if pg:
                d["$groups"] = pg
            frag = server_frag if server else frags[pi]
            body = orjson.dumps(d).decode()
            props = "{" + frag + ("," + body[1:] if len(body) > 2 else "}") if frag else body
            chunk["uuid"].append(uuid7(int(tsf * 1000), rnd))
            chunk["event"].append(e)
            chunk["properties"].append(props)
            chunk["timestamp"].append(int(tsf * 1_000_000))
            chunk["distinct_id"].append(did)
            chunk["person_id"].append(per["id"])
            chunk["$session_id"].append(d.get("$session_id", ""))
            chunk["$window_id"].append(d.get("$window_id", ""))
            chunk["elements_chain"].append("")
            for gi in range(5):
                chunk[f"$group_{gi}"].append("")
            if pg:
                for gname, gkey in pg.items():
                    chunk[f"$group_{group_names[gname]}"][-1] = gkey
            pidx_list.append(pi)
            ev_counts[e] += 1
            pc = prop_seen[e]
            for k in d:
                pc[k] += 1
                if k not in prop_types:
                    prop_types[k] = ptype(d[k])
            last_seen[e] = tsf
            if len(pidx_list) >= CH:
                flush()
        # legacy trickle for inactive events
        nleg = self._legacy_events(chunk, pidx_list, ev_counts, prop_seen, prop_types, last_seen, frags, server_frag)
        flush()
        writer.close()
        # context props are present on all non-server events
        for e in ev_counts:
            if e not in self.server_events and not e.startswith("$ai_"):
                for p in self.context_props:
                    prop_seen[e][p] += ev_counts[e]
        self.ev_counts, self.prop_seen, self.prop_types, self.last_seen = ev_counts, prop_seen, prop_types, last_seen
        for p in self.context_props:
            v = self.persons[0]["profile"].get(p) if self.persons else None
            prop_types.setdefault(p, ptype(v) if v is not None else "String")
        self.n_events = written
        self.notes["legacy_events"] = nleg

    def _legacy_events(self, chunk, pidx_list, ev_counts, prop_seen, prop_types, last_seen, frags, server_frag):
        """A few events for 'not seen in N days' events, placed before now - N days."""
        rnd = self.rnd
        n = 0
        for e, info in self.inactive.items():
            srcs = set(info["sources"])
            if srcs <= {"taxonomy_list"} and (info["standard"] or not info["properties"]):
                continue  # built-in taxonomy entry, definition only (round 3: Application */mcp * in web twins)
            nsd = int(info["not_seen_days"] or 30)
            if nsd > 730 or not self.persons:
                continue
            smps = self.ev_samplers.get(e, {})
            k = max(rnd.randint(1, 8), min(40, max([len(s.pending) for s in smps.values()] + [0])))
            for s in smps.values():
                s.plan(k)
            for _ in range(k):
                pi = rnd.randrange(len(self.persons))
                per = self.persons[pi]
                ts = self.now - dt.timedelta(days=nsd + rnd.uniform(0.2, 45))
                tsf = ts.timestamp()
                d = {}
                ctx = {"ts": ts, "person": per, "session_id": uuid7(int(tsf * 1000), rnd)}
                d["$session_id"] = ctx["session_id"]
                for p, smp in self.ev_samplers.get(e, {}).items():
                    v = smp(ctx)
                    if v is not None:
                        d[p] = v
                body = orjson.dumps(d).decode()
                frag = frags[pi]
                props = "{" + frag + ("," + body[1:] if len(body) > 2 else "}") if frag else body
                did = per["user_id"] if per["identified"] else per["anon_id"]
                chunk["uuid"].append(uuid7(int(tsf * 1000), rnd)); chunk["event"].append(e)
                chunk["properties"].append(props); chunk["timestamp"].append(int(tsf * 1_000_000))
                chunk["distinct_id"].append(did); chunk["person_id"].append(per["id"])
                chunk["$session_id"].append(d["$session_id"]); chunk["$window_id"].append("")
                chunk["elements_chain"].append("")
                for gi in range(5):
                    chunk[f"$group_{gi}"].append("")
                pidx_list.append(pi)
                ev_counts[e] += 1
                for kk in d:
                    prop_seen[e][kk] += 1
                    prop_types.setdefault(kk, ptype(d[kk]))
                for p in self.context_props:
                    prop_seen[e][p] += 1
                last_seen[e] = max(last_seen.get(e, 0), tsf)
                n += 1
        return n

    def _special_props(self, e, d, per, st, ts, ctx, did):
        rnd = per["rnd"]
        if e == "$identify":
            d["$anon_distinct_id"] = per["anon_id"]
            s = {k: v for k, v in (per.get("props") or {}).items() if not k.startswith("$initial")}
            if s:
                d["$set"] = dict(list(s.items())[:8])
        elif e == "$set":
            d["$set"] = {k: v for k, v in list((per.get("props") or {}).items())[:5]}
        elif e == "$pageleave":
            prev_pageview_props(d, st, ts.timestamp(), rnd)
        elif e in ("$autocapture", "$rageclick", "$dead_click"):
            d["$event_type"] = "click" if e != "$autocapture" else wchoice(rnd, [("click", 0.8), ("submit", 0.1), ("change", 0.1)])[0]
            d["$ce_version"] = 1
            d["$el_text"] = rnd.choice(["Sign up", "Continue", "Save", "Next", "Learn more", "Get started", "Submit",
                                         "Cancel", "Settings", "Upgrade"])
        elif e == "$web_vitals":
            for k, (med, sig) in catalog.WEB_VITALS.items():
                v = med * math.exp(rnd.gauss(0, sig))
                d[k] = round(v, 4) if "CLS" in k else round(v, 1)
        elif e == "$feature_flag_called" and self.flag_keys:
            k = self.flag_keys[min(len(self.flag_keys) - 1, int(rnd.paretovariate(1.2)) - 1)]
            vs = self.flag_variants.get(k) or []
            if vs:
                resp = vs[stable_seed(per["id"], k) % len(vs)]
            else:
                resp = (stable_seed(per["id"], k) % 100) < 60
            d["$feature_flag"] = k
            d["$feature_flag_response"] = resp
            d[f"$feature/{k}"] = resp
        elif e == "$exception":
            iss = wchoice(rnd, [(i, i["w"]) for i in self.issues])[0]
            d["$exception_types"] = [iss["type"]]
            d["$exception_values"] = [iss["message"]]
            d["$exception_type"] = iss["type"]
            d["$exception_message"] = iss["message"]
            d["$exception_issue_id"] = iss["id"]
            d["$exception_fingerprint"] = hashlib.sha1(str(iss["id"]).encode()).hexdigest()[:32]
            d["$exception_level"] = "error"
            d["$exception_list"] = [{"type": iss["type"], "value": iss["message"], "mechanism": {"handled": False, "synthetic": False},
                                     "stacktrace": {"type": "resolved", "frames": [
                                         {"filename": f"https://{self.hosts[0]}/static/chunks/app-{abs(hash(iss['id'])) % 99999:05d}.js",
                                          "function": rnd.choice(["render", "onClick", "fetchData", "useEffect", "handleSubmit"]),
                                          "lineno": rnd.randint(1, 900), "colno": rnd.randint(1, 120), "in_app": True}]}}]
        elif e.startswith("$ai_"):
            if st["trace"] is None:
                st["trace"] = str(uuid.UUID(int=rnd.getrandbits(128), version=4))
            d["$ai_trace_id"] = st["trace"]
            if e in ("$ai_generation", "$ai_embedding", "$ai_span"):
                model, _, prov = wchoice(rnd, catalog.AI_MODELS)
                tin = int(math.exp(rnd.gauss(6.5, 1.0)))
                tout = int(math.exp(rnd.gauss(5.0, 0.9))) if e == "$ai_generation" else 0
                d.update({"$ai_model": model, "$ai_provider": prov, "$ai_input_tokens": tin,
                          "$ai_output_tokens": tout, "$ai_latency": round(math.exp(rnd.gauss(0.3, 0.7)), 3),
                          "$ai_span_id": str(uuid.UUID(int=rnd.getrandbits(128), version=4)),
                          "$ai_http_status": 200 if rnd.random() > 0.02 else 500,
                          "$ai_is_error": False, "$ai_input_cost_usd": round(tin * 2.5e-6, 6),
                          "$ai_output_cost_usd": round(tout * 1e-5, 6)})
                d["$ai_total_cost_usd"] = round(d["$ai_input_cost_usd"] + d["$ai_output_cost_usd"], 6)
                d["$ai_is_error"] = d["$ai_http_status"] != 200
            elif e == "$ai_trace":
                d["$ai_span_name"] = rnd.choice(["chat", "agent_run", "summarize", "search"])
                d["$ai_latency"] = round(math.exp(rnd.gauss(1.2, 0.7)), 3)
            elif e == "$ai_feedback":
                d["$ai_feedback_text"] = rnd.choice(["helpful", "not helpful", "wrong answer", "great"])
            elif e == "$ai_metric":
                d["$ai_metric_name"] = rnd.choice(["thumbs", "accuracy"])
                d["$ai_metric_value"] = rnd.choice([0, 1])
        elif e in ("survey sent", "survey shown", "survey dismissed"):
            if self.surveys:
                sid, sname = self.surveys[stable_seed(per["id"]) % len(self.surveys)]
                d["$survey_id"], d["$survey_name"] = sid, sname
            if e == "survey sent" and "$survey_response" not in self.ev_samplers.get(e, {}):
                d["$survey_response"] = str(rnd.randint(1, 10))
        elif e == "$groupidentify" and self.group_types:
            idx, name, _ = self.group_types[0]
            d["$group_type"] = name
            d["$group_key"] = self.person_groups[ctx["pi"]].get(name)
        if self.flag_keys and e == "$pageview" and self.flag_variants:
            for k, vs in list(self.flag_variants.items())[:3]:
                if vs:
                    d[f"$feature/{k}"] = vs[stable_seed(per["id"], k) % len(vs)]

    # ------------------------------------------------------------------ tables other than events
    def write_people(self, out_dir):
        persons = pa.table({
            "id": [p["id"] for p in self.persons],
            "created_at": pa.array([int(p["created_at"].timestamp() * 1e6) for p in self.persons], pa.timestamp("us", tz="UTC")),
            "properties": self.person_props_json,
            "is_identified": [p["identified"] for p in self.persons],
            "version": [0] * len(self.persons)})
        pq.write_table(persons, os.path.join(out_dir, "persons.parquet"), compression="zstd")
        did, pid = [], []
        for p in self.persons:
            did.append(p["anon_id"]); pid.append(p["id"])
            if p["identified"] and p["user_id"] != p["anon_id"]:
                did.append(p["user_id"]); pid.append(p["id"])
        pq.write_table(pa.table({"distinct_id": did, "person_id": pid, "version": [0] * len(did),
                                 "is_deleted": [0] * len(did)}),
                       os.path.join(out_dir, "person_distinct_ids.parquet"), compression="zstd")
        n_groups = 0
        if self.group_types:
            rows = {"group_type_index": [], "group_key": [], "group_properties": [], "created_at": []}
            for idx, name, _ in self.group_types:
                for g in self.groups[idx]:
                    rows["group_type_index"].append(idx); rows["group_key"].append(g["key"])
                    rows["group_properties"].append(orjson.dumps(g["props"]).decode())
                    rows["created_at"].append(int(g["created_at"].timestamp() * 1e6))
            rows["created_at"] = pa.array(rows["created_at"], pa.timestamp("us", tz="UTC"))
            pq.write_table(pa.table(rows), os.path.join(out_dir, "groups.parquet"), compression="zstd")
            n_groups = len(rows["group_key"])
        self.n_groups = n_groups

    def definitions(self):
        S = self.S
        evdefs = []
        all_events = dict(self.active)
        all_events.update(self.inactive)
        for e, info in all_events.items():
            ls = self.last_seen.get(e)
            if ls is None and info["not_seen_days"] is not None:
                ls = (self.now - dt.timedelta(days=info["not_seen_days"])).timestamp()
            evdefs.append({"name": e, "description": info.get("description"),
                           "last_seen_at": iso(dt.datetime.fromtimestamp(ls, UTC)) if ls else None,
                           "volume_30_day": None, "invented": e in self.invented,
                           "generated_count": self.ev_counts.get(e, 0)})
        desc = {}
        types = {}
        for sec in [e["properties"] for e in S["events"].values()] + [S["unscoped"]]:
            for p, d in sec.items():
                if d.get("description"):
                    desc.setdefault(p, d["description"])
                if d.get("type"):
                    types.setdefault(p, d["type"])
        pdefs = []
        seen = set()
        for e, pc in self.prop_seen.items():
            for p in pc:
                if p in seen:
                    continue
                seen.add(p)
                t = types.get(p) or self.prop_types.get(p) or "String"
                pdefs.append({"name": p, "type": 1, "property_type": t, "is_numerical": t == "Numeric",
                              "description": desc.get(p), "group_type_index": None})
        # spec-listed virtual / platform-computed props: definitions only
        for sec in [e["properties"] for e in S["events"].values()] + [S["unscoped"]]:
            for p, d in sec.items():
                if p not in seen:
                    seen.add(p)
                    pdefs.append({"name": p, "type": 1, "property_type": d.get("type") or "String",
                                  "is_numerical": d.get("type") == "Numeric", "description": d.get("description"),
                                  "group_type_index": None, "virtual_or_unused": True})
        pp_seen = set()
        for per in self.persons:
            pp_seen.update(per["props"].keys())
        for p in sorted(pp_seen | set(self.person_prop_specs)):
            d = self.person_prop_specs.get(p, {})
            t = d.get("type") or "String"
            pdefs.append({"name": p, "type": 2, "property_type": t, "is_numerical": t == "Numeric",
                          "description": d.get("description"), "group_type_index": None})
        for p, d in S["session_props"].items():
            pdefs.append({"name": p, "type": 4, "property_type": d.get("type") or "String",
                          "is_numerical": d.get("type") == "Numeric", "description": d.get("description"),
                          "group_type_index": None, "derived": True})
        for idx, name, props in self.group_types:
            gp = set()
            for g in self.groups[idx]:
                gp.update(g["props"])
            for p in sorted(gp):
                d = (props or {}).get(p, {})
                pdefs.append({"name": p, "type": 3, "property_type": d.get("type") or "String",
                              "is_numerical": d.get("type") == "Numeric", "description": d.get("description"),
                              "group_type_index": idx})
        evprops = [{"event": e, "property": p} for e, pc in self.prop_seen.items() for p in pc]
        return {"event_definitions": evdefs, "property_definitions": pdefs, "event_properties": evprops,
                "group_type_mapping": [{"group_type_index": i, "group_type": n} for i, n, _ in self.group_types]}

    def objects(self):
        S, rnd = self.S, self.rnd
        out = defaultdict(list)
        excluded = Counter()
        top_events = sorted(self.ev_counts, key=lambda e: -self.ev_counts[e]) or ["$pageview"]
        for kind, objs in S["objects"].items():
            for key, o in objs.items():
                if self._created(o):
                    excluded[kind] += 1
                    continue
                base = {k: v for k, v in o.items() if k not in ("sources", "first_source", "created_in_conversation")}
                base["key"] = key
                base["edited_in_conversation"] = "edited_by_agent" in (o.get("sources") or {})
                if kind == "insights":
                    base["query"] = insight_query(o, top_events)
                elif kind == "feature_flags":
                    base.setdefault("name", key)
                    base["filters"] = {"groups": [{"properties": [], "rollout_percentage":
                                                   pct(o.get("rollout")) if o.get("rollout") is not None else 100}],
                                       "multivariate": {"variants": [{"key": v.get("key"), "rollout_percentage": v.get("rollout")}
                                                                     for v in o.get("variants") or []]} if o.get("variants") else None}
                elif kind == "cohorts":
                    pp = [p for p in self.person_prop_specs if not p.startswith("$")] or ["$geoip_country_code"]
                    p = rnd.choice(pp)
                    base["filters_generated"] = {"properties": {"type": "AND", "values": [
                        {"type": "AND", "values": [{"key": p, "type": "person", "operator": "is_set", "value": "is_set"}]}]}}
                elif kind == "actions":
                    nm = (o.get("name") or "").lower()
                    toks = set(re.split(r"[^a-z0-9]+", nm)) - {""}
                    best = max(top_events, key=lambda e: len(toks & set(re.split(r"[^a-z0-9]+", e.lower()))))
                    base["steps"] = [{"event": best}]
                elif kind == "surveys":
                    qt = o.get("question_types") or ["rating"]
                    base["questions"] = [{"type": t, "question": {"rating": "How likely are you to recommend us?",
                                                                  "open": "What could we improve?",
                                                                  "single_choice": "What best describes you?",
                                                                  "multiple_choice": "Which features do you use?"}.get(t, "Any feedback?")}
                                         for t in qt]
                elif kind == "error_tracking_issues":
                    base["generated_occurrences"] = None
                out[kind].append(base)
        # dashboards: attach tiles by name
        dash_names = {d.get("name"): d for d in out.get("dashboards", [])}
        for ins in out.get("insights", []):
            for dn in ins.get("dashboards") or []:
                if dn in dash_names:
                    dash_names[dn].setdefault("tiles", []).append(ins["key"])
        return dict(out), dict(excluded)

    def warehouse(self, out_dir):
        S = self.S
        tables = S["warehouse"]
        if not tables:
            return {}
        os.makedirs(os.path.join(out_dir, "warehouse"), exist_ok=True)
        sqls = [a.get("query") for a in S["anchors"] if isinstance(a.get("query"), str)]
        for o in (S["objects"].get("insights") or {}).values():
            q = o.get("query") or {}
            if isinstance(q, dict) and isinstance(q.get("sql"), str):
                sqls.append(q["sql"])
        schema_out = {}
        for tname, tb in tables.items():
            fields = [(f["name"], f["type"], f.get("description")) for f in tb.get("fields") or [] if f.get("name")]
            inferred = False
            if not fields:
                fields = infer_columns(tname, sqls)
                inferred = True
            joins = [f for f in fields if f[1] == "lazy_table" or f[1] == "virtual_table"]
            cols = [f for f in fields if f not in joins]
            tr = random.Random(stable_seed(S["id"], "wh", tname))
            nrows = tr.randint(200, 3000)
            if re.search(r"user|person|customer|account|contact|member", tname, re.I):
                nrows = max(50, min(20000, int(self.n_persons * tr.uniform(0.3, 0.9))))
            data = {}
            ptypes = []
            for cname, ctype, _ in cols:
                arr, at = wh_column(cname, ctype, nrows, tr, self)
                data[cname] = pa.array(arr, at)
                ptypes.append(at)
            fn = re.sub(r"[^A-Za-z0-9_.-]+", "_", tname) + ".parquet"
            if data:
                pq.write_table(pa.table(data), os.path.join(out_dir, "warehouse", fn), compression="zstd")
            schema_out[tname] = {"file": f"warehouse/{fn}", "kind": tb.get("kind"), "description": tb.get("description"),
                                 "columns_inferred": inferred, "rows": nrows if data else 0,
                                 "columns": [{"name": c, "type": t, "description": d} for c, t, d in cols],
                                 "joins": [{"name": c, "type": t, "description": d} for c, t, d in joins]}
        return schema_out

    # ------------------------------------------------------------------ driver
    def run(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        t = {}
        t0 = time.time()
        self.plan(); self.build_pages(); self.build_context_props()
        t["plan"] = time.time() - t0
        self.simulate_activity(); self.build_persons(); self.person_properties(); self.build_groups()
        t["persons"] = time.time() - t0 - t["plan"]
        self.build_event_samplers(); self.prepare_special(); self.plan_occurrences(); self.schedule()
        t1 = time.time()
        self.write_events(out_dir)
        t["events"] = time.time() - t1
        self.write_people(out_dir)
        defs = self.definitions()
        with open(os.path.join(out_dir, "definitions.json"), "wb") as fh:
            fh.write(orjson.dumps(defs))
        objs, excluded = self.objects()
        with open(os.path.join(out_dir, "objects.json"), "wb") as fh:
            fh.write(orjson.dumps(objs))
        wh = self.warehouse(out_dir)
        if wh:
            with open(os.path.join(out_dir, "warehouse", "schema.json"), "wb") as fh:
                fh.write(orjson.dumps(wh))
        t["total"] = time.time() - self.t0
        S = self.S
        man = {
            "generator": GEN_VERSION, "spec_id": S["id"], "spec_kind": S["kind"], "members": S["members"],
            "split": S.get("split"), "seed": self.seed, "now_utc": iso(self.now), "now_source": "spec" if S["now_utc"] else "default",
            "timezone": self.tzname, "timezone_known": S["tz_known"], "history_days": self.H,
            "required_history_days": self.required_days, "pre_history_days": self.pre_days,
            "volume_scale": self.volume_scale, "max_events": self.max_events, "dau_source": self.dau_source,
            "target_dau": round(self.D, 3), "realized_dau_last30": round(self.realized_dau, 3),
            "platform": "mobile" if (self.mobile and not self.web) else ("web+mobile" if self.mobile else "web"),
            "counts": {"events": self.n_events, "persons": self.n_persons,
                       "distinct_ids": sum(1 + (p["identified"] and p["user_id"] != p["anon_id"]) for p in self.persons),
                       "groups": self.n_groups, "event_names": len(self.ev_counts),
                       "event_definitions": len(defs["event_definitions"]),
                       "property_definitions": len(defs["property_definitions"]),
                       "objects": {k: len(v) for k, v in objs.items()}, "objects_excluded_created": excluded,
                       "warehouse_tables": len(wh), "invented_events": len(self.invented)},
            "files": {"events": "events.parquet", "persons": "persons.parquet",
                      "person_distinct_ids": "person_distinct_ids.parquet",
                      "groups": "groups.parquet" if self.group_types else None, "definitions": "definitions.json",
                      "objects": "objects.json", "warehouse_schema": "warehouse/schema.json" if wh else None},
            "targets": {e: {"daily_total": round(v[0], 4), "daily_dau": round(v[1], 4)} for e, v in self.targets.items()},
            "notes": dict(self.notes), "timing_s": {k: round(v, 3) for k, v in t.items()},
        }
        with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
            json.dump(man, fh, indent=1, default=str)
        return man


# ---------------------------------------------------------------------- helpers
def prev_pageview_props(d, st, tsf, rnd):
    content = rnd.randint(600, 9000)
    viewport = rnd.randint(500, 1100)
    mx = rnd.randint(0, max(0, content - viewport))
    last = rnd.randint(0, mx)
    d["$prev_pageview_pathname"] = st["page"][2]
    d["$prev_pageview_duration"] = round(max(0.0, tsf - st["pv_ts"]), 1)
    d["$prev_pageview_max_scroll"] = mx
    d["$prev_pageview_last_scroll"] = last
    d["$prev_pageview_max_content"] = mx + viewport
    d["$prev_pageview_last_content"] = last + viewport
    d["$prev_pageview_max_scroll_percentage"] = round(mx / max(1, content - viewport), 3)
    d["$prev_pageview_last_scroll_percentage"] = round(last / max(1, content - viewport), 3)
    d["$prev_pageview_max_content_percentage"] = round((mx + viewport) / content, 3)
    d["$prev_pageview_last_content_percentage"] = round((last + viewport) / content, 3)


def anchors_has(hints, ev):
    return any(h[0] == ev for h in hints)


def page_name(page):
    return page[2].strip("/").split("/")[0].replace("-", " ").title() or "Home"


def ptype(v):
    if isinstance(v, bool):
        return "Boolean"
    if isinstance(v, (int, float)):
        return "Numeric"
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z?", v):
        return "DateTime"
    return "String"


def pct(x):
    v = num(str(x).rstrip("%")) if x is not None else None
    return v if v is not None else 100


def insight_query(o, top_events):
    q = o.get("query") if isinstance(o.get("query"), dict) else None
    kind = (q or {}).get("kind") or o.get("query_kind") or "TrendsQuery"
    if kind in ("HogQLQuery", "DataVisualizationNode", "SQL", "sql") or (q and q.get("sql")):
        return {"kind": "DataVisualizationNode", "source": {"kind": "HogQLQuery", "query": (q or {}).get("sql") or
                                                             "SELECT count() FROM events WHERE timestamp > now() - INTERVAL 30 DAY"}}
    series = []
    for s in (q or {}).get("series") or []:
        if not isinstance(s, dict):
            continue
        node = {"kind": "EventsNode", "event": s.get("event"), "name": s.get("event")}
        if s.get("action") is not None:
            node = {"kind": "ActionsNode", "id": s.get("action")}
        if s.get("math"):
            node["math"] = s["math"]
        if s.get("math_property"):
            node["math_property"] = s["math_property"]
        series.append(node)
    if not series:
        series = [{"kind": "EventsNode", "event": top_events[0], "name": top_events[0]}]
        if kind == "FunnelsQuery":
            series += [{"kind": "EventsNode", "event": e, "name": e} for e in top_events[1:3]]
    src = {"kind": kind if kind.endswith("Query") else "TrendsQuery", "series": series}
    if q:
        if q.get("interval"):
            src["interval"] = q["interval"]
        if q.get("dateRange"):
            src["dateRange"] = q["dateRange"]
        if q.get("filterTestAccounts") is not None:
            src["filterTestAccounts"] = q["filterTestAccounts"]
        b = q.get("breakdown")
        if isinstance(b, list) and b:
            src["breakdownFilter"] = {"breakdowns": [{"property": x.get("property"), "type": x.get("type"),
                                                      **({"group_type_index": x["group_type_index"]} if "group_type_index" in x else {})}
                                                     for x in b if isinstance(x, dict)]}
        elif isinstance(b, str):
            src["breakdownFilter"] = {"breakdown": b, "breakdown_type": "event"}
    if src["kind"] == "RetentionQuery":
        src["retentionFilter"] = {"period": "Week", "totalIntervals": 8,
                                  "targetEntity": {"id": series[0].get("event"), "type": "events"},
                                  "returningEntity": {"id": series[-1].get("event"), "type": "events"}}
    return {"kind": "InsightVizNode", "source": src}


WH_TYPES = {"string": pa.string(), "integer": pa.int64(), "float": pa.float64(), "decimal": pa.float64(),
            "boolean": pa.bool_(), "datetime": pa.timestamp("us", tz="UTC"), "date": pa.date32(), "json": pa.string(),
            "array": pa.string()}


def infer_columns(tname, sqls):
    short = tname.split(".")[-1]
    cols = {}
    for sql in sqls:
        if not sql or short not in sql:
            continue
        aliases = {short}
        for m in re.finditer(r"(?:FROM|JOIN)\s+([`\"\w.]+)(?:\s+(?:AS\s+)?(\w+))?", sql, re.I):
            if m.group(1).strip('`"').split(".")[-1] == short and m.group(2) and m.group(2).upper() not in (
                    "WHERE", "ON", "JOIN", "LEFT", "INNER", "GROUP", "ORDER", "LIMIT", "AS", "RIGHT", "FULL"):
                aliases.add(m.group(2))
        for a in aliases:
            for m in re.finditer(rf"\b{re.escape(a)}\.(\w+)", sql):
                cols.setdefault(m.group(1), None)
    if not cols:
        toks = short.lower()
        cols = {"id": None, "created_at": None, "updated_at": None}
        if re.search(r"charge|invoice|payment|subscription|order|transaction|revenue", toks):
            cols.update({"customer_id": None, "amount": None, "currency": None, "status": None})
        if re.search(r"user|customer|account|contact|member|person|lead", toks):
            cols.update({"email": None, "name": None, "plan": None, "status": None})
        if re.search(r"product|item|plan|price", toks):
            cols.update({"name": None, "price": None, "active": None})
        if len(cols) == 3:
            cols.update({"name": None, "status": None, "user_id": None, "value": None})
    out = []
    for c in cols:
        sh = shape_of(c)
        t = {"datetime": "datetime", "count": "integer", "money": "float", "duration": "float", "bool": "boolean",
             "id": "string"}.get(sh, "string")
        if c in ("active",):
            t = "boolean"
        out.append((c, t, None))
    return out


def wh_column(cname, ctype, n, tr, proj):
    lc = cname.lower()
    t = (ctype or "string").lower()
    at = WH_TYPES.get(t, pa.string())
    persons = proj.persons
    if t in ("datetime", "date"):
        base = proj.now.timestamp()
        vals = [base - tr.uniform(0, (proj.H + proj.pre_days) * 86400) for _ in range(n)]
        if t == "date":
            return [dt.date.fromtimestamp(v) for v in vals], at
        return [int(v * 1e6) for v in vals], at
    if t == "boolean":
        p = tr.uniform(0.2, 0.8)
        return [tr.random() < p for _ in range(n)], at
    if t in ("integer",):
        if lc == "id" or lc.endswith("_id"):
            return [i + 1 if lc == "id" else tr.randint(1, max(2, n)) for i in range(n)], at
        med = 3 if shape_of(cname) == "count" else 100
        return [int(med * math.exp(tr.gauss(0, 1))) for _ in range(n)], at
    if t in ("float", "decimal"):
        return [round(49 * math.exp(tr.gauss(0, 1)), 2) for _ in range(n)], at
    if t in ("json", "array"):
        return ["{}" if t == "json" else "[]" for _ in range(n)], at
    # strings
    if "email" in lc and persons:
        em = [p["email"] for p in persons if p["email"]] or [f"user{i}@example.com" for i in range(10)]
        return [em[i % len(em)] for i in range(n)], at
    if lc in ("distinct_id", "posthog_distinct_id", "user_id", "external_id") and persons:
        return [persons[i % len(persons)]["user_id"] for i in range(n)], at
    if lc == "person_id" and persons:
        return [persons[i % len(persons)]["id"] for i in range(n)], at
    if lc == "id" or lc.endswith("_id") or lc == "uuid":
        pre = re.sub(r"[^a-z]", "", lc.replace("_id", ""))[:3] or "id"
        return [f"{pre}_{tr.getrandbits(48):012x}" for _ in range(n)], at
    if lc in ("currency",):
        return [tr.choice(["usd", "usd", "usd", "eur", "gbp"]) for _ in range(n)], at
    toks = re.split(r"[^a-z]+", lc)
    for tok in reversed(toks):
        if tok in VOCAB:
            pool = VOCAB[tok]
            return [pool[min(len(pool) - 1, int(tr.paretovariate(1.3)) - 1)] for _ in range(n)], at
    if "name" in lc:
        return [f"{tr.choice(catalog.FIRST_NAMES)} {tr.choice(catalog.LAST_NAMES)}" for _ in range(n)], at
    if "url" in lc:
        return [proj.page()[0] for _ in range(n)], at
    stem = stem_of(cname)
    k = tr.randint(3, 12)
    return [f"{stem}_{int(tr.paretovariate(1.2)) % k}" for _ in range(n)], at


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--now")
    ap.add_argument("--max-events", type=int, default=5_000_000)
    ap.add_argument("--history-days", type=int)
    a = ap.parse_args()
    spec = specio.load(a.spec)
    now = dt.datetime.fromisoformat(a.now).astimezone(UTC) if a.now else None
    man = Project(spec, a.seed, now, a.max_events, a.history_days).run(a.out)
    c = man["counts"]
    print(json.dumps({"events": c["events"], "persons": c["persons"], "event_names": c["event_names"],
                      "history_days": man["history_days"], "volume_scale": round(man["volume_scale"], 4),
                      "timing_s": man["timing_s"]}))


if __name__ == "__main__":
    main()
