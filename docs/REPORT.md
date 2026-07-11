# Sartor — Living Report & $/token Ledger

## Executive summary (for the impatient)

**Thesis tested**: per-model full-stack co-design — custom serving software, small
finetune-healed model modifications, and eventually model-family-fitted silicon —
can host frontier open-source models at a multiple below Fireworks/Baseten-class
providers. **Status: supported, with measured foundations and quantified uncertainty.**

- **Verdict distribution** (Monte Carlo w/ lever-failure modeling, N=1000):
  co-design gain vs provider-BEST practice = **median 3.9× [P10 3.0, P90 5.2]**;
  P(≥3×)=90%; still 3.2× median under maximally skeptical surgery priors.
  Market prices sit a further 2-4× above provider-best cost (incumbent margin).
- **Measured, not simulated**: our Rust engine beats vLLM 2.1× like-for-like;
  sim predicted a real weight-surgery's throughput within 0.1% (predicted
  1.050×, measured 1.051×); int8-KV measured lossless on real weights;
  calibration anchors within ±11.5% (lab) / one explicit 0.73 realization
  factor (datacenter peak).
- **Per-model headroom league** (co-designed, point → MC-median-equivalent):
  GLM-5.2 6.5×→3.9× · Kimi-K2 11.5×→6.9× · Qwen3-235B 10.8×→6.5× ·
  gpt-oss-120b 12.2×→7.3× · MiniMax-M2 14.3×→8.6×. Headroom concentrates on
  models whose labs under-invested in serving efficiency; the three binding
  constraints (hot-set / expert-stream / KV-capacity) and the optimal chips
  all differ per model — the abstraction tax is the value generality cannot price.
- **Sequencing**: software+surgery is a day-1 business on rented GPUs (no capex);
  the family-ASIC becomes rational at a computed volume milestone (~3-14k chips
  ≈ 1T tok/day); wafer-scale SRAM competitors are 10-76× off the cost pace for
  frontier MoE (latency lane, not cost lane).
- **Decisive next experiments** ($1M covers all): rented-GPU money-run vs
  Fireworks price sheet (~$20k), mid-size healing campaign (~$50k), cache-hit
  engineering on real agent traces (~$5k).

*Everything below is the evidence ledger behind this summary; the lab log on
this page records the work as it happened.*


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

### E5. Weight-bandwidth concentration + architecture round 2 (2026-07-11 late)
- **"Do a few weights dominate bandwidth?" — yes, structurally**: GLM-5.2 at
  EP144, the always-hot set (attn+shared+dense+head = 2.3% of params, 17GB
  replicated/GPU) causes **77% of per-GPU memory traffic** (43% at EP32).
  Kimi-K2 (thin attention, 384 experts): only 14-25% — per-model divergence.
- Negative finding: at saturation batch ALL experts activate every step →
  cold-expert offload to slow memory does NOT work at high load; the hot-set
  levers are architectural shrinkage and amortization (batch × MTP). This is
  why KV-shrinking surgery compounds: KV ↓ → batch ↑ → hot-GB/token ↓.
- Architecture round 2 on the co-designed optimum: thin returns (+2-6% for
  TP-attn, latent 384, MTP-2) — **the co-design converges**; expert
  consolidation (64×8192 top-2) is NEGATIVE (0.59×) under the current model.
- **Kimi-K2 dossier (new model, same pipeline)**: provider-best $0.474/Mtok
  (1T params, ships without MTP/DSA); surgery incl. family-proven retrofits
  2.96×; co-designed **11.5×** ($0.041). Headroom is model-dependent — the
  machine's job is finding which models have the most recoverable margin.

### E6. Loop closures + economics (2026-07-11 eve, heartbeat rounds)
- **G3 closed (the company mechanism works end-to-end)**: sim predicted
  head-prune surgery = 1.05× throughput on M4; real surgery on real weights,
  benched in barge: **1.051×** (1,308 vs 1,244 tok/s, 3-run means).
- **Twin measurements**: int8 KV = free on real weights (+0.06% ppl) — the
  strongest surgery lever is now measured, not assumed; int4 KV needs
  per-layer selectivity (+26% ppl if global). Healing run converging.
- **Trace-diff overturned the consolidation negative**: at equal batch/chip,
  64×8192-top2 is +8.5% (EP comm ÷2.7) — earlier 0.59× was a fitter artifact;
  the loop caught its own false negative.
- **At the co-designed optimum the step is compute-bound in expert GEMMs
  (57%)** — the remaining frontier is active-param reduction (quality-gated)
  or cheaper FLOPs.
- **MC N=1000**: co-design median 3.91× [P10 2.98, P90 5.17], P(≥3×)=0.90,
  P(surgered chip cheaper)=0.98.
- **NRE break-even**: family-ASIC beats surgery-on-rented at fleet ≥ ~2.9k
  chips (NRE $100M) / 7.2k ($250M) / 14.5k ($500M); 5k chips ≈ 1T tok/day ≈
  one-large-provider scale. Silicon is a volume-earned milestone, not a bet.
- **Headroom league** (point estimates, MC-discount before quoting): GLM-5.2
  6.5×, Kimi-K2 11.5×, Qwen3-235B 10.8×, gpt-oss-120b 12.2×, MiniMax-M2 14.3×
  — margin concentrates on models whose labs under-invested in efficiency.

### E7. Spot/interruptible economics (2026-07-11 eve)
Batch traffic tolerates preemption → it can use spot capacity that training and
interactive serving structurally cannot. Measured-parameter model: typical spot
(−55%) costs 5–9% in preemption overhead (EP-group blast radius included) →
**2.09× net cost advantage** stacking on the software tier; break-even tolerance
is 34–69 preemptions/node/DAY (real rates: 0.2–3). Synergy: surgery shrinks
memory/GPU → smaller EP groups → smaller blast radius → spot gets safer.
Caveats: hybrid fleet required (reserved base + spot surge); multi-node coherent
spot groups are thinner markets. FRAMING CORRECTION (from Josh): incumbent
margin is not counted as a "saving" — cost advantage is the claim; pricing
(undercut vs margin-for-capex) is a strategic choice on top.

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
