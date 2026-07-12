#!/usr/bin/env python3
"""One-at-a-time sensitivity of the moat study outputs (co-design gain,
synergy) to the most uncertain parameters. Output: range, not a point."""
import sys, copy
sys.path.insert(0, 'experiments')
import moat_study as M

def evaluate(mod):
    base = copy.deepcopy(M.BASE); mod_base = mod.get('base', lambda c: c)
    b_cfg = mod_base(base); b_cfg["serving"]["max_batch"] = M.kv_batch(b_cfg, 22)
    B = M.run_quiet(b_cfg)[0]
    s_cfg = M.apply_surgery(b_cfg)
    if 'surgery' in mod: mod['surgery'](s_cfg)
    s_cfg["serving"]["max_batch"] = M.kv_batch(s_cfg, 19)
    S = M.run_quiet(s_cfg)[0]
    asic_mod = mod.get('asic', lambda c: c)
    h_cfg = M.apply_asic(b_cfg); asic_mod(h_cfg); H = M.run_quiet(h_cfg)[0]
    sh_cfg = M.apply_asic(s_cfg); asic_mod(sh_cfg); SH = M.run_quiet(sh_cfg)[0]
    return B/S, B/H, B/SH, (B/SH)/((B/S)*(B/H))

def set_base(path, val):
    def f(c):
        d = c
        for k in path[:-1]: d = d[k]
        d[path[-1]] = val
        return c
    return f

CASES = [
 ("baseline (as studied)", {}),
 ("EP imbalance 1.4 (better EPLB)", {'base': set_base(["parallel","ep_imbalance"],1.4)}),
 ("EP imbalance 2.2 (worse)",       {'base': set_base(["parallel","ep_imbalance"],2.2)}),
 ("comm overlap 0.6 (worse)",       {'base': set_base(["parallel","comm_overlap"],0.6)}),
 ("H800 kernels better (0.7/0.7)",  {'base': lambda c: (c["kernel"].update(gemm_peak_efficiency=0.7, attn_bw_efficiency=0.7), c)[1]}),
 ("cache hit 0.80",                 {'base': set_base(["serving","prefix_cache_hit"],0.80)}),
 ("cache hit 0.95",                 {'base': set_base(["serving","prefix_cache_hit"],0.95)}),
 ("locality weak 0.8 (granite evidence)", {'surgery': lambda c: c["model"].update(expert_locality=0.8)}),
 ("no CLA latent share (fails heal)",     {'surgery': lambda c: c["model"].update(kv_share_layers=1)}),
 ("no head prune (fails heal)",           {'surgery': lambda c: c["model"].update(heads=64)}),
 ("HBM stack $2.5k",  {'asic': lambda c: c["hardware"].update(unit_cost_usd=c["hardware"]["unit_cost_usd"] + 700*round(c["hardware"]["mem_capacity_gb"]/24))}),
 ("die+board $10k (NRE @20k units)", {'asic': lambda c: c["hardware"].update(unit_cost_usd=c["hardware"]["unit_cost_usd"]+3000)}),
 ("ASIC kernels only GPU-grade",    {'asic': lambda c: c["kernel"].update(gemm_peak_efficiency=0.65, attn_bw_efficiency=0.7)}),
 ("ASIC util 0.7 (not 0.85)",       {'asic': lambda c: c["cost"].update(utilization=0.7)}),
 ("ASIC fabric 100GB/s only",       {'asic': lambda c: c["hardware"].update(interconnect_gbs=100.0)}),
]
print(f"{'case':<38} {'S':>6} {'H':>6} {'S+H':>6} {'synergy':>8}")
rows=[]
for name, mod in CASES:
    gs, gh, gsh, syn = evaluate(mod)
    rows.append((name, gs, gh, gsh, syn))
    print(f"{name:<38} {gs:>5.2f}x {gh:>5.2f}x {gsh:>5.2f}x {syn:>7.2f}")
g = [r[3] for r in rows]; sy = [r[4] for r in rows]
print(f"\nco-design gain range: {min(g):.1f}x - {max(g):.1f}x (base {rows[0][3]:.1f}x)")
print(f"synergy range:        {min(sy):.2f} - {max(sy):.2f} (base {rows[0][4]:.2f})")
