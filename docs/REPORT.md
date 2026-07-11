# Sartor — Living Report & $/token Ledger

*Updated 2026-07-11. All numbers measured on Apple M4 Pro, 48GB, unless marked [sim] or [lit].*

## The question

Can per-model-family full-stack co-design (custom serving software → kernels → hardware → model modifications) materially beat the incumbent norm (vLLM/SGLang on NVIDIA, hosted at Fireworks/Baseten margins) on $/token — by enough (5–10×) to build a company on?

## Evidence so far

### E1. The serving-software abstraction tax is real and quantified (vLLM dissection, 12-agent code audit)
- 1–5 ms/step of pure Python across scheduler + output loops at B=256 (vLLM's own comments flag it) — `docs/vllm-cost-dissection.md`
- 2.5–7 ms/step of JSON/msgpack serialization crossing 2–3 processes; 3–4 serialize passes per token
- 20–80 µs/token/request streaming-layer Python; ~10% VRAM idled by conservative sizing
- vLLM knows: they already rewrote the API frontend in Rust (`rust/` dir) and deleted their own paged-attention kernels (paging is now just a kernel input — the "paging requires custom kernels" coupling is dead weight for a framework backend)
- **Barge (our from-scratch Rust engine) eliminates these categories**: single process, zero serialization, slot KV with views-not-gathers, detok only at the edge. Engine hot loop measured at µs-scale bookkeeping.

### E2. The kernel-layer tax dwarfs the serving-layer tax on framework backends (measured today)
SmolLM2-135M-Instruct f16, M4 Pro Metal, decode tok/s at saturation:

| stack | b=1 | b=8 | b=32 | b=64 |
|---|---|---|---|---|
| barge (candle ops, unfused) | 103 | 483 | 893 | 1,075 |
| llama.cpp (hand-fused Metal kernels) | 377 | — | — | 7,186 (8,530 @128) |

Probe data: Metal dispatch floor 11.7 µs/op; ~300 dispatches/step × 30 layers ⇒ ~3.5 ms/step of launch overhead alone vs ~1 ms of actual math at b=1. **Custom fused kernels are worth ~5–7× on this backend for this size** — this is the direct, measured analog of the per-model kernel co-design lever.
- Cold-start note: first Metal forward pays ~1.2 s of pipeline compilation (excluded from steady-state numbers).

### E3. Serving-policy losses are visible and fixable (measured today)
At n=64 saturation test, average decode batch was 31.7/64 — one-prompt-per-step prefill admission starves the decode batch. Fix: pack multiple waiting prompts per prefill chunk. [ledger item, pending measurement]

### E4. The research base (131-source calibration set, `docs/research/`)
- Canonical efficiency anchor: DeepSeek production H800: 9,200 prefill / 1,850 decode tok/s/GPU; 545% theoretical margin disclosure
- Modern ceiling: SGLang GB200: 26,156 prefill / 13,386 decode tok/s/GPU
- GLM-5/5.1/5.2 = one frozen architecture family (744B/40B MLA+DSA MoE, shapes stable across releases) → **per-family co-design amortizes**; same convergence for DeepSeek-V3.x and Kimi-K2
- Kimi-K2-Thinking ships natively INT4 → labs accept low-bit weights
- Agent workloads: ~500:1 input:output tokens, 95.7% achievable prefix-cache hit; cache-hit pricing spans 2%–50% of miss price across providers → cache economics is a wedge
- Owned B200 ≈ $2.3/GPU-hr vs $4.5–6 rental; electricity <5% of cost
- Synthesis verdict: 5–10× is plausible but front-loaded in software + workload economics (cache-centric serving 1.75–5×, SLA/regime placement 2–5×, precision ~2×, MTP 1.5–2×, owned HW ~2×); custom silicon is the *last* 2–3×, gated on simulator evidence. 2–3× of the visible price gap is incumbent margin, which compresses.

## Ledger (relative $/token = relative saturation throughput on fixed hardware)

| # | Lever | Layer | Status | Effect |
|---|---|---|---|---|
| L1 | Kill Python/IPC serving tax (barge vs vLLM-CPU) | serving | **measured** | 2.1× (525 vs 246 out tok/s, same HW/model/workload; barge f32 vs vLLM bf16 — tax is structural: Python engine + multiproc executor. Caveat: vLLM macOS ARM backend untuned; CUDA-path tax is the smaller audited 1–7ms/step) |
| L2 | Batch saturation curve (b=1→64) | serving | **measured** | 10.4× (103→1,075 tok/s) |
| L3 | Prefill packing (fix admission starvation) | serving | designed | — |
| L4 | Fused kernels (llama.cpp gap = headroom) | kernel | **measured (gap)** | 6.7× headroom at b=64 |
| L5 | Slot KV vs paged (no gather, no per-token bookkeeping) | serving | built; ablation pending | — |
| L6 | Per-tensor mixed precision / KV dtype | model | pending | — |
| L7 | Tiered KV, prefix cache economics | serving | pending (sim) | [lit] 1.75–5× |
| L8 | Hardware spec sweeps (LPDDR vs HBM, per-family ASIC) | hardware | pending (sim) | [lit] ~2–3× |

## Verdict status (updated 2026-07-11 night — Monte Carlo)

**The thesis holds under compound uncertainty.** Monte Carlo over the moat
study (150 samples: baseline stack params, ASIC BOM, kernel quality drawn
from ranges; each surgery lever given a probability of surviving quality
evals — the auto-research loop only ships survivors):

| metric | P10 | median | P90 |
|---|---|---|---|
| surgery gain (rented GPUs) | 1.29× | **1.61×** | 1.81× |
| fitted-ASIC gain (vanilla model) | 1.94× | **2.33×** | 2.95× |
| **co-design gain (the company)** | 2.95× | **3.85×** | 5.15× |
| synergy | 0.92 | 1.05 | 1.16 |

P(co-design ≥ 2×) = 100% · P(≥3×) = 88% · P(≥4×) = 42% · P(≥5×) = 13%.
P(surgered model fits a cheaper chip) = 96% (the physical co-design mechanism
is near-certain even where the $-synergy is noisy).

Robust across workload shapes (agent 6.5× / chat 5.7× / batch 6.2× at base
params) — and the optimal chip differs per model×workload, which is the
product thesis in one line.

Calibration discipline: lab anchors ±11.5% (measured by us), GB200 peak anchor
gives realization factor 0.73, DeepSeek daily-average reconciles at duty 0.53
(docs/calibration.md). Ratios above are realization-invariant.

**Prior-robustness** (the MC's weakest input is the lever-survival priors —
so stress them): halving every survival probability still gives median 3.19×,
P10 2.43×, P(≥3×)=0.60; base priors 4.13× / P(≥3×)=0.92; optimistic 4.55× /
0.99. The verdict does not hinge on surgery optimism — the hardware tier is
prior-independent and the strongest levers have production precedent.

**What would change this verdict**: real-GPU profiling contradicting the
traffic map (rental campaign, ~$15k); healing failing at scale on a mid-size
MoE (~$50k campaign); HBM/NRE costs far above the sampled ranges.

Earlier status: The two measured facts so far both support the thesis directionally: (1) framework abstraction taxes are large and structural, (2) hand-specialized kernels beat general frameworks by integer factors on identical silicon. The decisive tests are L1 (vs vLLM), the simulator calibration (G2), and the sim-driven co-design loop closing (G3).
