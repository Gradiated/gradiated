"""Deterministic, wholly synthetic reporting-product project for the existing twin loader.

Creates complete journeys rather than repairing independently sampled event streams. No model calls or
production inputs. Output is a candidate environment: query audits and independent task validation still apply.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
from pathlib import Path
import random
import uuid


UTC = dt.timezone.utc
FIRST = "Amara Anika Arjun Asha Ava Ben Clara Daniel Elena Emma Ethan Felix Grace Hana Hugo Iris Isaac Kai Leah Leo Liam Lina Luca Maya Mia Mila Noah Nora Omar Owen Priya Rosa Sara Theo Yara Zoe".split()
LAST = "Alvarez Andersson Bennett Brooks Campbell Chen Costa Das Davis Fischer Garcia Green Hansen Harris Ito Jensen Jones Khan Kim Kumar Lee Martin Miller Morgan Novak Park Patel Pereira Reed Rivera Rossi Silva Singh Smith Tanaka Taylor Thomas Wang Wilson Young".split()
PROFILES = (
    {"$os": "Windows", "$browser": "Chrome", "$browser_version": "130.0", "$device_type": "Desktop",
     "$raw_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"},
    {"$os": "Mac OS X", "$browser": "Safari", "$browser_version": "18.0", "$device_type": "Desktop",
     "$raw_user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"},
    {"$os": "Android", "$browser": "Chrome", "$browser_version": "130.0", "$device_type": "Mobile",
     "$raw_user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"},
)
COUNTRIES = (("US", "United States", "New York"), ("GB", "United Kingdom", "London"),
             ("DE", "Germany", "Berlin"), ("CA", "Canada", "Toronto"), ("AU", "Australia", "Sydney"))
DOMAINS = ("cedarworks.io", "mapleforge.co", "brightlane.io", "riverstone.design", "oakfield.studio", "larkspur.co")
SUPPORTED = ("metric_lookup", "trend_breakdown", "funnel_conversion", "retention_engagement", "anomaly_investigation",
             "attribution_marketing", "entity_lookup", "sql_help", "build_insight_dashboard", "flags_experiments",
             "llm_analytics", "warehouse", "product_howto", "tracking_quality")
CONTEXT = ("Harbor Reports is a fictional self-service reporting product for individual analysts. Each person owns "
           "one billing account; accounts are not shared teams. Free users can create and export reports; Studio "
           "subscriptions cost USD 29 per month and include AI summaries. All users in this fixture joined within "
           "the observation period. Web events carry stable identified user/device context; billing and AI "
           "generation events come from the backend. Subscription renewals are separate invoices, not new signups.")


def identifier(seed: int, *parts) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(map(str, ("harbor-reports", seed, *parts)))))


def build(seed: int, now: dt.datetime, people: int = 700, days: int = 90, split: str = "train") -> dict:
    if not 1 <= people <= len(FIRST) * len(LAST) or days < 21 or now.tzinfo is None:
        raise ValueError(f"Use 1..{len(FIRST) * len(LAST)} people, at least 21 days, and an aware UTC end time")
    if split not in ("train", "dev", "test"):
        raise ValueError("Unknown split")
    rng = random.Random(seed)
    now = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now - dt.timedelta(days=days)
    events, persons, accounts, invoices = [], [], [], []
    anomaly_start = now - dt.timedelta(days=14)
    affected = PROFILES[(seed + 2) % len(PROFILES)]

    def emit(event, time, person, props, sid=None):
        p = dict(props)
        if sid:
            p.update({"$session_id": sid, "$window_id": sid})
        events.append({"uuid": identifier(seed, "event", len(events)), "event": event, "timestamp": time,
                       "distinct_id": person["id"], "person_id": person["id"], "properties": json.dumps(p),
                       "person_properties": person["properties"], "$session_id": sid or "", "$window_id": sid or "",
                       "elements_chain": "", **{f"$group_{i}": None for i in range(5)}})

    for i in range(people):
        pid, account = identifier(seed, "person", i), identifier(seed, "account", i)
        name = FIRST[i % len(FIRST)] + " " + LAST[i // len(FIRST)]
        source = rng.choices(["google", "newsletter", "referral", "direct"], [35, 20, 20, 25])[0]
        medium = {"google": "cpc", "newsletter": "email", "referral": "referral", "direct": "direct"}[source]
        country, country_name, city = rng.choice(COUNTRIES)
        profile = dict(rng.choices(PROFILES, [55, 30, 15])[0])
        variant = "guided" if int(uuid.UUID(pid)) % 2 else "control"
        created = start + dt.timedelta(days=rng.randrange(days - 7), hours=rng.randrange(7, 16))
        activation_rate = {"google": .62, "newsletter": .76, "referral": .84, "direct": .67}[source]
        activated = rng.random() < activation_rate + (.09 if variant == "guided" else 0)
        paid_at = created + dt.timedelta(days=rng.randint(2, 9)) if activated and rng.random() < .27 else None
        if paid_at and paid_at >= now:
            paid_at = None
        email = name.lower().replace(" ", ".") + "@" + rng.choice(DOMAINS)
        pp = {"name": name, "email": email, "account_id": account, "plan": "studio" if paid_at else "free",
              "acquisition_source": source, "country": country, "onboarding_variant": variant}
        person = {"id": pid, "created_at": created, "properties": json.dumps(pp), "is_identified": True, "version": 1}
        persons.append(person)
        accounts.append({"id": account, "person_id": pid, "email": email, "name": name, "created_at": created,
                         "plan": pp["plan"], "monthly_price_usd": 29.0 if paid_at else 0.0,
                         "acquisition_source": source, "country": country})
        context = {**profile, "$lib": "web", "$device_id": identifier(seed, "device", i), "$user_id": pid,
                   "$is_identified": True, "$geoip_country_code": country, "$geoip_country_name": country_name,
                   "$geoip_city_name": city, "$feature/onboarding-guide": variant, "account_id": account}
        if paid_at:
            billing_time = paid_at
            n = 0
            while billing_time < now:
                invoice = identifier(seed, "invoice", i, n)
                invoices.append({"id": invoice, "account_id": account, "person_id": pid, "issued_at": billing_time,
                                 "amount_usd": 29.0, "currency": "USD", "status": "paid", "billing_cycle": n})
                emit("subscription_started" if n == 0 else "subscription_renewed", billing_time, person,
                     {"$lib": "posthog-python", "account_id": account, "invoice_id": invoice, "amount_usd": 29.0,
                      "currency": "USD", "plan": "studio", "billing_cycle": n})
                n += 1
                billing_time += dt.timedelta(days=30)

        day = created.date()
        while day < now.date():
            age = (day - created.date()).days
            activity = (.30 if activated else .055) * (1 if day.weekday() < 5 else .42)
            activity *= {"google": .78, "newsletter": 1.14, "referral": 1.28, "direct": .9}[source]
            activity *= max(.35, 1 - age / (days * 1.7))
            if age and rng.random() > activity:
                day += dt.timedelta(days=1)
                continue
            t = created if age == 0 else dt.datetime.combine(day, dt.time(rng.randrange(7, 19), rng.randrange(60)), UTC)
            sid = identifier(seed, "session", i, day)
            plan = "studio" if paid_at and t >= paid_at else "free"
            session = {**context, "plan": plan, "utm_source": source, "utm_medium": medium,
                       "utm_campaign": {"google": "reporting-search", "newsletter": "analyst-weekly",
                                        "referral": "member-referrals", "direct": ""}[source],
                       "$referrer": "https://www.google.com/" if source == "google" else "$direct",
                       "$referring_domain": "www.google.com" if source == "google" else "$direct"}

            def action(event, props=None, delay=10):
                nonlocal t
                t += dt.timedelta(seconds=delay)
                emit(event, t, person, {**session, **(props or {})}, sid)

            def page(path):
                session.update({"$current_url": "https://app.harborreports.io" + path,
                                "$host": "app.harborreports.io", "$pathname": path})
                action("$pageview")

            if age == 0:
                page("/signup")
                action("signup_started")
                action("signup_completed")
                action("$feature_flag_called", {"$feature_flag": "onboarding-guide", "$feature_flag_response": variant})
                page("/onboarding")
                action("onboarding_started")
                if activated:
                    action("onboarding_completed", delay=rng.randint(40, 130))
                else:
                    action("onboarding_abandoned")
                    day += dt.timedelta(days=1)
                    continue
            page("/reports")
            report_id = identifier(seed, "report", i, day)
            page("/reports/new")
            action("report_create_started", {"report_id": report_id})
            action("report_created", {"report_id": report_id, "report_type": rng.choice(["sales", "operations", "marketing"])}, delay=rng.randint(35, 100))
            if rng.random() < .70:
                page("/reports/export")
                action("report_export_started", {"report_id": report_id, "format": "pdf"})
                regression = t >= anomaly_start and profile == affected
                failed = rng.random() < (.56 if regression else .035)
                action("report_export_failed" if failed else "report_export_succeeded",
                       {"report_id": report_id, "format": "pdf", "duration_ms": rng.randint(900, 4000),
                        "error_code": "render_timeout" if failed else "", "renderer_version": "2.8" if t >= anomaly_start else "2.7"})
                if not failed:
                    page("/reports/export/success")
            if plan == "studio" and rng.random() < .7:
                request = identifier(seed, "ai", i, day)
                action("summary_requested", {"report_id": report_id, "request_id": request})
                model = "swift-small" if rng.random() < .72 else "precise-large"
                tokens_in, tokens_out = rng.randint(400, 2600), rng.randint(80, 450)
                rate = .2 if model == "swift-small" else 2.0
                cost = round((tokens_in + 4 * tokens_out) * rate / 1e6, 7)
                emit("$ai_generation", t + dt.timedelta(seconds=2), person,
                     {"$lib": "posthog-python", "account_id": account, "report_id": report_id,
                      "$ai_trace_id": request, "$ai_model": model, "$ai_provider": "harbor-inference",
                      "$ai_input_tokens": tokens_in, "$ai_output_tokens": tokens_out,
                      "$ai_total_cost_usd": cost, "$ai_input_cost_usd": round(tokens_in * rate / 1e6, 7),
                      "$ai_output_cost_usd": round(tokens_out * 4 * rate / 1e6, 7),
                      "$ai_latency": round(rng.uniform(.4, 1.5) if model == "swift-small" else rng.uniform(1.8, 4.5), 3),
                      "$ai_is_error": False})
                action("summary_generated", {"report_id": report_id, "request_id": request}, delay=6)
            day += dt.timedelta(days=1)
    events.sort(key=lambda r: (r["timestamp"], r["uuid"]))
    counts = Counter(r["event"] for r in events)
    props = defaultdict(set)
    types = {}
    for r in events:
        values = json.loads(r["properties"])
        props[r["event"]].update(values)
        for key, value in values.items():
            types[key] = "Boolean" if isinstance(value, bool) else "Numeric" if isinstance(value, (int, float)) else "String"
    definitions = {"event_definitions": [{"name": e, "last_seen_at": max(r["timestamp"] for r in events if r["event"] == e).isoformat(),
                                          "description": e.replace("_", " "), "generated_count": n} for e, n in sorted(counts.items())],
                   "property_definitions": [{"name": p, "type": 1, "property_type": types[p],
                                             "is_numerical": types[p] == "Numeric"} for p in sorted(set().union(*props.values()))]
                   + [{"name": p, "type": 2, "property_type": "String"} for p in pp],
                   "event_properties": [{"event": e, "property": p} for e, ps in props.items() for p in sorted(ps)]}
    twin_id = identifier(seed, "project")
    return {"events": events, "persons": persons, "accounts": accounts, "invoices": invoices,
            "definitions": definitions,
            "objects": {"feature_flags": [{"key": "onboarding-guide", "name": "Guided onboarding experiment",
                                            "active": True, "variants": [{"key": "control", "rollout_percentage": 50},
                                                                           {"key": "guided", "rollout_percentage": 50}]}]},
            "manifest": {"spec_id": twin_id, "spec_kind": "synthetic_scenario", "split": split,
                         "now_utc": now.isoformat(), "timezone": "UTC", "platform": "web", "seed": seed,
                         "history_days": days, "counts": {"events": len(events), "persons": len(persons)},
                         "scenario_context": CONTEXT, "supported_families": SUPPORTED},
            "ground_truth": {"kind": "synthetic", "export_regression": {"from": anomaly_start.isoformat(),
                             "segment": {"$browser": affected["$browser"], "$os": affected["$os"]}, "baseline_failure_probability": .035,
                             "changed_failure_probability": .56}, "onboarding": {"guided_probability_uplift": .09}}}


def write_project(data: dict, root: Path) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    out = root / data["manifest"]["spec_id"]
    out.mkdir(parents=True, exist_ok=True)
    fields = [pa.field(k, pa.timestamp("us", tz="UTC") if k == "timestamp" else pa.string()) for k in data["events"][0]]
    pq.write_table(pa.Table.from_pylist(data["events"], schema=pa.schema(fields)), out / "events.parquet")
    pq.write_table(pa.Table.from_pylist(data["persons"]), out / "persons.parquet")
    pq.write_table(pa.Table.from_pylist([{"distinct_id": p["id"], "person_id": p["id"], "version": 1, "is_deleted": 0}
                                       for p in data["persons"]]), out / "person_distinct_ids.parquet")
    for key in ("manifest", "definitions", "objects", "ground_truth"):
        (out / f"{key}.json").write_text(json.dumps(data[key], indent=2))
    wh = out / "warehouse"
    wh.mkdir(exist_ok=True)
    schema = {}
    for key in ("accounts", "invoices"):
        if data[key]:
            table = pa.Table.from_pylist(data[key])
            pq.write_table(table, wh / f"{key}.parquet")
            schema[key] = {"file": f"warehouse/{key}.parquet", "rows": len(data[key]),
                           "columns": [{"name": f.name} for f in table.schema]}
    (wh / "schema.json").write_text(json.dumps(schema))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=41)
    ap.add_argument("--people", type=int, default=700)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--now", required=True)
    ap.add_argument("--split", choices=("train", "dev", "test"), default="train")
    a = ap.parse_args()
    data = build(a.seed, dt.datetime.fromisoformat(a.now), a.people, a.days, a.split)
    out = write_project(data, a.out)
    print(json.dumps({"project": str(out), **data["manifest"]["counts"]}))


if __name__ == "__main__":
    main()
