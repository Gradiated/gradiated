#!/usr/bin/env python3
"""Twin regression tests: regenerate listed conversations with the current code and check assertions on the output.

Every defect found in an environment spot check becomes one or more assertions here, so a later change cannot
silently bring it back. Cases reference real (anonymized) conversations, so the cases file stays on the GPU host:
/opt/posthog-sft/env-research/regression/cases.json (the repo holds this runner only).

    cd /opt/posthog-sft/env-research/twingen/v2 && python3 tests/regress.py [--cases FILE] [--only PREFIX] [--keep]

Per data root used by the cases, a scratch root under /tmp/regress/<name> symlinks the root's specs, facts, clusters,
xindex, overrides, targets and calibration, and holds fresh qfacts (current qfacts.py) and projects (current gen2.py).
Assertions read the generated files directly (production-dated events; no loading):

  {"type": "count", "event": E, "props": {k: v}, "from": D, "to": D, "op": "<=", "value": N}
  {"type": "ratio", "num": {count spec}, "den": {count spec}, "op": ">=", "value": X}
  {"type": "weekly_uniques", "event": E, "from": D, "to": D, "stat": "median"|"min"|"max", "op": ">=", "value": N}
  {"type": "prop_coverage", "event": E, "prop": P, "op": ">=", "value": share}
  {"type": "funnel", "steps": [E1, E2, ...], "from": D, "to": D, "max_ratio": [r12, r23, ...]}  (step i+1 persons
      <= r * step i persons, persons doing the steps in order)
  {"type": "object", "kind": "insights"|"dashboards"|"notebooks", "id": X, "present": true|false}
      (optional "min_tiles": n for dashboards, "query_kind": K for insights: the object's real definition)
  {"type": "history", "from": D, "op": ">=", "value": N}    (events on or before D; checks the twin covers D)
  {"type": "distinct", "event": E, "props": {..}, "prop": P, "op": "<=", "value": N}  (distinct values of P)
  {"type": "session_first_pageview", "op": ">=", "value": share}
  {"type": "parent_before_child", "parent": E1, "child": E2, "op": ">=", "value": share}  (persons doing E2 who did
      E1 earlier)
  {"type": "per_person", "event": E, "op": "<=", "value": n}  (max events per person)
  {"type": "uniq_ratio", "num_event": E, "den_event": E2|null, "op": "<=", "value": r}  (persons doing E / persons
      doing E2, or any event)  (web sessions whose first event is a $pageview)
  {"type": "lint", "check": C, "severity": "material"|"minor"|null, "op": "<=", "value": 0}  (lint.py findings of
      check C on the generated twin)
A props value starting with "~" matches as a substring ("~/gamelanding/"). Dates are production dates (YYYY-MM-DD,
inclusive). Prints one line per assertion and a summary; exit 1 on failure.
"""

from __future__ import annotations

import argparse
import collections as C
import datetime as dt
import glob
import json
import operator
import os
import subprocess
import sys

V2 = "/opt/posthog-sft/env-research/twingen/v2"
TG = "/opt/posthog-sft/env-research/twingen"
PH = "/opt/posthog-env/posthog"
CASES = "/opt/posthog-sft/env-research/regression/cases.json"
ROOTS = {"reanon": "/opt/posthog-sft/env-research/twins_reanon", "loop": "/opt/posthog-sft/env-research/twins_loop"}
TRACES = "/opt/posthog-sft/env-research/twins_reanon/traces"
OPS = {"<=": operator.le, ">=": operator.ge, "<": operator.lt, ">": operator.gt, "==": operator.eq}


def scratch(name: str) -> str:
    src, dst = ROOTS[name], f"/tmp/regress/{name}"
    os.makedirs(f"{dst}/twins/qfacts_v2", exist_ok=True)
    os.makedirs(f"{dst}/twingen", exist_ok=True)
    for rel in ("twins/specs", "twins/facts_v2", "twins/clusters", "twins/xindex_v2.json", "twins/overrides_v2",
                "twins/index.jsonl", "twingen/targets.jsonl", "twingen/calib_v2"):
        if os.path.exists(f"{src}/{rel}") and not os.path.lexists(f"{dst}/{rel}"):
            os.symlink(f"{src}/{rel}", f"{dst}/{rel}")
    return dst


def regenerate(name: str, ids: list[str], splits: str) -> str:
    root = scratch(name)
    env = {**os.environ, "TWIN_V2_ROOT": root, "TWIN_V2_TRACES": TRACES, "TWIN_V2_TAG": f"regress{name}"}
    csv = ",".join(ids)
    subprocess.run([f"{PH}/.venv/bin/python", f"{V2}/qfacts.py", "--split", splits, "--ids", csv,
                    "--out", f"{root}/twins/qfacts_v2"], cwd=PH, env=env, check=True, capture_output=True)
    import shutil

    for i in ids:  # never evaluate a previous run's output when this generation fails
        shutil.rmtree(f"{root}/projects/{i}", ignore_errors=True)
    r = subprocess.run([f"{TG}/.venv/bin/python", f"{V2}/run_all2.py", "--ids", csv, "--workers", "4",
                        "--out", f"{root}/projects"], env=env, check=True, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("FAIL"):
            print(f"GENERATION {line[:300]}")
    return f"{root}/projects"


class Twin:
    def __init__(self, d: str):
        import pyarrow.parquet as pq

        t = pq.read_table(f"{d}/events.parquet", columns=["event", "timestamp", "person_id", "properties"])
        self.ev = t.column("event").to_pylist()
        self.ts_full = t.column("timestamp").to_pylist()
        self.ts = [x.date() for x in self.ts_full]
        self.pid = t.column("person_id").to_pylist()
        self.props = t.column("properties").to_pylist()
        self.objects = json.load(open(f"{d}/objects.json")) if os.path.exists(f"{d}/objects.json") else {}
        self.dir = d
        self._pj = {}

    def p(self, i: int) -> dict:
        if i not in self._pj:
            try:
                self._pj[i] = json.loads(self.props[i] or "{}")
            except ValueError:
                self._pj[i] = {}
        return self._pj[i]

    def rows(self, event=None, props=None, a=None, b=None):
        a = dt.date.fromisoformat(a) if a else None
        b = dt.date.fromisoformat(b) if b else None
        for i, e in enumerate(self.ev):
            if event and e != event:
                continue
            if (a and self.ts[i] < a) or (b and self.ts[i] > b):
                continue
            if props and any((str(v)[1:] not in str(self.p(i).get(k, ""))) if str(v).startswith("~")
                             else str(self.p(i).get(k)) != str(v) for k, v in props.items()):
                continue
            yield i

    def count(self, c: dict) -> int:
        return sum(1 for _ in self.rows(c.get("event"), c.get("props"), c.get("from"), c.get("to")))


def check(tw: Twin, a: dict) -> tuple[bool, str]:
    t = a["type"]
    if t == "count":
        v = tw.count(a)
        return OPS[a["op"]](v, a["value"]), f"count={v}"
    if t == "ratio":
        n, d = tw.count(a["num"]), tw.count(a["den"])
        r = n / d if d else float("inf") if n else 0.0
        return OPS[a["op"]](r, a["value"]), f"ratio={r:.3f} ({n}/{d})"
    if t == "weekly_uniques":
        wk = C.defaultdict(set)
        for i in tw.rows(a.get("event"), a.get("props"), a.get("from"), a.get("to")):
            wk[tw.ts[i].isocalendar()[:2]].add(tw.pid[i])
        vals = sorted(len(s) for s in wk.values()) or [0]
        v = {"median": vals[len(vals) // 2], "min": vals[0], "max": vals[-1]}[a.get("stat", "median")]
        return OPS[a["op"]](v, a["value"]), f"weekly_uniques_{a.get('stat', 'median')}={v} over {len(wk)} weeks"
    if t == "prop_coverage":
        ii = list(tw.rows(a["event"], None, a.get("from"), a.get("to")))
        if not ii:
            return False, "no events"
        v = sum(1 for i in ii if tw.p(i).get(a["prop"]) not in (None, "")) / len(ii)
        return OPS[a["op"]](v, a["value"]), f"coverage={v:.2f} of {len(ii)}"
    if t == "funnel":
        steps = a["steps"]
        first = {}
        for k, e in enumerate(steps):
            for i in tw.rows(e, None, a.get("from"), a.get("to")):
                key = (tw.pid[i], k)
                if key not in first or tw.ts[i] < first[key]:
                    first[key] = tw.ts[i]
        reached = [0] * len(steps)
        for pid in {p for p, _ in first}:
            t0 = None
            for k in range(len(steps)):
                tk = first.get((pid, k))
                if tk is None or (t0 is not None and tk < t0):
                    break
                reached[k] += 1
                t0 = tk
        ok = all(reached[k + 1] <= r * reached[k] for k, r in enumerate(a["max_ratio"]) if k + 1 < len(reached))
        return ok and reached[0] > 0, f"funnel={reached}"
    if t == "object":
        objs = {str(o.get("short_id") or o.get("dashboard_id") or o.get("key")): o for o in tw.objects.get(a["kind"], [])}
        have = str(a["id"]) in objs
        if not have or "query_kind" not in a and "min_tiles" not in a:
            return have == a["present"], f"present={have}"
        o = objs[str(a["id"])]
        if "min_tiles" in a:
            n = len(o.get("tile_short_ids") or [])
            return n >= a["min_tiles"], f"tiles={n}"
        q = o.get("query_full") or {}
        kind = (q.get("source") or {}).get("kind") if q.get("kind") in ("InsightVizNode", "DataVisualizationNode") else q.get("kind")
        return kind == a["query_kind"], f"query_kind={kind}"
    if t == "distinct":
        vals = {str(tw.p(i).get(a["prop"])) for i in tw.rows(a.get("event"), a.get("props"), a.get("from"), a.get("to"))
                if tw.p(i).get(a["prop"]) not in (None, "")}
        return OPS[a["op"]](len(vals), a["value"]), f"distinct={len(vals)} {sorted(vals)[:5]}"
    if t == "session_first_pageview":
        first = {}
        for i in range(len(tw.ev)):
            sid = tw.p(i).get("$session_id") if tw.ev[i] in ("$pageview", "$autocapture", "$pageleave", "$identify") else None
            if sid and (sid not in first or tw.ts_full[i] < tw.ts_full[first[sid]]):
                first[sid] = i
        pv = [tw.ev[i] == "$pageview" for i in first.values()]
        v = sum(pv) / max(1, len(pv))
        return OPS[a["op"]](v, a["value"]), f"share_first_pageview={v:.2f} of {len(pv)} sessions"
    if t == "uniq_ratio":
        num = {tw.pid[i] for i in tw.rows(a["num_event"], None, a.get("from"), a.get("to"))}
        den = {tw.pid[i] for i in tw.rows(a.get("den_event"), None, a.get("from"), a.get("to"))}
        r = len(num) / max(1, len(den))
        return OPS[a["op"]](r, a["value"]), f"uniq_ratio={r:.2f} ({len(num)}/{len(den)})"
    if t == "parent_before_child":
        first_parent = {}
        for i in tw.rows(a["parent"], None, a.get("from"), a.get("to")):
            if tw.pid[i] not in first_parent or tw.ts_full[i] < first_parent[tw.pid[i]]:
                first_parent[tw.pid[i]] = tw.ts_full[i]
        kids = {}
        for i in tw.rows(a["child"], None, a.get("from"), a.get("to")):
            if tw.pid[i] not in kids or tw.ts_full[i] < kids[tw.pid[i]]:
                kids[tw.pid[i]] = tw.ts_full[i]
        ok = sum(1 for p_, t_ in kids.items() if p_ in first_parent and first_parent[p_] <= t_)
        v = ok / max(1, len(kids))
        return OPS[a["op"]](v, a["value"]), f"share_child_persons_with_prior_parent={v:.2f} of {len(kids)}"
    if t == "per_person":
        c = C.Counter(tw.pid[i] for i in tw.rows(a["event"], None, a.get("from"), a.get("to")))
        v = max(c.values()) if c else 0
        return OPS[a["op"]](v, a["value"]), f"max_per_person={v} over {len(c)} persons"
    if t == "lint":
        sys.path.insert(0, V2)
        import lint

        if not hasattr(tw, "_lint"):
            tw._lint = lint.lint_project(tw.dir)["findings"]
        hits = [f for f in tw._lint if f["check"] == a["check"] and (a.get("severity") in (None, f["severity"]))]
        return OPS[a.get("op", "<=")](len(hits), a.get("value", 0)), f"lint_{a['check']}={len(hits)} " + \
            "; ".join(f["detail"][:80] for f in hits[:2])
    if t == "history":
        v = sum(1 for d in tw.ts if d <= dt.date.fromisoformat(a["from"]))
        return OPS[a["op"]](v, a["value"]), f"events_on_or_before={v}"
    raise ValueError(t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=CASES)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    cases = [c for c in json.load(open(a.cases)) if c["id"].startswith(a.only)]
    groups = C.defaultdict(list)
    for c in cases:
        groups[(c["root"], c["split"])].append(c)
    fails = n = 0
    for (root, split), cs in groups.items():
        full = {}
        for c in cs:
            m = glob.glob(f"{ROOTS[root]}/twins/specs/{c['conv']}*.json")
            if len(m) != 1:
                print(f"SKIP {c['id']}: conversation {c['conv']} not found uniquely")
                continue
            full[c["conv"]] = os.path.basename(m[0])[:-5]
        proj = regenerate(root, sorted(set(full.values())), split)
        for c in cs:
            if c["conv"] not in full:
                continue
            d = f"{proj}/{full[c['conv']]}"
            if not os.path.exists(f"{d}/events.parquet"):
                n += 1
                fails += 1
                print(f"FAIL {c['id']}: generation failed (no output)")
                continue
            tw = Twin(d)
            for j, asr in enumerate(c["asserts"]):
                n += 1
                ok, info = check(tw, asr)
                fails += not ok
                print(f"{'PASS' if ok else 'FAIL'} {c['id']}#{j} {asr['type']}: {info}  ({asr.get('why', '')[:90]})")
    print(json.dumps({"assertions": n, "failed": fails}))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
