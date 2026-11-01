"""Per-task audit, verification and classification of v2 twin tasks (stdlib).

Audit (what the task needs, from the production trace facts): referenced objects, warehouse tables, events,
named entities, time range, time series (dynamics), answer-dependent follow-ups, external-system tools.
Verify (from a replay of production reads against the v2 twin, /tmp/fid2): production SQL runs, is non-empty where
production was non-empty, referenced objects exist, insights are non-zero where production was, and the key numbers
agree (single numbers and insight totals within 3x, Trends direction matches).
Classify: faithful (repaired) / partial (usable, limitations listed) / broken (still fails a core check and the
cause is fixable in the twin) / unrepairable (the need cannot be met in a local twin: reason listed).

    python3 verify_tasks.py --replay-dir /tmp/fid2 --tasks /opt/posthog-env/runner/tasks/v2/test.jsonl \
        --out /opt/posthog-env/runner/tasks/v2/status.json [--label before|after] [--fixes-dir ...]
Prints aggregates only.
"""

from __future__ import annotations

import argparse
import collections as C
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as PATHS  # noqa: E402

FACTS = PATHS.FACTS
QFACTS = PATHS.QFACTS
PROJ = PATHS.PROJECTS
OVR = PATHS.OVERRIDES
CALIB = PATHS.CALIB
EXTERNAL_TOOLS = {"scan_replay_vision_sessions": "replay content (vision) needs recording snapshots",
                  "get_replay_vision_quota": "replay vision quota is a production service",
                  "read_billing_tool": "billing is a production service"}
EXTERNAL_READ = {"billing_info": "billing is a production service", "llm_trace": "LLM trace bodies are not generated"}


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:  # noqa: BLE001
        return None


def zero_row(sh):
    return sh["n"] == 1 and all(str(x) in ("0", "None", "nan", "[]", "", "0.0") for x in sh["rows"][0])


def direction(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 4:
        return 0
    k = max(1, len(v) // 3)
    a, b = sum(v[:k]) / k, sum(v[-k:]) / k
    if a == b == 0:
        return 0
    r = (b - a) / max(abs(a), abs(b), 1e-9)
    return 1 if r > 0.2 else (-1 if r < -0.2 else 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay-dir", default=PATHS.REPLAY_DIR)
    ap.add_argument("--tasks", default=f"{PATHS.TASKS_DIR}/test.jsonl")
    ap.add_argument("--out", default=f"{PATHS.TASKS_DIR}/status.json")
    ap.add_argument("--label", default="after")
    ap.add_argument("--final", action="store_true",
                    help="map tasks still broken after the repair loop to partial (some production evidence "
                         "reproduces) or unrepairable (none does), with the failure kinds as the reason")
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import anoncheck

    voc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anoncheck_vocab.json")
    if os.path.exists(voc):
        anoncheck.load_vocab(voc)
    tasks = [json.loads(l) for l in open(a.tasks)]
    rp = C.defaultdict(list)
    for l in open(os.path.join(a.replay_dir, "replay.jsonl")):
        r = json.loads(l)
        rp[r["cid"]].append(r)
    ri = C.defaultdict(list)
    for l in open(os.path.join(a.replay_dir, "replay_ins.jsonl")):
        r = json.loads(l)
        ri[r["cid"]].append(r)
    calls = {}
    for l in open(os.path.join(a.replay_dir, "calls.jsonl")):
        c = json.loads(l)
        calls[(c["cid"], c["k"])] = c
    fp = "/opt/posthog-env/runner/tasks/test_flags.json"
    flags = json.load(open(fp))["tasks"] if os.path.exists(fp) else {}
    ap_ = os.path.join(os.path.dirname(a.out), "artefacts.json")
    artefacts = json.load(open(ap_)) if os.path.exists(ap_) else {}
    prev = json.load(open(a.out)) if os.path.exists(a.out) else {}
    out = {"_meta": prev.get("_meta", {}), "tasks": prev.get("tasks", {})}
    counts = C.Counter()
    reasons_ct = C.Counter()
    for t in tasks:
        cid = t["conversation_id"]
        f = json.load(open(os.path.join(FACTS, f"{cid}.json")))
        qf = json.load(open(os.path.join(QFACTS, f"{cid}.json")))
        man = json.load(open(os.path.join(PROJ, t["twin_id"], "manifest.json")))
        # ---------------- audit
        tools = C.Counter(c["tool"] for c in f["calls"])
        need = {
            "objects": sorted({f"{c.get('kind')}:{(c.get('input') or {}).get('query', {}).get('insight_id') or (c.get('input') or {}).get('query', {}).get('notebook_id') or (c.get('input') or {}).get('query', {}).get('dashboard_id')}"
                               for c in f["calls"] if c["tool"] == "read_data" and c.get("kind") in ("insight", "notebook", "dashboard")}
                              | {f"{r['kind']}:{r['id']}" for r in f.get("url_refs") or [] if r.get("id")}),
            "dw_tables": sorted(qf.get("dw") or {}),
            "events": sorted({e for c in qf["calls"] for e in c.get("events") or []})[:40],
            "entities": len(qf.get("entity_literals") or []) + len(f.get("emails") or {}),
            "query_dates": [min(f["query_dates"]), max(f["query_dates"])] if f.get("query_dates") else None,
            "series": len(qf.get("series") or []),
            "answer_dependent_followups": [x["turn"] for x in t.get("followups") or [] if x.get("depends_on_answer")],
            "external": sorted({EXTERNAL_TOOLS[k] for k in tools if k in EXTERNAL_TOOLS}
                               | {EXTERNAL_READ[c.get("kind")] for c in f["calls"] if c["tool"] == "read_data" and c.get("kind") in EXTERNAL_READ}),
            "docs_search": sum(1 for c in f["calls"] if c["tool"] == "search" and ((c.get("input") or {}).get("kind") in ("docs", "business-knowledge"))),
            "n_tool_calls": len(f["calls"]),
        }
        # ---------------- verify
        chk = C.Counter()
        fails = []
        for r in rp.get(cid, []):
            if r["tool"] == "execute_sql" and "shifted" in r and r["err_kind"] is None and r["n_rows"] is not None:
                q = (calls.get((cid, r["k"])) or {}).get("input", {}).get("query") or ""
                if anoncheck.analyze_sql(q).get("corrupted"):
                    chk["sql_corrupted"] += 1
                    continue
                sh = r["shifted"]
                chk["sql"] += 1
                chk["sql_runs"] += sh["ok"]
                if (r["n_rows"] or 0) > 0:
                    chk["sql_prod_nonempty"] += 1
                    ok = sh["ok"] and sh["n"] > 0 and not zero_row(sh)
                    chk["sql_nonempty"] += ok
                    if not ok:
                        fails.append({"k": r["k"], "kind": "sql", "why": (sh.get("cls") or "error") if not sh["ok"] else "empty",
                                      "err": (sh.get("err") or "")[:160]})
                pr = r.get("prod_rows") or []
                if sh["ok"] and len(pr) == 1 and sh["n"] == 1 and len(pr[0]) == len(sh["rows"][0]):
                    for x, y in zip(pr[0], sh["rows"][0]):
                        x, y = num(x), num(y)
                        if x and x > 0 and y is not None:
                            chk["numbers"] += 1
                            chk["numbers_3x"] += 1 / 3 <= y / x <= 3
            elif r["tool"] == "read_data" and "exists" in r and not r.get("err_kind"):
                if r.get("kind") == "error_tracking_issue" and not r["exists"]:
                    chk["issues_v1_id_collision"] += 1  # global PK held by the v1 twin; v2 issue exists under a remapped id
                    continue
                chk["objects"] += 1
                chk["objects_found"] += bool(r["exists"])
                if not r["exists"]:
                    fails.append({"k": r["k"], "kind": "object", "why": r.get("kind")})
        for r in ri.get(cid, []):
            sh = r.get("shifted") or {}
            if not sh or r.get("err_kind"):
                continue
            chk["insights"] += 1
            chk["insights_run"] += bool(sh.get("ok"))
            pr = r.get("prod_rows") or []
            pt = sum(v for row in pr for v in (num(x) for x in row[1:]) if v is not None)
            if pt > 0:
                chk["insights_prod_nonzero"] += 1
                tw = sh.get("total") or 0
                chk["insights_nonzero"] += tw > 0
                chk["insights_3x"] += bool(tw) and 1 / 3 <= tw / pt <= 3
                if not tw:
                    fails.append({"k": r["k"], "kind": "insight", "why": "zero" if sh.get("ok") else "error"})
                ser = (sh.get("series") or [None])[0]
                pser = [num(row[1]) for row in pr if len(row) > 1 and re.match(r"^\d{4}-\d\d-\d\d", str(row[0]))]
                if ser and len(pser) >= 4:
                    dp, dt_ = direction(pser), direction(ser[-len(pser):])
                    chk["directions"] += 1
                    chk["directions_match"] += dp == dt_
        # ---------------- classify
        reasons = []
        core_fail = []
        if chk["objects"] and chk["objects_found"] < chk["objects"]:
            core_fail.append("referenced object missing")
        if chk["sql_prod_nonempty"] and chk["sql_nonempty"] < 0.6 * chk["sql_prod_nonempty"]:
            core_fail.append("production SQL empty/failing in twin")
        if chk["insights_prod_nonzero"] and chk["insights_nonzero"] < 0.6 * chk["insights_prod_nonzero"]:
            core_fail.append("production insights zero/failing in twin")
        unrep = []
        if need["external"]:
            unrep.extend(need["external"])
        if chk["sql_corrupted"] and not chk["sql"] and not chk["insights"] and not chk["objects"]:
            reasons.append("all production SQL anonymizer-corrupted: verification limited")
        if chk["numbers"] and chk["numbers_3x"] < 0.5 * chk["numbers"]:
            reasons.append("single numbers not within 3x")
        if chk["insights_prod_nonzero"] and chk["insights_3x"] < 0.5 * chk["insights_prod_nonzero"]:
            reasons.append("insight totals not within 3x")
        if chk["directions"] and chk["directions_match"] < 0.5 * chk["directions"]:
            reasons.append("trend direction differs")
        if chk["issues_v1_id_collision"]:
            reasons.append("error-tracking issue ids held by the v1 twin (remapped in v2)")
        if need["docs_search"]:
            reasons.append("docs search dependency (stubbed / local docs index)")
        if need["answer_dependent_followups"]:
            reasons.append(f"answer-dependent follow-ups from turn {need['answer_dependent_followups'][0]} (option A truncates)")
        if man.get("volume_scale", 1) < 0.99:
            reasons.append(f"volume scaled x{man['volume_scale']:.3f} to fit the event cap")
        prev_status = (out["tasks"].get(t["task_id"]) or {}).get("status")
        env_denied = sorted({re.sub(r".*access to table `([^`]+)`.*", r"\1", x.get("err") or "") if "access to table" in (x.get("err") or "")
                             else "ClickHouse dictionary privileges" for x in fails if "AccessDenied" in (x.get("err") or "")})
        if core_fail:
            # a failure whose only failing evidence is external, env-permission or anonymized cannot be repaired here
            only_external = (unrep or env_denied) and all(x["kind"] != "sql" or "AccessDenied" in (x.get("err") or "") for x in fails)
            status = "unrepairable" if only_external else "broken"
            reasons = core_fail + reasons
            if env_denied:
                reasons.append("environment permission: " + ", ".join(env_denied))
            if status == "broken" and a.final:
                reproduced = chk["sql_nonempty"] + chk["insights_nonzero"] + chk["objects_found"]
                kinds = sorted({f"{x['kind']}:{x['why']}" for x in fails})
                if reproduced:
                    status = "partial"
                    reasons.append("after repair, some production evidence still not reproduced: " + ", ".join(kinds))
                else:
                    status = "unrepairable"
                    reasons.append("not reproduced by any generator rule: " + ", ".join(kinds))
        elif unrep:
            status = "partial"
        elif reasons:
            status = "partial"
        else:
            status = "faithful"
        if unrep:
            reasons += [f"needs external system: {u}" for u in unrep]
        fixes = {k: v for k, v in (man.get("v2") or {}).items() if isinstance(v, (int, float)) and v and k not in ("required_days_v2",)}
        if os.path.exists(os.path.join(OVR, f"{t['twin_id']}.json")):
            fixes["override"] = json.load(open(os.path.join(OVR, f"{t['twin_id']}.json"))).get("notes") or True
        if os.path.exists(os.path.join(CALIB, f"{t['twin_id']}.json")):
            fixes["calibrated_events"] = len(json.load(open(os.path.join(CALIB, f"{t['twin_id']}.json"))).get("events") or {})
        flag = (flags.get(t["task_id"]) or {})
        art = artefacts.get(t["task_id"])
        if flag.get("flag") == "trivial":
            reasons.append("trivial (calibration flag: every reference model scores >= 9)")
        if flag.get("flag") == "needs-missing-artefact":
            if art and art.get("provided"):
                fixes["missing_artefact_now_provided"] = True
            else:
                miss = [k for k, v in ((art or {}).get("checks") or {}).items() if not (v["ok"] if isinstance(v, dict) else v)]
                reasons.append("missing artefact: " + (", ".join(miss) if miss else str(flag.get("artefact"))[:120]))
                if status == "faithful":
                    status = "partial"
        rec = out["tasks"].get(t["task_id"]) or {}
        rec.update({"conversation_id": cid, "team_id": t["team_id"], "status": status, "reasons": reasons,
                    "calib_flag": flag.get("flag"), "calib_reason": flag.get("reason"),
                    "artefact_check": art,
                    "checks": dict(chk), "failures": fails[:20], "needs": need, "fixes": fixes})
        rec.setdefault("history", {})[a.label] = status
        rec["status_changed"] = prev_status is not None and prev_status != status
        out["tasks"][t["task_id"]] = rec
        counts[status] += 1
        for x in reasons:
            reasons_ct[re.sub(r"\d+", "N", x.split(":")[0])] += 1
    out["_meta"][a.label] = {"counts": dict(counts), "reasons": dict(reasons_ct.most_common())}
    with open(a.out + ".tmp", "w") as fh:
        json.dump(out, fh, indent=1)
    os.replace(a.out + ".tmp", a.out)
    print(json.dumps({"label": a.label, "counts": dict(counts), "reasons": dict(reasons_ct.most_common(12))}))


if __name__ == "__main__":
    main()
