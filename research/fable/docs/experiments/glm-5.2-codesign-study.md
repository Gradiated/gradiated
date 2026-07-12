# GLM-5.2 full-stack co-design study — v1 (2026-07-11)

**Question**: serving GLM-5.2 (744B/40B-active MLA+DSA MoE, real config.json) for background-agent traffic (8k-token prompts, 400-token outputs, no latency SLO), how much $/token improvement does per-model-family co-design buy over today's best practice?

**Method**: calibrated simulator (`sartor`), cumulative levers, per-GPU accounting. Baseline is *best current practice*, not a strawman: H800 + SGLang-class kernels with MTP, DSA, EP144, dual-microbatch comm overlap, and 60% realized prefix-cache hits all already ON. Batch ceilings derived from KV capacity at every step.

**Calibration status at time of study**: lab anchors (3 models measured on M4, spanning dispatch-bound → kernel-limited regimes) worst error ±11.5%; DeepSeek-V3 H800 production disclosure (1,850 decode tok/s/GPU) +13.0%. MoE FFN modeled as routed token-expert pairs through per-expert GEMMs with occupancy penalties; MLA modeled with absorbed-matmul decode (compute-for-memory trade explicit).

## Results (cost = amortized capex + power, 70% fleet utilization)

| Lever (cumulative) | Layer | tok/s/GPU | $/Mtok out | step Δ |
|---|---|---|---|---|
| L0 baseline (H800+SGLang norm) | — | 830 | $0.709 | — |
| L1 agent-aware prefix caching 0.60→0.95 | serving | 1,316 | $0.447 | **1.59×** |
| L2 fp8 KV latent (batch 76→146) | model | 1,413 | $0.416 | 1.07× |
| L3 int4 experts (Kimi-K2 precedent) | model | 2,024 | $0.291 | **1.43×** |
| L4 top-k 8→6 routing (quality-gated) | model-arch | 2,072 | $0.284 | 1.02× |
| L5 bespoke family kernels | kernel | 2,180 | $0.270 | 1.05× |
| L6 co-designed EP32 + overlap 0.9 | serving | 2,224 | $0.264 | 1.02× |
| L7 141GB/4.8TB/s memory-config HW | hardware | 2,585 | $0.286 | **0.92× (negative!)** |
| L8 family ASIC (speculative: $15k, 1200TF fp8, 500W, 85% util) | hardware | 2,403 | $0.104 | **2.75×** |

**Cumulative: 6.8×** ($0.709 → $0.104). Decomposed: software+model on the same H800s = **2.7×** (L1–L6); custom silicon adds a further **2.5×** — and it is a *cost-structure* play (cheaper die, no margin stack, higher utilization), not a throughput play.

## Findings

1. **The two big deployable levers are cache economics (1.59×) and int4 expert weights (1.43×)** — one workload-shaped, one model-shaped. Both have production precedent (Kimi 95%+ cache hits; K2-Thinking ships INT4).
2. **Negative result: premium memory hardware (H200-class) hurts $/token here** (+16% throughput, +31% cost) — the config is not bandwidth-bound after L3-L6. A cheaper-not-faster direction wins, which is exactly the ASIC result (L8: 7% *less* throughput, 2.75× better cost).
3. **Kernel/EP levers look small (5-7%) for this model on this hardware** — opposite of the SmolLM2-135M-on-M4 result where kernels were worth 1.78×. Per-model, per-hardware co-design conclusions genuinely differ — the environment's reason to exist.
4. Market check: GLM-4.6-class output sells at ~$1.75–2.75/Mtok; modeled L6 cost $0.264 implies the visible price gap is ~2.7× real cost advantage + incumbent margin structure (consistent with research: 2–3× of the gap is margin).

## Caveats (each is a queued workstream)
- L4 (top-k) and L3 (int4) carry quality risk: need the healing/eval loop (functional twin) before claiming them — L4 credited at only 1.02× here anyway.
- L8 ASIC spec is illustrative; NRE/volume math not yet in the cost model (research corpus has mask-set/NRE ranges: next).
- Prefill modeled on-GPU-local (no EP sharding of prefill); DSA modeled as hard top-k cap; comm overlap as a scalar; EP load imbalance not modeled (anchor +13% suggests net conservative-enough).
- Blended prefill+decode instances; production disaggregates (would improve all rows somewhat, mostly baseline).

## Verdict signal (v1)
5–10× total is **live**: 6.8× with one model, honest baseline, calibrated ±13%, and the speculative tier carrying 2.5× of it. The software+model 2.7× alone beats typical provider gross margin — a business even without silicon. Next fidelity steps sharpen L7/L8 (the decision that matters most).
