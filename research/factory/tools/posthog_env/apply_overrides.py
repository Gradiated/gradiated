#!/usr/bin/env python3
"""Apply curation twin overrides to the generator's per-conversation overrides (runs on fbf8, system python).

The editor writes overrides in twin dates (what the agent sees); the generator works in production dates and the
loader shifts by shift_days. This converts and merges them into <root>/twins/overrides_v2/<conversation_id>.json:
  event_multiplier -> "events": {event: factor} (multiplied into an existing factor)
  spike            -> "spikes": [{event, from, to, factor}] (dates minus shift_days; replaces a spike on the same
                      event and start date)
  history_days     -> "history_days": max(existing, n)
  new_event / sequence / event_props / person_props -> "scenario": [op, ...] (dates shifted)
  warehouse_table  -> "warehouse": {table: {column: {type, values}}}
Records the source ("curation") per entry. Prints the conversation ids changed (for regenerate + reload).

    python3 apply_overrides.py --overrides-dir B/curated/overrides --root /opt/posthog-sft/env-research/twins_loop
"""

import argparse
import copy
import datetime as dt
import glob
import json
import os


SCENARIO_KINDS = ("new_event", "sequence", "event_props", "person_props")


def shift(d: str, days: int) -> str:
    return (dt.date.fromisoformat(d[:10]) - dt.timedelta(days=days)).isoformat()


def merge(cur: dict, ovs: list[dict], shift_days: int) -> dict:
    # deep copy: a shallow copy shared the nested scenario/events containers with the caller's dict, so main()'s
    # `new != cur` compared two mutated objects and never wrote a second set of overrides (round 8: all 28 repair
    # overrides were dropped silently)
    cur = copy.deepcopy(cur)
    for o in ovs:
        k = o.get("kind")
        if k == "event_multiplier" and o.get("event") and o.get("factor") is not None:
            ev = cur.setdefault("events", {})
            ev[o["event"]] = float(ev.get(o["event"], 1.0)) * float(o["factor"])
        elif k == "spike" and o.get("event") and o.get("from"):
            sp = {"event": o["event"], "from": shift(o["from"], shift_days), "to": shift(o.get("to") or o["from"], shift_days),
                  "factor": float(o.get("factor", 3.0)), "source": "curation"}
            cur["spikes"] = [x for x in cur.get("spikes") or [] if not (x.get("event") == sp["event"] and x.get("from") == sp["from"])] + [sp]
        elif k == "history_days" and o.get("days"):
            cur["history_days"] = max(int(cur.get("history_days") or 0), int(o["days"]))
        elif k in SCENARIO_KINDS:  # r21: scenario data the request needs (generator: gen2.scenario_*)
            op = {kk: v for kk, v in o.items()}
            for f in ("from", "to"):
                if op.get(f):
                    op[f] = shift(op[f], shift_days)
            op["source"] = "curation"
            if op not in (cur.get("scenario") or []):
                cur.setdefault("scenario", []).append(op)
        elif k == "warehouse_table" and o.get("table") and isinstance(o.get("columns"), dict):
            wh = cur.setdefault("warehouse", {})
            wh.setdefault(o["table"], {}).update(o["columns"])
    cur.setdefault("notes", []).append("curation overrides merged")
    return cur


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overrides-dir", required=True)
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    od = f"{a.root}/twins/overrides_v2"
    os.makedirs(od, exist_ok=True)
    changed = []
    for f in sorted(glob.glob(f"{a.overrides_dir}/*.json")):
        d = json.load(open(f))
        cid = d["twin_id"]
        path = f"{od}/{cid}.json"
        cur = json.load(open(path)) if os.path.exists(path) else {}
        new = merge(cur, d.get("overrides") or [], int(d.get("shift_days") or 0))
        if new != cur:
            json.dump(new, open(path, "w"), indent=1)
            changed.append(cid)
    print(",".join(changed))


if __name__ == "__main__":
    main()
