#!/usr/bin/env python3
"""Deterministic, CPU-only queue/economic bound for the admitted W4 geometry."""
import argparse, hashlib, json, math, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
W4 = ROOT.parent / "gemma_l40s_w4_c16_economic_bound" / "W4_C16_BOUND_V2.json"
SAT = ROOT.parent / "l40s_saturation_economic_gate" / "SATURATION_GATE.json"

SEED = 20260717
N = 8000
WINDOWS = (0.0, 0.05, 0.10, 0.25, 0.50, 1.0, 2.0)
ARRIVAL_MULTIPLIERS = (0.25, 0.40, 0.55, 0.70, 0.80, 0.90, 0.97)
NONLINEAR = (0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.0)
BURST_SHAPES = {"smooth": 50.0, "moderate_burst": 4.0, "bursty": 1.5}

def load():
    w, s = json.loads(W4.read_text()), json.loads(SAT.read_text())
    return w, s

def p95(xs):
    if not xs: return None
    xs = sorted(xs); return xs[min(len(xs)-1, math.ceil(.95*len(xs))-1)]

def simulate(c, rate, window, nonlinear, burst_shape, seed, seconds=0.0):
    """One FIFO single-worker batch server; arrival rate is requests/s."""
    w, _ = load(); phase = w["phase_bound"]
    prefill, decode = phase["prefill_floors_primary_s"]["selected_floor"], phase["decode_batch_wall_s"]["W4"]
    # Explicit optimistic non-GEMM terms. Cache reads reduce attention work only.
    fixed = 0.018 * (1 - .127) + 0.010 * (1 + 358/4214) + 0.008 + 0.006
    # The swept term is a per-request nonlinear scheduler/attention/sampling tail;
    # it grows with occupancy and is intentionally not credited to GEMM floors.
    def service(b):
        return prefill + decode + b * (fixed + nonlinear * (b/c) ** 1.35)
    rng = random.Random(seed)
    arrivals, t = [], 0.0
    # Gamma renewal process: shape=large is smooth, low shape is bursty.
    while len(arrivals) < N:
        t += rng.gammavariate(burst_shape, 1.0/(burst_shape*rate))
        arrivals.append(t)
    q, i, now, done, waits, batches, busy = [], 0, 0.0, [], [], [], 0.0
    while i < N or q:
        if not q:
            now = max(now, arrivals[i])
            while i < N and arrivals[i] <= now:
                q.append(i); i += 1
        first = arrivals[q[0]]
        deadline = first + window
        while i < N and len(q) < c and arrivals[i] <= deadline:
            q.append(i); i += 1
        b = min(c, len(q)); ids, q = q[:b], q[b:]
        start = max(now, deadline if len(ids) < c else now)
        if start > now: now = start
        dur = service(b); busy += dur; now += dur
        for idx in ids:
            waits.append(now - arrivals[idx]); done.append(now)
        batches.append(b)
    horizon = max(done) - min(arrivals)
    throughput = N / horizon
    p50, p95v = sorted(waits)[N//2], p95(waits)
    return {"p50_s": p50, "p95_s": p95v,
            "throughput_req_s": throughput, "mean_batch": sum(batches)/len(batches),
            "full_batch_fraction": sum(b == c for b in batches)/len(batches),
            "idle_fraction": max(0.0, 1 - busy/horizon),
            "stable": throughput >= rate * .97 and p95v < 120.0,
            "arrival_rate_req_s": rate, "batches": len(batches), "n": N}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "QUEUE_BOUND.json")); args = ap.parse_args()
    w, sat = load(); cap = w["capacity"]; phase = w["phase_bound"]
    factors = sat["scenario_factors"]; prices = [1.00, 1.10, 1.25]
    base_rate = {"c8": phase["service_floor_by_concurrency"]["W4_req_s"]["c8"],
                 "c16": phase["service_floor_by_concurrency"]["W4_req_s"]["c16"],
                 "c32": phase["service_floor_by_concurrency"]["W4_req_s"]["c32"]}
    rows=[]
    for cname, c in (("c8",8),("c16",16),("c32",32)):
      for burst, shape in BURST_SHAPES.items():
       for mult in ARRIVAL_MULTIPLIERS:
        for win in WINDOWS:
         for nl in NONLINEAR:
          r = simulate(c, base_rate[cname]*mult, win, nl, shape, SEED+c*1000+int(win*100)+int(nl*1000))
          cost = {}
          for scenario, f in factors.items():
            all_in = math.prod(v for k, v in f.items() if k != "utilization") / f["utilization"]
            cost[scenario] = {str(p): p/3600/all_in/r["throughput_req_s"] for p in prices}
          rows.append({"c":c,"name":cname,"burst":burst,"arrival_multiplier":mult,"window_s":win,
                       "nonlinear_s_per_req_at_full_batch":nl,"memory_primary_gib":cap["w4_primary_totals_gib"][cname],
                       "memory_10k_gib":cap["w4_10k_totals_gib"][cname],"memory_10k_allocator_sensitive":c==32,**r,"cost_usd_per_request":cost})
    # Analytic maximum nonlinear term at full batch for each all-in market hurdle.
    hurdles = {"planning": sat["target_costs_usd_per_request"]["WandB"],
               "conservative": sat["target_costs_usd_per_request"]["WandB"]}
    max_nl={}
    for cname,c in (("c8",8),("c16",16),("c32",32)):
      out={}
      for scen,f in factors.items():
       mult=math.prod(v for k, v in f.items() if k != "utilization")/f["utilization"]
       target=hurdles["planning"] if scen=="planning_base" else hurdles["conservative"]
       req_s=1.10/3600*mult/target
       max_service=c/req_s
       fixed=0.018*(1-.127)+.010*(1+358/4214)+.008+.006
       nl=max(0.0,(max_service-phase["prefill_floors_primary_s"]["selected_floor"]-phase["decode_batch_wall_s"]["W4"])/c-fixed)
       out[scen]=round(nl,6)
      max_nl[cname]=out
    # Distinct 10K check: no queue claim; capacity/allocator screen only.
    tenk={k:{"total_gib":cap["w4_10k_totals_gib"][k],"headroom_gib":cap["w4_10k_headroom_gib"][k],
             "fit_status":"allocator_sensitive" if k=="c32" else "logical_fit"} for k in ("c8","c16","c32")}
    result={"schema_version":1,"evidence_type":"deterministic_cpu_discrete_event_and_analytic_bound",
      "seed":SEED,"events":N,"inputs":{"w4_sha256":hashlib.sha256(W4.read_bytes()).hexdigest(),"saturation_sha256":hashlib.sha256(SAT.read_bytes()).hexdigest(),
      "mix":{"input_tokens":4214,"output_tokens":358,"cache_read_fraction":.127},"phase_floors_s":{"prefill":phase["prefill_floors_primary_s"]["selected_floor"],"decode_batch":phase["decode_batch_wall_s"]["W4"]},
      "explicit_overhead_s":{"attention_cache_adjusted":.018*(1-.127),"kv_head":.010*(1+358/4214),"scheduler":.008,"sampling":.006},"arrival_process":"gamma renewal; fixed seed; burst shapes smooth=50, moderate=4, bursty=1.5"},
      "capacity_10k_check":tenk,"max_nonlinear_s_per_request_at_full_batch":max_nl,"rows":rows}
    Path(args.out).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"rows":len(rows),"out":args.out,"max_nonlinear":max_nl,"10k":tenk},indent=2))

if __name__ == "__main__": main()
