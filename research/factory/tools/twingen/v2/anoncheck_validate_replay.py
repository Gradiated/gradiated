"""Second view: every replayed execute_sql vs detector; prints disagreement tokens only."""
import json, sys, re, collections as C
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import anoncheck as A
A.load_vocab("/opt/posthog-sft/env-research/twingen/v2/anoncheck_vocab.json")
calls = {r["cid"] + ":" + str(r["k"]): r for r in map(json.loads, open("/tmp/fid/calls.jsonl"))}
cm = C.Counter(); dis = []
for r in map(json.loads, open("/tmp/fid/replay.jsonl")):
    k = r["cid"] + ":" + str(r["k"])
    if r["tool"] != "execute_sql" or "shifted" not in r or k not in calls: continue
    q = calls[k]["input"].get("query") or ""
    s = r["shifted"]; err = s.get("err") or ""
    d = A.analyze_sql(q)
    if s.get("ok"): lab = "ok"
    elif re.search(r"SyntaxError|Unsupported function|resolve field|Field not found", err): lab = "resolve/syntax_err"
    else: lab = "other_err"
    cm[(lab, d["corrupted"])] += 1
    m = re.search(r"(?:field|found): ([\w$]+)|call '([\w$]+)|expression: '([^']+)'", err)
    et = m and next(g for g in m.groups() if g)
    if (lab == "ok" and d["corrupted"]) or (lab == "resolve/syntax_err" and not d["corrupted"]):
        dis.append((lab, "det=" + str(d["corrupted"]), "err_tok=" + str(et), d["bad_identifiers"][:4], d["score"]))
print(sorted(cm.items()))
seen = set()
for x in dis:
    key = str(x[2:4])
    if key in seen: continue
    seen.add(key); print(x)
