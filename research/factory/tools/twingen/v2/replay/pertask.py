import sys as _sys
_sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import paths as PATHS  # noqa: E402
FID = PATHS.REPLAY_DIR

import json, re, os, collections as C
tasks=[json.loads(l) for l in open(PATHS.TASKS_DIR + "/test.jsonl")]
sqlc=json.load(open(FID + "/sql_cls.json"))
rp=[json.loads(l) for l in open(FID + "/replay.jsonl")]
ri=[json.loads(l) for l in open(FID + "/replay_ins.jsonl")]
calls=[json.loads(l) for l in open(FID + "/calls.jsonl")]
callk={(c["cid"],c["k"]):c for c in calls}
leak={"c41db8bd","01d7f8d4","3c845f97","d0a8f9c4"}
# leakage per team recomputed from leak.py output is in memory only; recompute cheaply from runs: skip, use list file if exists
def clean(u): return u.split("</voice_mode>")[-1].split("</system_reminder>")[-1].strip()
OBJURL=re.compile(r"/(notebooks|insights|dashboard|replay|feature_flags|experiments|surveys|error_tracking|cohorts|persons|person)/[A-Za-z0-9_-]+", re.I)
def num(x):
    try: return float(str(x).replace(",",""))
    except: return None
runs="/nonexistent/"
out=[]; F=C.Counter()
for t in tasks:
    cid=t["conversation_id"]; f=set()
    txt=" ".join(clean(u) for u in t["turns"])
    if OBJURL.search(txt) or any(r["cid"]==cid and r["tool"]=="read_data" and r.get("exists") is False for r in rp): f.add("object_missing")
    cl=[v for k,v in sqlc.items() if k.startswith(cid+":")]
    if "fail_dw_schema" in cl: f.add("dw_schema")
    if "empty_entity_literal" in cl: f.add("entity_literal_empty")
    if "fail_anonymization" in cl: f.add("anon_corrupted_ref")
    if "empty_abs_date" in cl: f.add("abs_date_outside_history")
    if "fail_env_access" in cl: f.add("env_access")
    cl2=[v for v in cl if v not in ("fail_anonymization","ok_empty_prod_empty")]
    if cl2 and "ok_nonempty" not in cl2: f.add("no_prod_sql_reproducible")
    if cl and not cl2: f.add("all_prod_sql_anon_corrupted")
    for r in ri:
        if r["cid"]==cid and "raw" in r:
            c=callk[(cid,r["k"])]; pnz=any((num(x) or 0)>0 for row in (c.get("rows") or []) for x in row[1:])
            if pnz and not (r["shifted"]["ok"] and (r["shifted"].get("total") or 0)>0): f.add("insight_zero")
    if any(c["cid"]==cid and c["tool"]=="search" and (c["input"] or {}).get("kind") in ("docs","business-knowledge") for c in calls): f.add("docs_dependency")
    if t.get("max_turns", 4) < len(t.get("turns_full", t["turns"])): f.add("truncated_turns")
    # rollouts of 5 models
    for m in ("qwen","k3","k3-reasoning","sonnet","opus"):
        p=runs+m+"/"+t["task_id"]+".json"
        if not os.path.exists(p): continue
        for msg in json.load(open(p))["messages"]:
            if msg.get("type")!="AssistantToolCallMessage": continue
            s=str(msg.get("content"))[:400]
            if "Documentation search is not available" in s or "Business knowledge search is not available" in s: f.add("docs_called_in_env")
            if re.search(r"(Notebook|insight|dashboard|Dashboard).{0,40}(not found|was not found)", s): f.add("object_missing")
    ntools=sum(sum(d.values()) for d in t["reference_tools"])
    if ntools==0: f.add("no_tools_in_prod")
    for x in f: F[x]+=1
    out.append((t["task_id"], sorted(f), ntools))
print("flag counts over", len(tasks), dict(F.most_common()))
HARD={"object_missing","dw_schema","no_prod_sql_reproducible","entity_literal_empty"}
SOFT={"all_prod_sql_anon_corrupted","docs_called_in_env","truncated_turns","docs_dependency","insight_zero","abs_date_outside_history","env_access","anon_corrupted_ref"}
tier=C.Counter()
res={}
for tid,f,n in out:
    fs=set(f)
    if fs & HARD: k="broken"
    elif fs & SOFT: k="partial"
    elif "no_tools_in_prod" in fs: k="faithful_no_data"
    else: k="faithful_structural"
    tier[k]+=1; res[tid]=(k,f)
print(tier)
json.dump(res, open(FID + "/pertask.json","w"))
# multi-flag overlap
print("broken reasons", C.Counter(x for k,f in res.values() if k=="broken" for x in f if x in HARD))
print("partial reasons", C.Counter(x for k,f in res.values() if k=="partial" for x in f if x in SOFT))
