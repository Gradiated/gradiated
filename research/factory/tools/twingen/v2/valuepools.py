"""Realistic value pools for properties the generator has no observed values for (twingen v2, rule r7).

Without observed values the base sampler invents placeholder pools ("<prop>_a".."<prop>_g", "Prop 1".."Prop 20"),
which agents notice and report as data-quality problems that production does not have (spot-check batch b02: 7 of 10
tasks). Before generating a twin, this module lists those properties and asks an LLM (subscription proxy, one call per
twin) for realistic, business-consistent values with weights, using the project's event names, the conversation's
language and a short excerpt of the user's request. Results are cached per spec in <root>/twins/valuepools_v2/, so
regeneration is deterministic and costs nothing; a failed call leaves the old behaviour (counted in the manifest).

Pools are keyed "<event>::<prop>" for event properties and "person::<prop>" for person properties.
"""

from __future__ import annotations

import json
import os
import re
import sys

SKIP_SHAPES = {"id", "email", "url", "path"}
PROMPT = """You help build a realistic synthetic copy of a customer's PostHog analytics project. Some event and person
properties have no observed values, and we need realistic values for them.

Business context (from the customer's own question to their analytics assistant; may be in any language):
{context}

Events in the project (most frequent first): {events}

For each property below, list 4-15 realistic values this business would actually record, most common first, with a
relative weight. Values must fit the business (its domain, country, language, product names style) and the property's
meaning; use the formats real tracking code sends (snake_case enums, ISO country codes, version strings, plan names,
cities...). Never use placeholders like "<name>_a", "Name 1", "example", "foo", "test", "N/A". For numeric-looking
properties give plausible numbers as strings. If a property is clearly free text, give short realistic examples.

Properties ("<event>::<property>" or "person::<property>"):
{props}

Respond with ONLY a JSON object mapping each key above to a list of [value, weight] pairs."""


def candidates(spec: dict, shape_of, vocab: dict, stem_of) -> list[str]:
    """Keys of String-like properties with no observed values that would get a placeholder pool."""
    def needs(p: str, d: dict) -> bool:
        if (d.get("values") or []) or (d.get("type") not in (None, "String")):
            return False
        if p.startswith("$") or shape_of(p) in SKIP_SHAPES:
            return False
        toks = re.split(r"[^a-z]+", p.lower())
        return not any(t in vocab for t in toks)

    out = []
    for e, info in (spec.get("events") or {}).items():
        for p, d in (info.get("properties") or {}).items():
            if needs(p, d):
                out.append(f"{e}::{p}")
    for p, d in (spec.get("unscoped") or {}).items():
        if needs(p, d):
            out.append(f"*::{p}")
    for p, d in ((spec.get("entities") or {}).get("person", {}).get("properties") or {}).items():
        if needs(p, d):
            out.append(f"person::{p}")
    return sorted(set(out))[:120]


def get_pools(spec: dict, root: str, keys: list[str], user_text: str, model: str = "gpt-6.1-terra") -> tuple[dict, str]:
    """Cached LLM value pools for `keys`. Returns (pools, status) with status cached|llm|failed|none."""
    if not keys:
        return {}, "none"
    d = f"{root}/twins/valuepools_v2"
    path = f"{d}/{spec['id']}.json"
    cached = {}
    if os.path.exists(path):
        try:
            cached = json.load(open(path))
        except ValueError:
            cached = {}
    missing = [k for k in keys if k not in cached]
    if not missing:
        return cached, "cached"
    if os.environ.get("TWINGEN_NO_LLM_POOLS") == "1":
        return cached, "failed"
    sys.path.insert(0, "/opt/posthog-env")
    try:
        import llm_proxy

        events = ", ".join(list((spec.get("events") or {}).keys())[:40])
        prompt = PROMPT.format(context=(user_text or "")[:1500] or "(none)", events=events, props="\n".join(missing))
        text, _ = llm_proxy.judge_complete(prompt, model, None, attempts=4, preamble=False, limit=False)
        s, e = text.find("{"), text.rfind("}")
        got = json.loads(text[s:e + 1])
        for k, v in got.items():
            if k in missing and isinstance(v, list):
                pool = [[str(x[0]), float(x[1])] for x in v if isinstance(x, list) and len(x) == 2 and str(x[0]).strip()
                        and isinstance(x[1], (int, float)) and x[1] > 0 and not PLACEHOLDER.match(str(x[0]))]
                if pool:
                    cached[k] = pool
        os.makedirs(d, exist_ok=True)
        json.dump(cached, open(path + ".tmp", "w"), ensure_ascii=False, indent=1)
        os.replace(path + ".tmp", path)
        return cached, "llm"
    except Exception:  # noqa: BLE001
        return cached, "failed"


PLACEHOLDER = re.compile(r"^([a-z0-9]+(_[a-z0-9]+)*_[a-l]|[A-Z][a-z]+( [A-Z][a-z]+)* \d{1,2}|example.*|foo|bar|test|n/?a)$")


def pool_for(pools: dict, event: str | None, prop: str) -> list | None:
    """Pool for (event, prop): event-specific first, then unscoped, then any event's pool for the same property."""
    for k in ((f"{event}::{prop}") if event else None, f"*::{prop}"):
        if k and k in pools:
            return pools[k]
    for k, v in pools.items():
        if k.split("::", 1)[-1] == prop and not k.startswith("person::"):
            return v
    return None


PAGES_PROMPT = """You help build a realistic synthetic copy of a customer's PostHog analytics project. We need the web
pages this business's site/app actually has, so pageviews look like this product and not a generic SaaS template.

Business context (from the customer's own question to their analytics assistant; may be in any language):
{context}

Events in the project (most frequent first): {events}

List 15-30 page paths this product would really have (most visited first) with a relative weight, matching what the
events describe (e.g. an AI video generator: /create, /editor/<id>, /gallery, /pricing; a game wiki: /characters/<slug>,
/calculator, /guides/<slug>). Use concrete realistic slugs/ids instead of placeholders. Also give one plausible host name
for the app (e.g. app.<brand>.com) using a brand word from the context if there is one, else a neutral invented brand.

Respond with ONLY JSON: {{"host": "<host>", "paths": [["/path", weight], ...]}}"""


def get_pages(spec: dict, root: str, user_text: str, model: str = "gpt-6.1-terra") -> tuple[dict, str]:
    """Cached LLM page set {"host", "paths"} for a twin whose conversation shows no pages (rule r17)."""
    d = f"{root}/twins/valuepools_v2"
    path = f"{d}/{spec['id']}.pages.json"
    if os.path.exists(path):
        try:
            return json.load(open(path)), "cached"
        except ValueError:
            pass
    if os.environ.get("TWINGEN_NO_LLM_POOLS") == "1":
        return {}, "failed"
    sys.path.insert(0, "/opt/posthog-env")
    try:
        import llm_proxy

        events = ", ".join(list((spec.get("events") or {}).keys())[:50])
        prompt = PAGES_PROMPT.format(context=(user_text or "")[:1500] or "(none)", events=events)
        text, _ = llm_proxy.judge_complete(prompt, model, None, attempts=4, preamble=False, limit=False)
        a, b = text.find("{"), text.rfind("}")
        got = json.loads(text[a:b + 1])
        paths = [[str(x[0]), float(x[1])] for x in got.get("paths") or [] if isinstance(x, list) and len(x) == 2
                 and str(x[0]).startswith("/") and isinstance(x[1], (int, float)) and x[1] > 0]
        host = str(got.get("host") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", host):
            host = ""
        out = {"host": host, "paths": paths[:40]}
        if not paths:
            return {}, "failed"
        os.makedirs(d, exist_ok=True)
        json.dump(out, open(path + ".tmp", "w"), ensure_ascii=False, indent=1)
        os.replace(path + ".tmp", path)
        return out, "llm"
    except Exception:  # noqa: BLE001
        return {}, "failed"


REMAP_PROMPT = """You help build a realistic synthetic copy of a customer's PostHog analytics project. The generator produced
placeholder values for some properties. Replace each placeholder with a realistic, distinct value this business would
record for that property (same language/conventions as real tracking data; for PostHog's own $-properties use the real
formats PostHog SDKs send, e.g. $config_defaults like "2025-05-24" or "unset", gclid like a long Google click id).

Business context (from the customer's own question; may be in any language):
{context}

Events in the project: {events}

Placeholders per property (JSON): {placeholders}

Respond with ONLY JSON mapping each property to an object {{"<placeholder>": "<realistic value>", ...}}; every
placeholder must get a distinct value within its property."""

STEM_LETTER = re.compile(r"^([a-z][a-z0-9_]*)_([a-l])$")
TITLE_NUMBER = re.compile(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)?) (\d{1,2})$")
EXAMPLE_COMPANY = re.compile(r"^example company \d+$", re.I)
ORDINAL_WORDS = {"version", "step", "level", "tier", "season", "chapter", "round", "phase", "week", "day", "lesson",
                 "module", "episode", "part", "stage", "plan", "team", "room", "table", "floor", "gate", "slot"}


def _norm(x: str) -> str:
    return re.sub(r"[^a-z0-9]", "", x.lower())


def is_placeholder(prop: str, value: str) -> bool:
    """Generator placeholder for this property: <stem>_a..l where stem relates to the property name, "<Word> N" where
    the word relates to it ("Tag 3" for tag_name), or "example company N"."""
    if not isinstance(value, str):
        return False
    p = _norm(prop.lstrip("$"))
    m = STEM_LETTER.match(value)
    if m and (_norm(m.group(1)) in p or p in _norm(m.group(1))):
        return True
    m = TITLE_NUMBER.match(value)
    if m and _norm(m.group(1)) and _norm(m.group(1)) in p and _norm(m.group(1)) not in ORDINAL_WORDS:
        return True
    return bool(EXAMPLE_COMPANY.match(value))


def get_remap(spec: dict, root: str, placeholders: dict, user_text: str, model: str = "gpt-6.1-terra") -> tuple[dict, str]:
    """Cached {prop: {placeholder: realistic}} for a twin (rule r19)."""
    if not placeholders:
        return {}, "none"
    d = f"{root}/twins/valuepools_v2"
    path = f"{d}/{spec['id']}.remap.json"
    cached = {}
    if os.path.exists(path):
        try:
            cached = json.load(open(path))
        except ValueError:
            cached = {}
    missing = {k: [v for v in vs if v not in (cached.get(k) or {})] for k, vs in placeholders.items()}
    missing = {k: vs for k, vs in missing.items() if vs}
    if not missing:
        return cached, "cached"
    if os.environ.get("TWINGEN_NO_LLM_POOLS") == "1":
        return cached, "failed"
    sys.path.insert(0, "/opt/posthog-env")
    try:
        import llm_proxy

        events = ", ".join(list((spec.get("events") or {}).keys())[:50])
        prompt = REMAP_PROMPT.format(context=(user_text or "")[:1500] or "(none)", events=events,
                                     placeholders=json.dumps(missing, ensure_ascii=False)[:8000])
        text, _ = llm_proxy.judge_complete(prompt, model, None, attempts=4, preamble=False, limit=False)
        a, b = text.find("{"), text.rfind("}")
        got = json.loads(text[a:b + 1])
        for k, m in got.items():
            if k in missing and isinstance(m, dict):
                good = {str(o): str(n) for o, n in m.items() if o in missing[k] and str(n).strip() and not is_placeholder(k, str(n))}
                cached.setdefault(k, {}).update(good)
        os.makedirs(d, exist_ok=True)
        json.dump(cached, open(path + ".tmp", "w"), ensure_ascii=False, indent=1)
        os.replace(path + ".tmp", path)
        return cached, "llm"
    except Exception:  # noqa: BLE001
        return cached, "failed"
