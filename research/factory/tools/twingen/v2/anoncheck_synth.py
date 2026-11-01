"""Synthetic check of detection recall and repair accuracy: scramble one code span per conversation the way the
anonymizer does (_fpe: same length and character classes, memoized, replaced everywhere in the trace), then score.
Uses only conversations whose SQL the detector considers clean. Prints aggregates only."""
import json, sys, re, random, string, copy, collections as C
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import anoncheck as A
A.load_vocab("/opt/posthog-sft/env-research/twingen/v2/anoncheck_vocab.json")
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 0)

def fpe(real):
    while True:
        out = []
        for i, c in enumerate(real):
            if c.isdigit(): out.append(rng.choice("123456789" if (i == 0 or not real[i-1].isdigit()) else string.digits))
            elif c.isascii() and c.islower(): out.append(rng.choice(string.ascii_lowercase))
            elif c.isascii() and c.isupper(): out.append(rng.choice(string.ascii_uppercase))
            else: out.append(c)
        f = "".join(out)
        if f != real: return f

def spans(sql):
    toks = A.tokenize(sql); v = [t[1] for t in toks]; k = [t[0] for t in toks]; out = []
    for i in range(len(toks) - 2):
        if k[i] == "id" and v[i+1] == "." and k[i+2] == "id":
            out.append(("qual.field", sql[toks[i][2]:toks[i+2][2] + len(v[i+2])]))
        if k[i] == "id" and v[i+1] == "(" and k[i+2] == "id" and v[i].lower() in A.FUNCTIONS:
            out.append(("func(arg", sql[toks[i][2]:toks[i+2][2] + len(v[i+2])]))
        if k[i] == "id" and v[i+1].lower() == "as" and k[i+2] == "id":
            out.append(("x AS y", sql[toks[i][2]:toks[i+2][2] + len(v[i+2])]))
        if k[i] == "id" and len(v[i]) >= 5 and v[i].lower() not in A.KEYWORDS and v[i+1] != "(" and (i == 0 or v[i-1] != "."):
            out.append(("bare", v[i]))
    return [(t, s) for t, s in out if "\n" not in s and len(s) >= 4]

def sub_all(o, pat, fake):
    if isinstance(o, dict): return {k: sub_all(v, pat, fake) for k, v in o.items()}
    if isinstance(o, list): return [sub_all(v, pat, fake) for v in o]
    if isinstance(o, str): return pat.sub(fake, o)
    return o

MISS = []; WRONG = []
st = C.Counter(); bytype = C.defaultdict(C.Counter)
for l in open(sys.argv[1]):
    r = json.loads(l)
    calls = A.analyze_conversation(r["messages"])
    clean = [c for c in calls if not c["bad"]]
    if not clean or any(c["corrupted"] for c in calls): continue
    c0 = rng.choice(clean); cand = spans(c0["sql"])
    if not cand: continue
    typ, span = rng.choice(cand); fake = fpe(span)
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(span) + r"(?![A-Za-z0-9])")
    msgs = sub_all(r["messages"], pat, lambda m: fake)
    orig = {(c["tool_use_id"], c["field"]): c["sql"] for c in calls}
    new = A.analyze_conversation(msgs)
    for c in new:
        o = orig.get((c["tool_use_id"], c["field"]))
        if o is None: continue
        if o == c["sql"]:
            st["unaffected"] += 1; st["unaffected_flagged"] += c["corrupted"]; continue
        b = bytype[typ]; b["affected"] += 1; st["affected"] += 1
        if not c["corrupted"]:
            fakes = {t for k, t, _ in A.tokenize(c["sql"]) if k == "id"} - {t for k, t, _ in A.tokenize(o) if k == "id"}
            harmless = fakes and all(f.lower() in c["defined"] for f in fakes)
            b["miss_harmless" if harmless else "miss"] += 1; st["miss_harmless" if harmless else "miss"] += 1
            if not harmless and len(MISS) < 25: MISS.append((typ, sorted(fakes)[:3], c["score"], c["bad_identifiers"][:2]))
        if c["corrupted"]:
            b["detected"] += 1; st["detected"] += 1
            ft = [t for k, t, _ in A.tokenize(c["sql"])]; ot = [t for k, t, _ in A.tokenize(o)]
            truth = {a: b2 for a, b2 in zip(ft, ot) if a != b2} if len(ft) == len(ot) else {}
            for x, y in c["repairs"].items():
                if x in truth:
                    tk = "tok_ok" if truth[x] == y else "tok_wrong"; st[tk] += 1; b[tk] += 1
                    if tk == "tok_wrong" and len(WRONG) < 25: WRONG.append((typ, x, y, truth[x], c["repair_sources"].get(x)))
            if c["repaired_sql"] is not None:
                rt = [t for k, t, _ in A.tokenize(c["repaired_sql"])]
                ok = rt == ot or (len(rt) == len(ot) and all(a == b2 or a.lower() in c["defined"] for a, b2 in zip(rt, ot)))
                b["repaired_ok" if ok else "repaired_wrong"] += 1; st["repaired_ok" if ok else "repaired_wrong"] += 1
            else:
                b["not_repaired"] += 1; st["not_repaired"] += 1
print(dict(st))
d = st["detected"] or 1
print(f"recall_harmful={st['detected']/max(1,st['affected']-st['miss_harmless']):.3f} recall={st['detected']/max(1,st['affected']):.3f} repaired={(st['repaired_ok']+st['repaired_wrong'])/d:.3f} "
      f"repair_precision={st['repaired_ok']/max(1,st['repaired_ok']+st['repaired_wrong']):.3f} "
      f"token_repair_precision={st['tok_ok']/max(1,st['tok_ok']+st['tok_wrong']):.3f} fp_on_unaffected={st['unaffected_flagged']/max(1,st['unaffected']):.4f}")
for t, b in bytype.items(): print(t, dict(b))
if "-v" in sys.argv:
    for m in MISS: print("MISS", m)
    for w in WRONG: print("WRONG", w)
