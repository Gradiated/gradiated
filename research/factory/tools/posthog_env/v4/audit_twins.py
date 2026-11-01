#!/usr/bin/env python3
"""v4 twin audit: audit each twin's data ONCE before tasks are authored on it (fbf8).

Synthesized tasks probe a twin's data deeply, so twin defects (not task defects) decide whether tasks survive
(v4 pilot 1: 0/28; nearly all "data_implausible"). An auditor model explores the twin with read-only queries and
reports implausibilities an analyst would notice, with severity. Twins with a material defect are excluded from
authoring; minor defects are passed to the author ("avoid"); all findings feed generator fixes.

    python3 audit_twins.py --base BASE.jsonl --out DIR [--workers 6] [--model claude-opus-5-5]
Writes DIR/<twin_id>.json and DIR/audit.jsonl ({twin_id, team_id, verdict: CLEAN|MINOR|MATERIAL, defects}).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import audit_contracts as AC
from reference_queries import normalize_team

sys.path.insert(0, "/opt/posthog-env/runner")
sys.path.insert(0, "/opt/posthog-env")
import curate_tasks as CT  # noqa: E402
import llm_proxy  # noqa: E402
import spot_card as SC  # noqa: E402

PROMPT = """You audit the data of a synthetic PostHog analytics project that will host evaluation tasks for an analytics
agent. Find what an experienced analyst would notice as implausible or inconsistent when analysing this product.
Be concrete and verify with queries; do not report things that are plausible for a real product.

## Project (data ends at {now})
{twin}

## Objects
{objects}

Check at least: page journeys (completion/thank-you/success pages after their start pages; entry pages first),
event funnels and lifecycles (later steps by people who did earlier steps, once-only events not repeated), reach
(custom events used by plausible shares of people), identity (emails unique per person, no placeholder names/domains
like userN@example.com or example-N.com used as real data), device/SDK coherence ($lib vs $os vs $device_type, app
metadata only on native apps, $screen only from mobile SDKs), ids (order/transaction/session ids not shared by
unrelated people), attribution (utm_source/medium/campaign and referrer agree), entity consistency (an order/account
keeps its attributes across events), time series (no unexplained one-day bursts or gaps), warehouse tables (join to
events/persons), and values (realistic domains and magnitudes).

Explore with {{"queries": [{{"why": "...", "sql": "..."}}]}} (at most 8 per round, up to 5 rounds). Every query must
contain `team_id = {{team}}`; tables: events(team_id, event, timestamp, distinct_id, person_id, properties),
person(team_id, id, properties), session_replay_events(team_id, session_id, ...), warehouse('<name>').

Final answer, ONLY JSON:
{{"verdict": "CLEAN|MINOR|MATERIAL",
 "defects": [{{"severity": "material|minor", "area": "journeys|funnels|reach|identity|device|ids|attribution|entities|time|warehouse|values|other",
              "what": "<concrete>", "evidence": "<query -> result>", "events": ["<event or page involved>"]}}],
 "summary": "<one sentence>"}}
MATERIAL = an analyst doing common analyses on this product would hit it and doubt the data; MINOR = real but
confined to something peripheral."""


def audit(base: dict, model: str, out: str) -> dict:
    path = f"{out}/{base['twin_id']}.json"
    if os.path.exists(path):
        try:
            cached = json.loads(Path(path).read_text())
            if AC.reusable(cached, base, model):
                return cached
        except (OSError, ValueError):
            pass
    twin = "\n".join(str(x) for x in SC.twin_state(base) + SC.event_props(base))
    prompt = PROMPT.format(now=base.get("loaded_now_utc"), twin=SC.clip(twin, 24000),
                           objects=SC.clip(SC.team_objects(base["team_id"]), 3000))
    rec = {"twin_id": base["twin_id"], "team_id": base["team_id"], "queries_run": [], "model": model,
           "snapshot": AC.snapshot(base), "cache_key": AC.cache_key(base, model)}
    convo, rounds = prompt, 0
    for _ in range(10):
        try:
            text, _u = llm_proxy.judge_complete(convo, model, None, attempts=2, timeout=120, preamble=False)
            d = json.loads(text[text.find("{"):text.rfind("}") + 1])
            if d.get("queries") and "verdict" not in d and rounds < 5:
                rounds += 1
                qs = [{**q, "sql": normalize_team(q.get("sql", ""), int(base["team_id"]))}
                      for q in d["queries"][:8]]
                res = CT.run_queries(qs, int(base["team_id"]))
                rec["queries_run"] += res
                rec["rounds"] = rounds
                Path(path + ".tmp").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
                os.replace(path + ".tmp", path)
                convo += (f"\n\n## Results (round {rounds})\n" +
                          "\n".join(f"- {r['why']}\n  SQL: {r['sql']}\n  -> {r['result']}" for r in res) +
                          ("\n\nNow give the final JSON." if rounds >= 5 else "\n\nQuery more or give the final JSON."))
                continue
            if AC.valid_verdict(d) and AC.completed({**rec, **d, "error": None}):
                rec.update({k: d[k] for k in ("verdict", "defects", "summary") if k in d})
                rec.pop("error", None)
                break
            convo += "\n\nReturn a consistent verdict and concrete query evidence for every defect. " \
                     "Query the project before giving a final verdict."
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            if isinstance(e, RuntimeError):
                break
    if not rec.get("verdict"):
        rec.setdefault("error", "No complete, evidence-backed verdict")
    Path(path + ".tmp").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    os.replace(path + ".tmp", path)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    seen, bases = set(), []
    for line in open(a.base):
        t = json.loads(line)
        if t["twin_id"] not in seen:
            seen.add(t["twin_id"])
            bases.append(t)
    with ThreadPoolExecutor(a.workers) as pool, open(f"{a.out}/audit.jsonl", "w") as f:
        futures = [pool.submit(audit, b, a.model, a.out) for b in bases]
        for future in as_completed(futures):
            r = future.result()
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
    rows = [json.loads(x) for x in open(f"{a.out}/audit.jsonl")]
    print(json.dumps({"twins": len(rows), "verdicts": {v: sum(1 for r in rows if r.get("verdict") == v)
                                                       for v in ("CLEAN", "MINOR", "MATERIAL", None)}}))


if __name__ == "__main__":
    main()
