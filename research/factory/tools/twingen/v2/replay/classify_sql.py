import sys as _sys
_sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import paths as PATHS  # noqa: E402
FID = PATHS.REPLAY_DIR

import json,re,collections as C
calls={(json.loads(l)["cid"],json.loads(l)["k"]):json.loads(l) for l in open(FID + "/calls.jsonl")}
rs=[json.loads(l) for l in open(FID + "/replay.jsonl")]
ok=[r for r in rs if r["tool"]=="execute_sql" and "raw" in r and not r["err_kind"] and r["n_rows"] is not None]
ANON={"x","g","r","eo","sub1","fdxslpjgn","mlpllhid_mm"}
teams={}
for l in open(PATHS.TASKS_DIR + "/test.jsonl"):
    t=json.loads(l); teams[t["conversation_id"]]=t
def cls(r):
    s=r["shifted"]; q=calls[(r["cid"],r["k"])]["input"]["query"]
    if not s["ok"]:
        e=s["err"]
        if e.startswith("SyntaxError") or "Unsupported function" in e: return "fail_anonymization"
        m=re.search(r"(?:resolve field|Field not found): ([A-Za-z0-9_]+)", e)
        if m and m.group(1) in ANON: return "fail_anonymization"
        if "AccessDenied" in e: return "fail_env_access"
        return "fail_dw_schema"
    zero = s["n"]==1 and all(x in ("0","None","nan","[]","","0.0") for x in s["rows"][0])
    if s["n"]>0 and not zero: return "ok_nonempty"
    if r["n_rows"]==0: return "ok_empty_prod_empty"
    lit = re.search(r"email\s*(=|ILIKE|LIKE|IN)|distinct_id\s*(=|IN)|\bid\s*=\s*\x27|\$group_\d\s*=\s*\x27|organization_id\s*=|person_id\s*=", q, re.I)
    if lit: return "empty_entity_literal"
    if r.get("has_abs_date"): return "empty_abs_date"
    return "empty_other"
c=C.Counter(cls(r) for r in ok)
for k,v in c.most_common(): print(v, f"{100*v/len(ok):.0f}%", k)
pc=C.defaultdict(list)
for r in ok: pc[r["cid"]].append(cls(r))
print("convs", len(pc))
print("per conv dominant:", C.Counter(("any_anon" if "fail_anonymization" in v else "")+("any_dw" if "fail_dw_schema" in v else "") for v in pc.values()))
json.dump({r["cid"]+":"+str(r["k"]):cls(r) for r in ok}, open(FID + "/sql_cls.json","w"))
# among non-anon queries
na=[r for r in ok if cls(r)!="fail_anonymization"]
print("excluding anonymization-corrupted:", len(na), "runs", sum(1 for r in na if r["shifted"]["ok"]), "nonempty", sum(1 for r in na if cls(r)=="ok_nonempty"))
