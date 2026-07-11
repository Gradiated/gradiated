# Optimization log: SmolLM2-135M-Instruct on M4 Pro

*The per-model co-design experiment record. Each decision: what, why, measured or simulated $/token impact, and whether it is GENERIC (any model) or MODEL-SPECIFIC (exploits this model's structure). Relative $/token ≡ inverse relative saturation throughput on fixed hardware.*

## Model profile (what makes this model's optimal stack unusual)
- 135M params, hidden **576** → every core GEMM is tile-starved on GPUs (measured: 15% of peak at b=64 vs 51% for the wide vocab GEMM). Kernels tuned for d≥2048 are the wrong shape here.
- Vocab 49,152 on hidden 576, tied embeddings → lm_head is **26% of active params**; at low batch the single biggest op.
- GQA 9q/3kv, 64-dim heads → KV is just 23 KB/token — **KV memory is a non-issue** (3 GB serves 64 slots × 2048 ctx). Paging solves a problem this model does not have.
- bf16 checkpoint, 30 thin layers → per-layer dispatch overhead × 30 dominates unfused runtimes.

## Decisions & impacts

| # | Decision | Type | Impact on $/token | Status |
|---|---|---|---|---|
| D1 | Slot KV cache (no paging): preallocate 64×2048, views not gathers | model-specific (KV tiny) + generic-ish | removes gather copies + per-token block bookkeeping entirely; enabler for D2 | built, parity-tested |
| D2 | Continuous batching to b=64 | generic | **10.4× measured** (103→1,075 tok/s) | measured |
| D3 | Multi-prompt prefill admission (fix batch starvation) | generic | avg batch 31.6→61.7 at n=256, **+32% measured** (741→977 tok/s w/ convoy fix) | measured |
| D4 | Fused QKV + fused gate/up projections | generic | folded into baseline (2 fewer dispatches/layer) | built |
| D5 | GQA via batch-folding (never tile KV to 9 heads) | model-specific (GQA ratio 3) | avoids 3× KV read traffic per step | built, parity-tested |
| D6 | LM head only on final prefill position | model-specific amplifier (huge vocab/hidden ratio) | saves 26% of prefill GEMM flops | built |
| D7 | Sampling on CPU over unified memory | hardware-specific (M-series) | frees GPU; logits copy 0.7ms/step at b=64 | measured (probe) |
| D8 | Kernel fusion 25→8→3 dispatches/layer | generic mechanism, model-specific payoff (thin layers) | **1.63×–1.78× [sim]**; llama.cpp gap (6.7× measured) bounds the full custom-kernel prize | sim; engine work queued (fused rope = −12 dispatches/layer) |
| D9 | Weight quantization int4 | — | **1.00× [sim] — null result.** This model at b=64 on M4 is dispatch/occupancy-bound, not bandwidth-bound. Quantize for memory only if capacity-constrained. Opposite conclusion expected for GLM-class on HBM GPUs. | sim; lab verification queued |

## The model-specific thesis, as evidenced so far
The 135M's optimal stack diverges from the generic playbook in at least three places: (1) paging is pure overhead (D1), (2) quantization buys nothing at saturation (D9), (3) the win concentrates in dispatch-count and small-shape GEMM tiles (D8) — i.e., a bespoke kernel set tuned to d=576/30-layers, which is exactly what per-model codegen would produce. Next: verify D8/D9 in the engine (fused rope first), then rerun this table on Qwen2.5-0.5B (vocab 151k — even more head-dominated) and Qwen3-4B (bandwidth-bound regime begins) to see how the optimal stack shifts with model shape.

## Calibration status (trust label for [sim] rows)
Sim reproduces measured avg batch exactly (61.7); throughput +69% optimistic (sim 1,649 vs measured 977) — engine-side buffer churn at varying shapes and prefill activation traffic not yet modeled. [sim] ratios are more trustworthy than absolutes; treat D8/D9 as directional until the gap closes (target ±20%).
