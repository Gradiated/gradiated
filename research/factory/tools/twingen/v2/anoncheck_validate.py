"""Validate anoncheck against the /tmp/fid replay labels (noisy reference). Prints aggregates and short tokens only."""
import json, sys, collections as C
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import anoncheck as A
A.load_vocab("/opt/posthog-sft/env-research/twingen/v2/anoncheck_vocab.json")
use_known = "--known" in sys.argv
cls = json.load(open("/tmp/fid/sql_cls.json"))
calls = {r["cid"] + ":" + str(r["k"]): r for r in map(json.loads, open("/tmp/fid/calls.jsonl"))}
rs = {r["cid"] + ":" + str(r["k"]): r for r in map(json.loads, open("/tmp/fid/replay.jsonl"))}
specs = {}
def known(cid):
    if not use_known: return None
    if cid not in specs:
        try: specs[cid] = A.known_from_spec(json.load(open(f"/opt/posthog-sft/env-research/twins/specs/{cid}.json")))
        except FileNotFoundError: specs[cid] = None
    return specs[cid]
tp = fp = fn = tn = 0
dis = []
other = C.Counter()
for k, lab in cls.items():
    q = calls[k]["input"]["query"]
    r = A.analyze_sql(q, known(calls[k]["cid"]))
    pos = lab == "fail_anonymization"
    if lab in ("fail_dw_schema", "fail_env_access"):
        other[(lab, r["corrupted"])] += 1
        if r["corrupted"]: dis.append(("dw?", lab, r["bad_identifiers"][:5], r["reasons"]))
        continue
    if pos and r["corrupted"]: tp += 1
    elif pos: fn += 1; dis.append(("FN", rs[k]["shifted"]["err"][:70], r["bad_identifiers"][:5], r["score"]))
    elif r["corrupted"]: fp += 1; dis.append(("FP", lab, r["bad_identifiers"][:5], r["reasons"]))
    else: tn += 1
print(f"known={use_known} tp={tp} fp={fp} fn={fn} tn={tn} precision={tp/max(1,tp+fp):.3f} recall={tp/max(1,tp+fn):.3f}")
print("excluded labels:", dict(other))
# replay-wide: all execute_sql with resolution errors (not just sql_cls subset)
for d in dis: print(d)
