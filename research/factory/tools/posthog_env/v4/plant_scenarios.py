#!/usr/bin/env python3
"""v4 planted scenarios: give clean twins an exactly known, segment-level change to investigate (fbf8).

Investigation tasks ("why did X drop, for whom, since when") are the hardest and most valuable family, but a twin
rarely contains a clean, unambiguous cause. Per twin this picks a high-volume event and a segment (browser, OS,
country, source, device or a low-cardinality custom property) holding 15-50% of that event, and plants a drop or
spike for that segment only (gen2 segment_shift), ending at the data end or in a recent past window. Writes curator-
style override files (twin dates), records the ground truth, then the caller regenerates + reloads + refreshes.

    python3 plant_scenarios.py --tasks BASE.jsonl --twins N --out DIR [--seed 11]
Writes DIR/overrides/<twin>.json and DIR/planted.jsonl ({twin_id, team_id, event, where, from, to, factor,
segment_share, baseline_daily}).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys

sys.path.insert(0, "/opt/posthog-env/runner")
sys.path.insert(0, "/opt/posthog-env")
import curate_tasks as CT  # noqa: E402

SEG_PROPS = ["$browser", "$os", "$geoip_country_code", "utm_source", "$device_type", "$referring_domain"]


def q(team: int, sql: str):
    r = CT.run_queries([{"why": "plant", "sql": sql}], team)[0]["result"]
    try:
        return json.loads(r)
    except ValueError:
        return []


def plan(task: dict, rng) -> dict | None:
    team = int(task["team_id"])
    end = dt.date.fromisoformat(str(task["loaded_now_utc"])[:10])
    evs = q(team, "SELECT event, count() AS n FROM events WHERE team_id = {team} AND timestamp > now() - INTERVAL 60 DAY "
                  "AND (event NOT LIKE '$%' OR event = '$pageview') GROUP BY event HAVING n > 1500 ORDER BY n DESC LIMIT 6")
    rng.shuffle(evs)
    for ev, n in evs:
        ev_sql = ev.replace("'", "''")
        props = list(SEG_PROPS)
        keys = q(team, f"SELECT arrayJoin(JSONExtractKeys(properties)) AS k, count() AS c FROM events WHERE team_id = {{team}} "
                       f"AND event = '{ev_sql}' AND timestamp > now() - INTERVAL 30 DAY AND NOT startsWith(k, '$') "
                       f"GROUP BY k ORDER BY c DESC LIMIT 8")
        props += [k for k, _ in keys]
        rng.shuffle(props)
        for p in props:
            p_sql = p.replace("'", "''")
            dist = q(team, f"SELECT JSONExtractString(properties, '{p_sql}') AS v, count() AS c FROM events WHERE team_id = {{team}} "
                           f"AND event = '{ev_sql}' AND timestamp > now() - INTERVAL 30 DAY GROUP BY v ORDER BY c DESC LIMIT 12")
            dist = [(v, c) for v, c in dist if v not in ("", None, "null")]
            tot = sum(c for _, c in dist)
            if len(dist) < 3 or not tot:
                continue
            cands = [(v, c / tot) for v, c in dist if 0.15 <= c / tot <= 0.5]
            if not cands:
                continue
            v, share = rng.choice(cands)
            ongoing = rng.random() < 0.6
            length = rng.randint(6, 14)
            to = end if ongoing else end - dt.timedelta(days=rng.randint(10, 25))
            fr = to - dt.timedelta(days=length - 1)
            factor = rng.choice([0.3, 0.4, 0.5]) if rng.random() < 0.75 else rng.choice([2.0, 2.5])
            return {"twin_id": task["twin_id"], "team_id": team, "event": ev, "where": {p: v}, "from": fr.isoformat(),
                    "to": to.isoformat(), "factor": factor, "segment_share": round(share, 3), "ongoing": ongoing,
                    "baseline_daily": round(n / 60, 1), "shift_days": task.get("shift_days")}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="task file with team_id/twin_id/loaded_now_utc per twin")
    ap.add_argument("--twins", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(f"{a.out}/overrides", exist_ok=True)
    seen, bases = set(), []
    for line in open(a.tasks):
        t = json.loads(line)
        if t["twin_id"] not in seen:
            seen.add(t["twin_id"])
            bases.append(t)
    rng.shuffle(bases)
    n = 0
    with open(f"{a.out}/planted.jsonl", "a") as f:
        for t in bases:
            p = plan(t, rng)
            if not p:
                continue
            op = {"kind": "segment_shift", **{k: p[k] for k in ("event", "where", "from", "to", "factor")}}
            json.dump({"twin_id": t["twin_id"], "shift_days": t.get("shift_days"), "overrides": [op]},
                      open(f"{a.out}/overrides/{t['twin_id']}.json", "w"), indent=1)
            f.write(json.dumps(p) + "\n")
            n += 1
            if n >= a.twins:
                break
    print(json.dumps({"planted": n}))


if __name__ == "__main__":
    main()
