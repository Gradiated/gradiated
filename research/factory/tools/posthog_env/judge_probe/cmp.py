import json, glob, collections
def load(D):
    R = collections.defaultdict(dict)
    for f in glob.glob(D + "/*.judge.json"):
        d = json.load(open(f)); R[d["task"]][d["variant"]] = d
    return R
def ok(d): return d.get("overall") is not None and d["overall"] >= 7.5 and d.get("material_wrong_final") == 0 and d.get("material_unsupported_final") == 0
H, I = load("/tmp/gam/out"), load("/tmp/gam/out_v3i")
V = ["original","minimal","hedged","padded","sycophantic","clarify_only","process_only","confident_wrong"]
print("variant  h_mean h_pass | i_mean i_pass i_dDelta | i_fad_false  i_out")
for v in V:
    h=[H[t][v] for t in H]; i=[I[t][v] for t in I]
    di=sum(I[t][v]["overall"]-I[t]["original"]["overall"] for t in I)/len(I)
    print(f"{v:16s} {sum(x['overall'] for x in h)/20:5.2f} {sum(map(ok,h))/20:4.0%} | {sum(x['overall'] for x in i)/20:5.2f} {sum(map(ok,i))/20:4.0%} {di:+5.2f} | {sum(x.get('final_answer_delivers') is False for x in i):2d}  {sum(x['capped_dims']['outcome'] for x in i)/20:.1f}")
print("\nper task v3h -> v3i")
for t in sorted(I):
    print(t, " ".join(f"{H[t][v]['overall']:4.1f}{'P' if ok(H[t][v]) else ' '}>{I[t][v]['overall']:4.1f}{'P' if ok(I[t][v]) else ' '}" for v in V))
print("\nflags v3i")
for t in sorted(I):
    for v in ("clarify_only","process_only","confident_wrong"):
        if ok(I[t][v]): print("SHOULD-FAIL PASS", t, v, I[t][v]["overall"], I[t][v].get("final_answer_delivers"))
    for v in ("original","minimal","hedged","padded","sycophantic"):
        d=I[t][v]
        if not ok(d) or d.get("final_answer_delivers") is False:
            print("FAIL/NONDELIVER", t, v, d["overall"], "fad=",d.get("final_answer_delivers"), d["material_wrong_final"], d["material_unsupported_final"], d["capped_dims"])
            print("   O:", d["outcome"]["reason"][:230]); print("   E:", [(e["severity"][:3],e["kind"][:5],e["what"][:110]) for e in d["errors"] if e["severity"]=="material"])
    for v in ("padded","hedged","sycophantic"):
        if I[t][v]["overall"]-I[t]["original"]["overall"]>=0.5: print("STYLE UP", t, v, I[t]["original"]["overall"], "->", I[t][v]["overall"])
o=[I[t]["original"]["overall"]-H[t]["original"]["overall"] for t in I]
b=[I[t]["original"]["overall"]-I[t]["original"]["orig_bench_overall"] for t in I]
print("\nnoise: v3i orig - v3h orig rescore: mean %+.2f mean|d| %.2f max %+.2f" % (sum(o)/20, sum(map(abs,o))/20, max(o,key=abs)))
print("noise: v3i orig - bench v3h: mean %+.2f mean|d| %.2f max %+.2f" % (sum(b)/20, sum(map(abs,b))/20, max(b,key=abs)))
for v in V:
    dd=[I[t][v]["overall"]-H[t][v]["overall"] for t in I]
    print(v, "v3i-v3h mean %+.2f mean|d| %.2f" % (sum(dd)/20, sum(map(abs,dd))/20))
