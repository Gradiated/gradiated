#!/usr/bin/env python3
"""GLM-5.2 moat study: does model-surgery+finetune x hardware co-design beat
provider-best generic serving by more than the two do independently?

Tiers:
  B      provider-best GENERIC serving of vanilla GLM-5.2 (H800, SGLang-class:
         grouped MoE kernels, prefill packing, MTP, DSA, fp8, cache 0.90, EP
         overlap+imbalance). Everything here is available to any provider.
  B+S    + model SURGERY with finetune healing (rented H800s unchanged):
         int4 experts (QAT-healed), expert-locality routing finetune,
         cross-layer latent sharing, asymmetric prefill top-k, head prune,
         per-layer DSA profile. Each requires model access + eval/heal infra.
  B+H    + fitted ASIC for the VANILLA model (no surgery).
  B+S+H  co-designed: surgered model on silicon fitted to its traffic map.

Moat metrics: gains vs B; synergy = gain(S+H) / (gain(S) * gain(H)).
Note: absolute $/Mtok inherits sim idealizations (peak-duty, see anchors);
RATIOS are the trustworthy output — both sides share the idealizations.
"""
import json, subprocess, copy, sys

BASE = {
 "model": {"name":"glm-5.2","layers":78,"hidden":6144,"heads":64,"kv_heads":64,"head_dim":192,
  "intermediate":12288,"vocab":154880,"tied_embeddings":False,"weight_bytes":1.0,"kv_bytes":2.0,
  "mtp_accept":0.7,
  "attention":{"mla":{"kv_lora_rank":512,"qk_rope_dim":64,"q_lora_rank":2048,"qk_nope_head_dim":192,"v_head_dim":256}},
  "ffn":{"moe":{"experts":256,"top_k":8,"shared_experts":1,"moe_intermediate":2048,"first_k_dense":3}},
  "sparse_attention":{"index_top_k":2048}},
 "hardware": {"name":"h800","tflops":1979.0,"mem_bw_gbs":3350.0,"mem_capacity_gb":80.0,
  "dispatch_us":3.0,"step_sync_us":100.0,"tdp_w":700.0,"unit_cost_usd":30000.0,
  "interconnect_gbs":50.0,"interconnect_latency_us":50.0},
 "kernel": {"name":"sglang-cuda","dispatches_per_layer":8.0,"dispatches_fixed":20.0,
  "gemm_peak_efficiency":0.6,"gemm_occupancy_half_cells":5e3,"attn_bw_efficiency":0.6,
  "unfused_activation_traffic":0.05,"grouped_moe":True},
 "serving": {"name":"provider-best","max_batch":72,"prefill_chunk":4096,"sched_overhead_us":500.0,
  "per_token_host_us":1.0,"prefix_cache_hit":0.90,"prefill_packing":True,"sampling":"device"},
 "workload": {"name":"agent-8k-400","num_requests":2048,"input_len":8000,"output_len":400},
 "parallel": {"tp":1,"ep":144,"act_bytes":1.0,"comm_overlap":0.75,"ep_imbalance":1.8},
 "cost": {"amortization_months":36.0,"utilization":0.7,"power_usd_per_kwh":0.09,"pue":1.25,"system_overhead_frac":0.25},
}

def kv_batch(cfg, headroom_gb, cap=512):
    m = cfg["model"]
    kvtok = ((m["attention"]["mla"]["kv_lora_rank"]+m["attention"]["mla"]["qk_rope_dim"])
             * m["kv_bytes"] * m["layers"] / m.get("kv_share_layers",1))
    avg_ctx = cfg["workload"]["input_len"] + cfg["workload"]["output_len"]/2
    return min(int((cfg["hardware"]["mem_capacity_gb"]-headroom_gb)*1e9/(kvtok*avg_ctx)), cap)

def toml_of(cfg):
    def emit(d, prefix=""):
        lines=[]; tables=[]
        for k,v in d.items():
            if v is None: continue
            if isinstance(v,dict): tables.append((k,v))
            elif isinstance(v,bool): lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v,str): lines.append(f'{k} = "{v}"')
            else: lines.append(f"{k} = {float(v) if isinstance(v,float) else v}")
        out = (f"[{prefix}]\n" if prefix else "") + "\n".join(lines) + "\n"
        for k,v in tables: out += emit(v, f"{prefix}.{k}" if prefix else k)
        return out
    return emit(cfg)

def run(cfg, label):
    open('/tmp/moat.toml','w').write(toml_of(cfg))
    r = subprocess.run(['./target/release/sartor','run','--config','/tmp/moat.toml'],capture_output=True,text=True)
    if r.returncode:
        print(label, "ERR", r.stderr[-400:]); sys.exit(1)
    d = json.loads(r.stdout)
    c = d['cost']['usd_per_mtok_output']
    print(f"{label:<58} {d['perf']['output_tok_per_s']:>7.0f} tok/s/GPU  ${c:.3f}/Mtok  batch {d['perf']['avg_decode_batch']:.0f}")
    return c

def apply_surgery(cfg):
    """Model modifications requiring finetune-healing. Quality evidence tiers
    noted per lever; twin experiments (real surgery on local models) ground
    the head-prune and locality claims."""
    c = copy.deepcopy(cfg)
    m = c["model"]
    m["name"] = "glm-5.2-surgered"
    m["weight_bytes"] = 0.55        # int4 experts, QAT-healed (Kimi-K2 ships int4)
    m["kv_bytes"] = 1.0             # fp8 latent (near-lossless in literature)
    m["kv_share_layers"] = 2        # CLA-on-latent, healed (halves KV + kv_down)
    m["expert_locality"] = 0.5      # routing-locality finetune (placeholder until twin stats)
    m["prefill_top_k"] = 4          # asymmetric prompt routing, healed
    m["heads"] = 48                 # weakest 25% heads pruned + healed
    m["sparse_attention"] = {"index_top_k":1024}  # per-layer DSA profile (avg)
    return c

def asic_variant(cfg, n_stacks):
    """Parametric family ASIC: fp8-only die + n HBM3e stacks. BOM: ~750mm2 N4
    die+package+board ~$6k with NRE amortized (50k units), $1.8k per 24GB/
    1.2TBps HBM3e stack, $1k scale-up fabric. Fitting = argmin over n_stacks."""
    c = copy.deepcopy(cfg)
    c["hardware"] = {"name":f"glm-asic-{n_stacks}stk","tflops":1400.0,
        "mem_bw_gbs":1200.0*n_stacks,"mem_capacity_gb":24.0*n_stacks,
        "dispatch_us":2.0,"step_sync_us":50.0,"tdp_w":300.0+40.0*n_stacks,
        "unit_cost_usd":7000.0+1800.0*n_stacks,
        "interconnect_gbs":200.0,"interconnect_latency_us":5.0}
    c["parallel"] = dict(c["parallel"], ep=16, comm_overlap=0.85, ep_imbalance=1.4)
    c["kernel"] = dict(c["kernel"], name="asic-native", dispatches_per_layer=3.0,
        gemm_peak_efficiency=0.8, gemm_occupancy_half_cells=1e3, attn_bw_efficiency=0.9,
        unfused_activation_traffic=0.0)
    c["cost"] = dict(c["cost"], utilization=0.85)
    return c

def run_quiet(cfg):
    open('/tmp/moat.toml','w').write(toml_of(cfg))
    r = subprocess.run(['./target/release/sartor','run','--config','/tmp/moat.toml'],capture_output=True,text=True)
    if r.returncode: print("ERR", r.stderr[-300:]); sys.exit(1)
    d = json.loads(r.stdout)
    return d['cost']['usd_per_mtok_output'], d['perf']['output_tok_per_s'], d['perf']['avg_decode_batch']

def weights_per_chip_gb(m, ep):
    """GLM-5.2 family: ~705B expert params (sharded over EP) + ~39B
    attn+dense+embed+MTP (replicated per chip)."""
    return (705.0/ep + 39.0) * m["weight_bytes"]

def apply_asic(cfg):
    """Fit the chip to THIS model variant: argmin $/Mtok over stack count.
    The discrete cliff is real: weights/chip must fit before any KV does."""
    best = None
    for n in range(2, 9):
        c = asic_variant(cfg, n)
        headroom = weights_per_chip_gb(c["model"], c["parallel"]["ep"]) + 4.0  # + workspace
        cap = c["hardware"]["mem_capacity_gb"]
        if cap - headroom < 5.0:
            continue
        c["serving"] = dict(c["serving"], max_batch=kv_batch(c, headroom))
        cost, tps, batch = run_quiet(c)
        if best is None or cost < best[0]:
            best = (cost, tps, batch, n, c)
    cost, tps, batch, n, c = best
    print(f"    fitted ASIC: {n} HBM stacks ({24*n}GB, {1.2*n:.1f}TB/s, ${7000+1800*n}/unit) batch {batch:.0f}")
    return c

def main():
    print("=== GLM-5.2 moat study (agent workload 8k/400, cache 0.90) ===")
    b_cfg = copy.deepcopy(BASE); b_cfg["serving"]["max_batch"]=kv_batch(b_cfg,22)
    B = run(b_cfg, "B    provider-best generic (H800, SGLang-class)")
    
    s_cfg = apply_surgery(b_cfg); s_cfg["serving"]["max_batch"]=kv_batch(s_cfg,19)
    S = run(s_cfg, "B+S  + model surgery w/ healing (same rented H800s)")
    
    print("  -- surgery lever attribution (each solo on H800, vs B) --")
    SOLO = [
      ("int4 experts (QAT)",      {"weight_bytes":0.55}),
      ("fp8 KV latent",           {"kv_bytes":1.0}),
      ("cross-layer latent share",{"kv_share_layers":2}),
      ("expert-locality finetune",{"expert_locality":0.5}),
      ("asym prefill top-k 4",    {"prefill_top_k":4}),
      ("head prune 64->48",       {"heads":48}),
      ("per-layer DSA 1024",      {"sparse_attention":{"index_top_k":1024}}),
    ]
    for name, patch in SOLO:
        c = copy.deepcopy(b_cfg); c["model"].update(patch)
        c["serving"]["max_batch"] = kv_batch(c, 19)
        cost, tps, batch = run_quiet(c)
        print(f"    {name:<28} {B/cost:>5.2f}x   (batch {batch:.0f})")
    
    h_cfg = apply_asic(b_cfg)
    H = run(h_cfg, "B+H  + fitted family ASIC, vanilla model")
    
    sh_cfg = apply_asic(s_cfg)
    SH = run(sh_cfg, "B+S+H co-designed: surgered model on fitted ASIC")
    
    gs, gh, gsh = B/S, B/H, B/SH
    print(f"\ngain(surgery only)   = {gs:.2f}x")
    print(f"gain(hardware only)  = {gh:.2f}x")
    print(f"gain(co-designed)    = {gsh:.2f}x")
    print(f"synergy = joint / (s*h) = {gsh/(gs*gh):.2f}  (>1 => super-additive moat)")
    print(f"\nmoat vs generic-on-rented: co-designed is {gsh:.1f}x cheaper; "
          f"surgery alone (no silicon) {gs:.1f}x")
    

if __name__ == "__main__":
    main()
