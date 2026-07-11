# GLM-5.2 moat study: model surgery × fitted silicon (v1, 2026-07-11)

**Question**: is there a *moat* in co-designing OS models (small architecture changes + finetune healing) together with custom hardware — beyond what generic providers and generic ASIC vendors can each reach alone?

**Method**: calibrated simulator (`sartor`; lab anchors ±11.5%, DeepSeek-H800 anchor bracketed — see caveats), byte-exact traffic traces driving lever selection, four tiers with per-tier fitted hardware. Baseline is provider-best generic (grouped-MoE kernels, prefill packing, MTP, DSA, fp8, 90% prefix cache, EP overlap/imbalance modeled). Workload: background agents, 8k in / 400 out. **Ratios are the trustworthy output** — absolute $/Mtok inherits peak-duty idealizations shared by all tiers.

## The traffic map that drove lever selection (trace of DSv3-class decode, H800)
Latent-KV reads **40%** of step; EP all-to-all **24%**; expert GEMMs 17%; MLA o_proj weight-stream 6%. Co-design targets: KV stream, expert placement, memory-per-token — *not* FLOPs.

## Results

| Tier | Config | tok/s/GPU | $/Mtok | vs B |
|---|---|---|---|---|
| B | provider-best generic, H800 | 2,060 | $0.285 | — |
| B+S | + model surgery (healed), same H800s | 3,781 | $0.156 | **1.84×** |
| B+H | + fitted ASIC, **vanilla** model → fitter picks 7 HBM stacks, 168GB, $19.6k | 3,529 | $0.091 | **3.12×** |
| B+S+H | surgered model on **its** fitted ASIC → 4 stacks, 96GB, $14.2k | 5,384 | $0.044 | **6.54×** |

**Synergy = 6.54 / (1.84 × 3.12) = 1.14** — super-additive. Mechanism: surgery halves memory-per-token (KV share, int4, fp8 latent) → the fitted chip crosses a discrete HBM-stack cliff (7→4 stacks; HBM is the dominant BOM line) → hardware $/throughput falls further than either lever alone predicts. Co-design also shows in the fitter's choices: *the optimal chip is a function of the model* (168GB vs 96GB designs).

## Surgery lever attribution (solo, on H800, vs B)
| Lever | solo gain | evidence tier |
|---|---|---|
| int4 experts (QAT-healed) | 1.20× | strong (Kimi-K2-Thinking ships INT4) |
| fp8 KV latent | 1.17× | strong (near-lossless in literature) |
| cross-layer latent sharing (CLA-on-MLA, healed) | 1.17× | plausible (CLA/YOCO precedent; novel on MLA) — needs healing run |
| per-layer DSA profile (avg top-k 1024) | 1.07× | plausible — needs per-layer eval |
| head prune 64→48 (healed) | 1.05× | being tested on real weights (twin experiment, SmolLM2) |
| expert-locality routing finetune | 1.03× solo | value concentrates in the ASIC tier (cheaper fabric); grounding via granite-MoE routing stats (twin, running) |
| asymmetric prefill top-k 4 | 1.01× | small at 90% cache; grows on cache-cold workloads |

## Moat reading
1. **The co-designed point ($0.044) requires both competencies at once** — weights access + finetune/eval infrastructure (weeks per model family) AND silicon (~18-24mo cycle). A generic provider tops out at ~$0.285; a generic ASIC vendor serving vanilla models at ~$0.091; a lab that finetunes but rents at ~$0.156. Even at synergy 1.0 the *organizational* barrier is conjunctive; at 1.14 the joint design is strictly better than the parts.
2. **Family amortization holds**: GLM-5.0/5.1/5.2 share frozen shapes (verified configs), so surgery recipes + silicon amortize across the family's release cadence.
3. **The negative results matter**: premium generic hardware (H200-class) made $/token *worse* for the co-designed config in the earlier study; locality/asym-topk are near-worthless solo but load-bearing in the ASIC tier — lever value is configuration-dependent, which is exactly why an auto-research environment (not a static playbook) is the product.

## Caveats / next fidelity steps
- DSv3 anchor open: sim's peak-duty idealization sits ~2.6× above DeepSeek's *daily-average* disclosure; ratios shared across tiers, absolutes not for external quoting until a peak anchor (GB200) is added.
- Surgery quality costs are evidence-tiered, not yet all measured; the twin workstream (real head-prune + heal + routing stats on local models) is running and will replace placeholders (esp. expert_locality=0.5).
- ASIC cost model is BOM+NRE-amortized at 50k units ($7k die/board + $1.8k/HBM-stack + $1k fabric); NRE sensitivity analysis pending.
- EP prefill sharding, per-layer heterogeneity (layer groups), and quality-aware objective (quality-adjusted $/token) are queued model-fidelity items.
