import json, glob, collections, sys
D = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gam/out"
R = collections.defaultdict(dict)
for f in glob.glob(D + "/*.judge.json"):
    d = json.load(open(f)); R[d["task"]][d["variant"]] = d
def ok(d): return d.get("overall") is not None and d["overall"] >= 7.5 and d.get("material_wrong_final") == 0 and d.get("material_unsupported_final") == 0
V = ["original","minimal","hedged","padded","sycophantic","clarify_only","process_only","confident_wrong"]
print("variant n mean_overall pass_rate mean_delta_vs_orig mean_chars  mean dims(out,ev,an,pr,co)")
for v in V:
    xs = [R[t][v] for t in R if v in R[t] and "overall" in R[t][v]]
    if not xs: continue
    ds = [R[t][v]["overall"] - R[t]["original"]["overall"] for t in R if v in R[t] and "original" in R[t] and "overall" in R[t][v]]
    dims = [sum(x["capped_dims"][k] for x in xs)/len(xs) for k in ("outcome","evidence","analysis","process","communication")]
    print(f"{v:16s} {len(xs):2d} {sum(x['overall'] for x in xs)/len(xs):5.2f} {sum(ok(x) for x in xs)/len(xs):5.0%} {sum(ds)/max(1,len(ds)):+5.2f} {sum(x.get('answer_chars',0) for x in xs)/len(xs):6.0f}  " + " ".join(f"{d:.1f}" for d in dims))
print("\nper task overall (P=pass)")
print("task     " + " ".join(f"{v[:7]:>8s}" for v in V))
for t in sorted(R):
    print(t, " ".join(f"{R[t][v]['overall']:6.1f}{'P' if ok(R[t][v]) else ' '} " if v in R[t] and 'overall' in R[t][v] else "     -  " for v in V), R[t]["original"]["arm"] if "original" in R[t] else "")
print("\nflags")
for t in sorted(R):
    o = R[t].get("original")
    for v in ("clarify_only","process_only","confident_wrong"):
        if v in R[t] and ok(R[t][v]): print("SHOULD-FAIL PASSED", t, v, R[t][v]["overall"])
    if o and "minimal" in R[t] and ok(o) and not ok(R[t]["minimal"]): print("MINIMAL FAILS", t, R[t]["minimal"]["overall"], R[t]["minimal"]["material_wrong_final"], R[t]["minimal"]["material_unsupported_final"])
    for v in ("padded","hedged","sycophantic"):
        if o and v in R[t] and R[t][v]["overall"] - o["overall"] >= 0.5: print("STYLE UP", t, v, o["overall"], "->", R[t][v]["overall"])
    if o and not ok(o): print("ORIGINAL FAILS ON RESCORE", t, o["overall"], o["orig_bench_overall"])
