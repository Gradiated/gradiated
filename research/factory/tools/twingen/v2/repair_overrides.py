"""Replay-driven repairs written as declarative per-twin overrides (stdlib).

Rules (each turns a replay failure into an override entry in twins/overrides_v2/<twin_id>.json; gen2 applies them):
- schema completion: "Unable to resolve field: X" on an uncorrupted production query over warehouse tables adds
  column X (type from its name) to the query's warehouse table (the single one, or every one when ambiguous);
- history: a production query that is empty only because it reaches before the twin's history extends history_days.
Existing override entries are kept; every entry records its source call in `notes`.

    python3 repair_overrides.py --replay /tmp/fid2/replay.jsonl
Prints aggregates only.
"""

from __future__ import annotations

import argparse
import collections as C
import datetime as dt
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as PATHS  # noqa: E402

OVR = PATHS.OVERRIDES
PROJ = PATHS.PROJECTS
TEAMS_V2 = PATHS.TEAMS
UNRES = re.compile(r"Unable to resolve field: ([A-Za-z_][A-Za-z0-9_]*)")


def col_type(name: str) -> str:
    n = name.lower()
    if re.search(r"(_at|_date|_time|^date|month|week|day|period|quarter_start)$", n) or n in ("date", "month", "week"):
        return "datetime"
    if re.search(r"amount|price|cost|revenue|mrr|arr|usd|rate|pct|percent|score|value|total|sum|avg", n):
        return "float"
    if re.search(r"(^n_|_count$|count|num_|qty|quantity|seats|days$)", n):
        return "integer"
    if re.match(r"^(is|has|was)_", n):
        return "integer"
    return "string"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import anoncheck

    voc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anoncheck_vocab.json")
    if os.path.exists(voc):
        anoncheck.load_vocab(voc)
    twin_of = {}
    for l in open(TEAMS_V2):
        r = json.loads(l)
        if not r.get("removed"):
            for cid in r.get("members") or []:
                twin_of[cid] = r["twin_id"]
    calls = {}
    cp = os.path.join(os.path.dirname(a.replay), "calls.jsonl")
    for l in open(cp):
        c = json.loads(l)
        calls[(c["cid"], c["k"])] = c
    os.makedirs(OVR, exist_ok=True)
    st = C.Counter()
    per: dict = C.defaultdict(lambda: {"warehouse": {}, "notes": []})
    for l in open(a.replay):
        r = json.loads(l)
        if r.get("tool") != "execute_sql" or "shifted" not in r or r.get("err_kind") is not None:
            continue
        twin = twin_of.get(r["cid"])
        if not twin:
            continue
        sh = r["shifted"]
        q = (calls.get((r["cid"], r["k"])) or {}).get("input", {}).get("query") or ""
        if anoncheck.analyze_sql(q).get("corrupted"):
            continue
        dw = (r.get("ents") or {}).get("dw") or []
        if not sh.get("ok") and dw:
            m = UNRES.search(sh.get("err") or "")
            if m:
                col = m.group(1)
                for t in dw:
                    per[twin]["warehouse"].setdefault(t, {})[col] = {"type": col_type(col)}
                per[twin]["notes"].append(f"schema: {col} from call {r['k']}")
                st["schema_columns"] += 1
        elif sh.get("ok") and sh.get("n") == 0 and (r.get("n_rows") or 0) > 0 and r.get("has_abs_date"):
            man = json.load(open(os.path.join(PROJ, twin, "manifest.json")))
            ds = sorted(set(re.findall(r"'(\d{4}-\d\d-\d\d)", q)))
            if ds:
                now = dt.datetime.fromisoformat(man["now_utc"].replace("Z", "+00:00")).date()
                need = (now - dt.date.fromisoformat(ds[0])).days + 7
                if need > man["history_days"] and need <= 800:
                    per[twin]["history_days"] = max(per[twin].get("history_days", 0), need)
                    per[twin]["notes"].append(f"history: {need} days from call {r['k']}")
                    st["history_extended"] += 1
    for twin, o in per.items():
        p = os.path.join(OVR, f"{twin}.json")
        cur = json.load(open(p)) if os.path.exists(p) else {}
        for t, cols in o["warehouse"].items():
            cur.setdefault("warehouse", {}).setdefault(t, {}).update(cols)
        if o.get("history_days"):
            cur["history_days"] = max(cur.get("history_days") or 0, o["history_days"])
        cur["notes"] = sorted(set((cur.get("notes") or []) + o["notes"]))
        with open(p, "w") as f:
            json.dump(cur, f, indent=1)
        st["twins"] += 1
    print(json.dumps(dict(st)))


if __name__ == "__main__":
    main()
