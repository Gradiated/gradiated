#!/usr/bin/env python3
"""Monte Carlo moat study: compound uncertainty + surgery-lever pass/fail.

Models the auto-research reality: each surgery lever has a probability of
surviving quality evals (the loop only ships survivors); baseline stack
parameters, ASIC costs, and kernel quality are drawn from ranges. Output is
the DISTRIBUTION of gains, which is the honest answer to "will this work".
Ratios are quoted (realization/duty factors cancel; see docs/calibration.md).
"""
import sys, copy, random, json
sys.path.insert(0, 'experiments')
import moat_study as M

random.seed(7)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120

def sample_case(rng):
    base = copy.deepcopy(M.BASE)
    base["parallel"]["ep_imbalance"] = rng.uniform(1.4, 2.2)
    base["parallel"]["comm_overlap"] = rng.uniform(0.65, 0.85)
    base["kernel"]["gemm_peak_efficiency"] = rng.uniform(0.55, 0.70)
    base["kernel"]["attn_bw_efficiency"] = rng.uniform(0.50, 0.70)
    base["serving"]["prefix_cache_hit"] = rng.uniform(0.80, 0.95)

    levers = {}
    levers["int4"] = rng.random() < 0.90
    levers["fp8kv"] = rng.random() < 0.95
    levers["cla"] = rng.random() < 0.50
    levers["prune"] = rng.random() < 0.60
    levers["locality"] = rng.uniform(0.55, 0.85) if rng.random() < 0.60 else 1.0
    levers["asym"] = rng.random() < 0.50
    levers["dsa"] = int(rng.uniform(1024, 1536)) if rng.random() < 0.70 else 2048

    asic = {
        "die_board": rng.uniform(6000, 10000),
        "stack_cost": rng.uniform(1400, 2400),
        "gemm": rng.uniform(0.65, 0.80),
        "attn": rng.uniform(0.75, 0.90),
        "util": rng.uniform(0.70, 0.90),
        "fabric": rng.uniform(100, 250),
    }
    return base, levers, asic

def surgery_with(cfg, lv):
    c = copy.deepcopy(cfg)
    m = c["model"]
    if lv["int4"]: m["weight_bytes"] = 0.55
    if lv["fp8kv"]: m["kv_bytes"] = 1.0
    if lv["cla"]: m["kv_share_layers"] = 2
    m["expert_locality"] = lv["locality"]
    if lv["asym"]: m["prefill_top_k"] = 4
    if lv["prune"]: m["heads"] = 48
    m["sparse_attention"] = {"index_top_k": lv["dsa"]}
    return c

def fit_asic(cfg, a):
    best = None
    for n in range(2, 9):
        c = M.asic_variant(cfg, n)
        c["hardware"]["unit_cost_usd"] = a["die_board"] + a["stack_cost"] * n + 1000.0
        c["hardware"]["interconnect_gbs"] = a["fabric"]
        c["kernel"]["gemm_peak_efficiency"] = a["gemm"]
        c["kernel"]["attn_bw_efficiency"] = a["attn"]
        c["cost"]["utilization"] = a["util"]
        headroom = M.weights_per_chip_gb(c["model"], c["parallel"]["ep"]) + 4.0
        if c["hardware"]["mem_capacity_gb"] - headroom < 5.0:
            continue
        c["serving"] = dict(c["serving"], max_batch=M.kv_batch(c, headroom))
        cost = M.run_quiet(c)[0]
        if best is None or cost < best[0]:
            best = (cost, n)
    return best

rows = []
for i in range(N):
    rng = random.Random(1000 + i)
    base, lv, asic = sample_case(rng)
    b_cfg = copy.deepcopy(base); b_cfg["serving"]["max_batch"] = M.kv_batch(b_cfg, 22)
    B = M.run_quiet(b_cfg)[0]
    s_cfg = surgery_with(b_cfg, lv); s_cfg["serving"]["max_batch"] = M.kv_batch(s_cfg, 19)
    S = M.run_quiet(s_cfg)[0]
    H, hn = fit_asic(b_cfg, asic)
    SH, shn = fit_asic(s_cfg, asic)
    gs, gh, gsh = B / S, B / H, B / SH
    rows.append({"gs": gs, "gh": gh, "gsh": gsh, "syn": gsh / (gs * gh),
                 "stacks_vanilla": hn, "stacks_surgered": shn, "levers": lv})
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{N} samples", file=sys.stderr)

def pct(v, p):
    s = sorted(v); return s[int(p / 100 * (len(s) - 1))]

for key, name in [("gs", "surgery gain"), ("gh", "hardware gain"),
                  ("gsh", "co-design gain"), ("syn", "synergy")]:
    v = [r[key] for r in rows]
    print(f"{name:<16} P10 {pct(v,10):.2f}  median {pct(v,50):.2f}  P90 {pct(v,90):.2f}")
g = [r["gsh"] for r in rows]
for t in [2, 3, 4, 5, 6.5]:
    print(f"P(co-design gain >= {t}x) = {sum(1 for x in g if x >= t)/len(g):.2f}")
syn = [r["syn"] for r in rows]
print(f"P(synergy > 1) = {sum(1 for x in syn if x > 1)/len(syn):.2f}")
dn = [r["stacks_vanilla"] - r["stacks_surgered"] for r in rows]
print(f"P(surgered chip needs fewer HBM stacks) = {sum(1 for x in dn if x > 0)/len(dn):.2f}")
with open("experiments/results/moat-mc.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
