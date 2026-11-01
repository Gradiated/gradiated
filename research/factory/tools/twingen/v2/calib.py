"""Volume calibration for v2 twins from a replay of production reads (stdlib).

Input: replay output of production queries against the loaded v2 twins (replay.jsonl for execute_sql,
replay_ins.jsonl for create_insight; see /tmp/fid2), qfacts_v2 and teams_v2.jsonl. For every twin, each replayed
query that refers to exactly one event and returned a production number gives a ratio production/twin:
- Trends insights with one series (sum of the series over the date range);
- SQL with one event filter and a single-row numeric result (first numeric cell).
The multiplier per event is the geometric median of its ratios, clamped to [1/30, 30]; a twin value of 0 against a
positive production value counts as ratio 30. With --existing DIR, multipliers compound on an earlier calibration.

    python3 calib.py --replay /tmp/fid2/replay.jsonl --replay-ins /tmp/fid2/replay_ins.jsonl --out calib_v2
Writes OUT/<twin_id>.json ({"events": {event: multiplier}, "n": {event: n_ratios}}). Prints aggregates only.
"""

from __future__ import annotations

import argparse
import collections as C
import json
import math
import os
import statistics
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as PATHS  # noqa: E402

QFACTS = PATHS.QFACTS
TEAMS_V2 = PATHS.TEAMS
LO, HI = 1 / 30, 30.0


def num(x):
    try:
        s = str(x).replace(",", "").strip()
        return float(s)
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--replay-ins", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--existing", default=None)
    a = ap.parse_args()
    twin_of = {}
    for l in open(TEAMS_V2):
        r = json.loads(l)
        if not r.get("removed"):
            for cid in r.get("members") or []:
                twin_of[cid] = r["twin_id"]
    ratios: dict = C.defaultdict(lambda: C.defaultdict(list))
    for l in open(a.replay_ins):
        r = json.loads(l)
        sh = r.get("shifted") or {}
        evs = (r.get("acc") or {}).get("events") or []
        if not sh.get("ok") or len(evs) != 1 or r.get("qkind") != "TrendsQuery":
            continue
        prod = sum(v for row in r.get("prod_rows") or [] for v in (num(x) for x in row[1:]) if v is not None)
        twin = sh.get("total") or 0
        if prod > 0:
            ratios[r["cid"]][evs[0]].append(HI if twin <= 0 else prod / twin)
    for l in open(a.replay):
        r = json.loads(l)
        if r.get("tool") != "execute_sql" or "shifted" not in r:
            continue
        sh = r["shifted"]
        qf_path = os.path.join(QFACTS, f"{r['cid']}.json")
        evs = (r.get("ents") or {}).get("events") or []
        if not sh.get("ok") or len(evs) != 1 or (r.get("ents") or {}).get("dw"):
            continue
        pr = r.get("prod_rows") or []
        if len(pr) != 1 or not pr[0]:
            continue
        pv = next((num(x) for x in pr[0] if num(x) is not None), None)
        if not pv or pv <= 0:
            continue
        tv = None
        if sh.get("n") == 1 and sh.get("rows"):
            tv = next((num(x) for x in sh["rows"][0] if num(x) is not None), None)
        elif sh.get("n") == 0:
            tv = 0
        if tv is None:
            continue
        ratios[r["cid"]][evs[0]].append(HI if tv <= 0 else pv / tv)
        _ = qf_path
    os.makedirs(a.out, exist_ok=True)
    st = C.Counter()
    allm = []
    for cid, evr in ratios.items():
        twin = twin_of.get(cid)
        if not twin:
            continue
        prev = {}
        if a.existing and os.path.exists(os.path.join(a.existing, f"{twin}.json")):
            prev = json.load(open(os.path.join(a.existing, f"{twin}.json"))).get("events") or {}
        ev = {}
        for e, rs in evr.items():
            m = math.exp(statistics.median(math.log(min(HI, max(LO, x))) for x in rs))
            m = min(HI, max(LO, m * prev.get(e, 1.0)))
            if abs(math.log(m)) > math.log(1.25):
                ev[e] = round(m, 4)
                allm.append(m)
        for e, m in prev.items():
            ev.setdefault(e, m)
        if ev:
            with open(os.path.join(a.out, f"{twin}.json"), "w") as f:
                json.dump({"events": ev, "n": {e: len(rs) for e, rs in evr.items()}}, f)
            st["twins"] += 1
            st["events"] += len(ev)
    if allm:
        s = sorted(allm)
        st["mult_p10_x100"] = int(100 * s[len(s) // 10])
        st["mult_p50_x100"] = int(100 * s[len(s) // 2])
        st["mult_p90_x100"] = int(100 * s[9 * len(s) // 10])
    print(json.dumps(dict(st)))


if __name__ == "__main__":
    main()
