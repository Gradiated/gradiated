#!/usr/bin/env python3
"""Twin lint: deterministic coherence checks on a generated twin project (events.parquet, persons.parquet).

The LLM validator checks that the data a task needs exists; it misses ratio and plausibility problems (acceptance audit
of loop round b12: purchases 12x checkouts, every person firing every custom event, placeholder values, a GitHub PR
URL as the project's top page, campaigns crossed with random sources). These checks are mechanical:

  event_reach       a custom event (not $-prefixed) reaches > 90% of the persons who have any event (n >= 50)
  funnel_order      a later step outnumbers its earlier step in events or persons by > 10% (name-evident pairs,
                    e-commerce chain view_item < add_to_cart < begin_checkout < purchase, family roots)
  buyers_vs_visitors  persons with a purchase-like event exceed persons with a $pageview/$screen (web/mobile twins)
  placeholder       a property value looks like a generator placeholder (<stem>_a..l, "Name 3", page3, handle1,
                    sub1.sub2.*, "example company 7"), per property with share of rows
  third_party_host  pageviews on hosts that are third-party services (github.com, google docs, notion, ...)
  url_dominance     one URL with a query string carries > 50% of pageviews
  value_domain      a property whose name is not URL-like holds URLs in >= 30% of rows
  campaign_source   utm_campaign names a channel (google/search, facebook/meta, email/newsletter, ...) that its
                    utm_source contradicts in > 30% of rows

    python3 lint.py <project dir> [<project dir> ...]     -> one JSON line per project
lint_project(dir) returns {"findings": [{"check", "severity", "detail"}], "stats": {...}}.
"""

from __future__ import annotations

import collections as C
import json
import os
import re
import sys

PLACEHOLDER_PATTERNS = [
    ("stem_letter", re.compile(r"^[a-z][a-z0-9_]*_[a-l]$")),
    ("title_number", re.compile(r"^(?!Q[1-4] )(?!Version )[A-Z][a-z]+( [A-Z][a-z]+)? \d{1,2}$")),
    ("page_n", re.compile(r"(^|/)page\d+(/|$)")),
    ("handle_n", re.compile(r"(^|[./])handle\d+([./]|$)")),
    ("sub_n", re.compile(r"(^|\.)sub\d+\.sub\d+\.")),
    ("example_company", re.compile(r"^example company \d+$", re.I)),
]
THIRD_PARTY = re.compile(r"(^|\.)(github\.com|gitlab\.com|google\.com|docs\.google\.com|notion\.so|figma\.com|stripe\.com|"
                         r"youtube\.com|linkedin\.com|twitter\.com|x\.com|facebook\.com|slack\.com|loom\.com|"
                         r"atlassian\.net|zendesk\.com|intercom\.io|hubspot\.com|calendly\.com|typeform\.com)$", re.I)
URL_PROPS = {"$host", "$current_url", "$pathname", "$referrer", "$referring_domain", "$initial_referrer",
             "$initial_referring_domain", "$initial_current_url", "$initial_host", "$initial_pathname", "$prev_pageview_pathname"}
URLISH_TOKENS = {"url", "urls", "uri", "host", "hostname", "link", "links", "href", "referrer", "referer", "page", "pathname",
                 "path", "domain", "site", "website", "homepage", "location", "redirect", "src", "endpoint", "webhook",
                 "callback", "image", "avatar", "icon", "logo", "origin", "target", "source", "screenshot"}


def urlish(name: str) -> bool:
    """A property name that may hold URLs: its last token is url/host/link/page/referrer/... (not 'linked', 'status')."""
    toks = [t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t]
    return bool(toks) and (toks[-1] in URLISH_TOKENS or toks[-1].endswith("url"))  # '..._url_trigger_status': status
URL_VALUE = re.compile(r"^https?://")
COMMERCE = ["view_item", "add_to_cart", "begin_checkout", "add_payment_info", "purchase"]
PURCHASE = re.compile(r"(^|[_ .:-])(purchase|purchased|order[_ ]completed|order[_ ]placed|payment[_ ]succeeded|checkout[_ ]completed)"
                      r"([_ .:-]|$)", re.I)
CHANNEL = [("google", re.compile(r"google|search|sem|cpc|adwords", re.I), re.compile(r"google|bing|search", re.I)),
           ("meta", re.compile(r"facebook|meta|insta|fb_|ig_", re.I), re.compile(r"facebook|instagram|meta|fb|ig", re.I)),
           ("email", re.compile(r"email|newsletter|drip|mailchimp|klaviyo", re.I), re.compile(r"email|newsletter|mail", re.I)),
           ("tiktok", re.compile(r"tiktok", re.I), re.compile(r"tiktok", re.I)),
           ("linkedin", re.compile(r"linkedin", re.I), re.compile(r"linkedin", re.I))]


def _gen2():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gen2  # noqa: E402  (shared name rules: parent_event, family_parent, LIFECYCLE_ONCE)

    return gen2


def _pairs(names: set) -> list[tuple[str, str, bool]]:
    gen2 = _gen2()
    out = []
    for e in names:
        p = gen2.parent_event(e, names)
        if p:
            out.append((p, e, True))
        elif gen2.family_parent(e, names):  # same-prefix family: repeat use is normal, compare persons only
            out.append((gen2.family_parent(e, names), e, False))
    low = {n.lower(): n for n in names}
    chain = [low[c] for c in COMMERCE if c in low]
    out += [(a, b, True) for a, b in zip(chain, chain[1:])]
    return out


def lint_project(d: str, max_rows: int = 400000) -> dict:
    import pyarrow.parquet as pq

    t = pq.read_table(f"{d}/events.parquet", columns=["event", "person_id", "properties"])
    n = t.num_rows
    step = max(1, n // max_rows)
    ev = t.column("event").to_pylist()
    pid = t.column("person_id").to_pylist()
    props = t.column("properties").to_pylist()
    findings = []
    persons_any = set(pid)
    ev_count = C.Counter(ev)
    ev_persons: dict = C.defaultdict(set)
    for e, p in zip(ev, pid):
        ev_persons[e].add(p)
    # event_reach
    if len(persons_any) >= 50:
        for e, ps in ev_persons.items():
            if not str(e).startswith("$") and len(ps) > 0.9 * len(persons_any):
                # one-time lifecycle events (signed_up, first_*): reach reflects the acquisition window (minor)
                findings.append({"check": "event_reach", "severity": "minor" if _gen2().LIFECYCLE_ONCE.match(str(e)) else "material",
                                 "detail": f"{e!r} reaches {len(ps)}/{len(persons_any)} persons"})
    # funnel_order
    for parent, child, by_events in _pairs(set(ev_count)):
        if (by_events and ev_count[child] > 1.1 * ev_count[parent]) or len(ev_persons[child]) > 1.1 * len(ev_persons[parent]):
            findings.append({"check": "funnel_order", "severity": "material",
                             "detail": f"{child!r} ({ev_count[child]} ev/{len(ev_persons[child])} p) > {parent!r} "
                                       f"({ev_count[parent]} ev/{len(ev_persons[parent])} p)"})
    # buyers vs visitors
    visitors = ev_persons.get("$pageview", set()) | ev_persons.get("$screen", set())
    if visitors:
        for e in ev_count:
            if PURCHASE.search(str(e)) and len(ev_persons[e]) > 1.05 * len(visitors) and len(ev_persons[e]) >= 20:
                findings.append({"check": "buyers_vs_visitors", "severity": "material",
                                 "detail": f"{e!r} persons {len(ev_persons[e])} > visitors {len(visitors)}"})
    # property scans (sampled rows)
    ph: dict = C.defaultdict(C.Counter)
    url_vals: C.Counter = C.Counter()
    seen_rows: C.Counter = C.Counter()
    hosts: C.Counter = C.Counter()
    urls: C.Counter = C.Counter()
    pv = 0
    camp_bad = camp_tot = 0
    for i in range(0, n, step):
        s = props[i]
        if not s:
            continue
        try:
            d_ = json.loads(s)
        except ValueError:
            continue
        for k, v in d_.items():
            if not isinstance(v, str) or k in ("$session_id", "$window_id", "$device_id", "$insert_id", "token"):
                continue
            seen_rows[k] += 1
            if URL_VALUE.match(v) and not urlish(k):
                url_vals[k] += 1
            for name, rx in PLACEHOLDER_PATTERNS:
                if rx.search(v):
                    ph[k][name] += 1
                    break
        if ev[i] == "$pageview":
            pv += 1
            u = d_.get("$current_url")
            if isinstance(u, str):
                h = re.sub(r"^https?://", "", u).split("/")[0].split("?")[0].lower()
                hosts[h] += 1
                if "?" in u:
                    urls[u] += 1
        c, src = d_.get("utm_campaign"), d_.get("utm_source")
        if isinstance(c, str) and isinstance(src, str):
            for _ch, crx, srx in CHANNEL:
                if crx.search(c):
                    camp_tot += 1
                    camp_bad += not srx.search(src)
                    break
    for k, cnt in ph.items():
        share = sum(cnt.values()) / max(1, seen_rows[k])
        # hosts/URLs: sub1.sub2.* and handle1 are the trace anonymizer's tokens, shared with the task text (minor)
        anon = (k in URL_PROPS or urlish(k)) and set(cnt) <= {"page_n", "handle_n", "sub_n"}
        if share >= 0.05:
            findings.append({"check": "placeholder", "severity": "material" if share >= 0.3 and not anon else "minor",
                             "detail": f"{k}: {share:.0%} placeholder-like ({dict(cnt)})"})
    for k, c in url_vals.items():
        if c >= 0.3 * max(1, seen_rows[k]) and c >= 5:
            findings.append({"check": "value_domain", "severity": "material",
                             "detail": f"{k}: {c}/{seen_rows[k]} values are URLs"})
    for h, c in hosts.items():
        if THIRD_PARTY.search(h) and c >= 0.02 * max(1, pv):
            findings.append({"check": "third_party_host", "severity": "material", "detail": f"{h}: {c}/{pv} pageviews"})
    if urls and pv:
        u, c = urls.most_common(1)[0]
        if c > 0.5 * pv:
            findings.append({"check": "url_dominance", "severity": "material", "detail": f"{u[:120]}: {c}/{pv} pageviews"})
    if camp_tot >= 30 and camp_bad > 0.3 * camp_tot:
        findings.append({"check": "campaign_source", "severity": "minor",
                         "detail": f"{camp_bad}/{camp_tot} rows: campaign names a channel its source contradicts"})
    return {"findings": findings, "stats": {"events": n, "persons": len(persons_any), "event_names": len(ev_count),
                                            "pageviews_sampled": pv}}


def main() -> None:
    for d in sys.argv[1:]:
        try:
            r = lint_project(d)
        except Exception as e:  # noqa: BLE001
            r = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        print(json.dumps({"project": os.path.basename(d.rstrip("/")), **r}))


if __name__ == "__main__":
    main()
