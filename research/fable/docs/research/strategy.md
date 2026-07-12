# Sartor Strategy Synthesis: The 5–10x $/Token Thesis

Synthesized 2026-07-11 from an 8-agent web research workflow (model architectures, SOTA serving, hardware economics, simulator prior art, custom silicon, model-side levers, market prices). Constants and full source tables: [calibration-constants.md](calibration-constants.md).

---

## 1. Strategic Assessment: Verdict on 5–10x

**The evidence supports the 5–10x $/token thesis, with three corrections that should reshape the roadmap:**

1. **The multiple is real, but it is mostly capturable in software and workload economics on existing GPUs.** Custom silicon is the last ~2–3x, not the first 5x.
2. **The winning granularity is per-model-FAMILY, not per-model.** The Chinese frontier has converged on one recipe — MLA 576-dim latent KV, 256–384 fine-grained experts top-8 + 1 shared, MTP head, native FP8, and (since late 2025) a top-k=2048 DSA sparse-attention indexer shared bit-for-bit by DeepSeek-V3.2 and GLM-5.x. Shapes are stable across point releases (GLM 5.0→5.2 and MiniMax M2→M2.1 are tensor-identical; DeepSeek V3→V3.2 was additive). One kernel/silicon suite covers most open frontier models.
3. **Roughly 2–3x of the customer-visible price gap is incumbent margin compression, not cost innovation.** Fireworks/Baseten-class providers now run >70% gross margins ([SemiAnalysis](https://newsletter.semianalysis.com/p/ai-value-capture-the-shift-to-model), paywalled — verify before external use). Be explicit internally about which multiple is being claimed.

### Where the multiple comes from (multiplicative, saturating, partially overlapping)

- **Cache economics on agent workloads** — the single clearest wedge. Coding agents run ~500:1 input:output with 95.7% prefix hit rates; prefix reads are ~60% of API spend ([TraceLab](https://arxiv.org/html/2606.30560)). DeepSeek prices a cache hit at 2% of a miss and Anthropic at 10%, while Fireworks/Groq/Together charge 50% — a **5–25x pricing gap** on the token class that dominates agent spend, backed by Mooncake-style engineering (1.75–5x capacity gains, [arxiv 2407.00079](https://arxiv.org/abs/2407.00079)) that is architectural, not kernel-level.
- **Regime placement.** InferenceMAX shows identical hardware/software swings 5–10x in tok/s/GPU across the interactivity frontier ([inferencex.semianalysis.com](https://inferencex.semianalysis.com/compare/deepseek-r1-b200-vs-h200)); batch APIs price at 50% of list everywhere. $/token is not a scalar — deliberately serving latency-insensitive agent traffic at the saturated-throughput end banks a structural multiple.
- **Precision co-design** — a proven, lab-sanctioned ~2–2.3x (SGLang GB200 measured 1.8–1.9x kernels; Kimi-K2-Thinking ships INT4 natively; NVFP4 costs −0.1pt MMLU on R1).
- **Per-family kernels + MTP.** MTP heads shipped in GLM/DeepSeek weights offer ~1.5–2x decode that generic stacks leave off; day-0 engine gaps of 3–5x are documented but decay in weeks–months.
- **Owned hardware vs on-demand rental** — a quiet ~2x (derived B200 TCO ~$2.3/hr vs $4.5–6 rented).

Multiplying the credible levers — cache/disagg (1.5–3x on agent mix), regime placement (1.5–2x), precision (2x), MTP (1.5x), family kernels (1.2–1.5x), owned hardware (2x) — **comfortably spans 5–10x against what Fireworks/Baseten-class providers charge today, before any silicon.**

### What contradicts the thesis

1. **Replication lag is short.** SGLang matched DeepSeek's custom stack ~3 months after disclosure ([lmsys.org](https://www.lmsys.org/blog/2025-05-05-large-scale-ep/)); vLLM hit 2.2k tok/s/GPU wide-EP by Dec 2025. Per-model serving-software advantage on popular open models is a wasting asset — durable only in day-0 windows, proprietary/modified models, and workload-specific cache co-design.
2. **The moving baseline is Blackwell + TRT-LLM/Dynamo with disaggregation and wide-EP already in production** at Together/Baseten/Fireworks (and every frontier lab). "Beat vLLM-on-H100" overstates headroom. NVIDIA's $0.02/Mtok gpt-oss floor and its 5x-in-2-months software gain cut both ways: they prove software co-design works, and prove NVIDIA captures it for everyone.
3. **Kernel-level decode headroom is bounded.** MBU ~60% → 90% is only ~1.5–1.7x; bigger wins require changing the regime, precision, or memory system.
4. **Specialized-silicon vendors price Llama-70B at GPU parity** (~$0.6/Mtok), implying at-scale internal savings smaller than claimed. No analyst defends weights-frozen per-model silicon against the 2–3yr silicon cycle vs 6–12mo model cadence.

**Bottom line: pursue the 5–10x software-first — cache-centric serving for agent workloads on the converged MLA+DSA family, precision and MTP exploitation, regime arbitrage against incumbents' margin umbrella — with the simulator as the instrument that decides, with <5% error, whether and when a per-family ASIC's final ~2–3x clears its NRE against model-family half-life. The thesis survives; the sequencing is the strategy.**

---

## 2. Stack-Ranked Levers

| # | Lever | Layer | Est. gain | Confidence |
|---|---|---|---|---|
| 1 | **KV-cache-centric architecture for agent workloads**: prefix-cache DRAM/SSD tiering + PD disaggregation (Mooncake-style), monetized against the 5–25x cache-hit pricing gap | serving software | 1.75–5x effective capacity on cache-heavy traffic; largest $/token wedge vs incumbent pricing (hits at 2–10% vs their 50%) | high — production-proven (Mooncake, DeepSeek); workload data (TraceLab 95.7% hit, 500:1 in:out) is primary |
| 2 | **Regime/SLA placement**: serve latency-insensitive agent traffic at saturated-throughput end of the frontier; batch-API economics | serving software | 2–5x tok/s/GPU vs interactive-SLA operation on identical hardware | high — directly measured across the InferenceMAX frontier |
| 3 | **Low-precision co-design**: NVFP4/INT4 weights + FP8 KV with quantization-aware distillation (sartor owns the model, so QAD is available) | kernels + model mods | ~2–2.3x throughput vs FP8; ~3.5x memory vs FP16; near-zero accuracy cost at 30B+ | high at 30B+; medium below 2B (unpublished; overtrained-model penalty) |
| 4 | **Owned/committed hardware** instead of on-demand rental (TCO arbitrage) | hardware | ~2x $/GPU-hr (B200 ~$2.3/hr owned vs $4.5–6 rented) | high — arithmetic from well-sourced constants |
| 5 | **MTP self-speculative decoding** (heads already shipped in GLM/DeepSeek weights, often unused by generic stacks) | serving + kernels | 1.5–2x decode | medium — mechanism proven; acceptance rates on agent workloads unmeasured |
| 6 | **Per-family kernel suite** for the converged MLA+DSA+fine-grained-MoE recipe (MLA absorb, top-k 2048 sparse gather, small-N grouped GEMM), incl. day-0 windows | kernels | 1.2–1.5x steady-state vs best open engine; 3–5x transient at day-0 | medium — day-0 gaps decay in weeks–months; steady-state edge thin vs 3-month replication lag |
| 7 | **KV-architecture retrofits of GQA models**: MLA retrofit (TransMLA/MHA2MLA) + 4-bit KV quant + local:global windows | model mods | 2.7–4.7x KV footprint → 1.5–3x long-context decode $/token; retrofit ~6B tokens; accuracy cost 0.3–2.6% | high on KV/accuracy; medium on e2e $/token (never measured under a real stack) |
| 8 | **Host/framework overhead elimination**: lean per-model engine (GPU-resident scheduling, no Python loop) | serving software | 1.5–2x for sub-8B/high-interactivity; 1.1–1.3x for frontier MoE | medium-high — 33–50% host share measured; biggest exactly where market is commoditized |
| 9 | **2:4 structured sparsity** with recovery training, stacked with INT4 | model mods | 1.24–1.27x alone; 1.2–3.0x with INT4 kernels; 98% accuracy recovery | medium — recovery training required; stacking with NVFP4+MLA unmeasured |
| 10 | **Bespoke right-sized models per customer** (Minitron prune+distill) | model mods | 2–10x when workload tolerates smaller model; ~1/40 pretraining cost to produce | medium — solid at 4–15B; unpublished below 500M |
| 11 | **Rack-scale bandwidth domains** (GB200/NVL72-class) for high-interactivity serving | hardware | up to 4.4x per-GPU vs B200 at 125 tok/s/user; least relevant to batch-heavy agent regime | medium — regime-specific; rental premium eats much of it |
| 12 | **Per-FAMILY inference ASIC** (N4, decode-optimized cheap-memory hierarchy: LPDDR/GDDR7 tiers + HBM for KV; explicitly not SRAM-only) targeting the frozen MLA+DSA recipe | hardware | 2–3x TCO on top of software stack (TPU v7 precedent; vendor 10x+ claims unverified); NRE $50–150M; ~5–10K-unit break-even | low-medium — no per-model ASIC exists; Groq anti-pattern shows wrong memory choice loses 10x; only after software proves volume and family stability |

---

## 3. Custom-Silicon Landscape Lessons (mid-2026)

**No pure per-MODEL ASIC exists.** The market settled on a specialization spectrum — per-architecture (Etched: transformers), per-workload-shape (Positron/d-Matrix: memory-bound decode; Cerebras/Groq: latency), per-lab (TPU/Trainium/MTIA/Maia) — with analysts consistently citing 2–3yr silicon lead time vs 6–12mo model cadence as the reason to stop at architecture level ([chipstrat](https://www.chipstrat.com/p/etched-silicon-valleys-speedrun)).

- **Groq (the anti-pattern):** SemiAnalysis's teardown found 576 SRAM-only chips needed per Mixtral instance at batch ~3; NVIDIA ~10x better perf/$ at throughput scale ([teardown](https://newsletter.semianalysis.com/p/groq-inference-tokenomics-speed-but)). Groq effectively exited via a $20B non-exclusive NVIDIA license (Dec 2025) and pivoted to a neocloud ([TechCrunch](https://techcrunch.com/2026/06/22/ai-chipmaker-groq-confirms-650m-raise-re-staffs-after-nvidias-20b-not-acqui-hire-deal/)). Lesson: SRAM-only wins batch-1 latency, loses min-$/token. For sartor, co-design must optimize the high-batch regime — cheap high-capacity memory (LPDDR à la Positron/MTIA, HBM-for-KV à la MatX), not SRAM-resident weights. Encode the batch-1-latency vs saturated-throughput split as a first-class axis in the simulator.
- **Cerebras:** real commercial traction (IPO ~$56B, FY25 revenue $510M, >$20B/750MW OpenAI deal) but throughput is roughly batch-insensitive — it wins the interactive/speed premium regime, not min $/token. Risks: 86% of FY25 revenue from UAE customers, operating loss ([tech-insider.org](https://tech-insider.org/cerebras-ipo-filing-510m-revenue-openai-deal-23b-valuation-2026/)).
- **Etched:** strongest existence proof for architecture-specialized silicon ($800M raised, >$1B contracts, A0 silicon, racks shipping summer 2026) — but the 500k tok/s Llama-70B claim is vendor-only with no batch-32/256 figures, no independent benchmark, no pricing. Etched itself estimates ~3 years to respin for a new architecture.
- **SambaNova (cautionary):** abandoned training ambitions, 15% layoffs, $350M raise at $2.2B (down from ~$5B in 2021) ([datacenterdynamics](https://www.datacenterdynamics.com/en/news/sambanova-lays-off-77-employees-as-company-pivots-focus-from-training-to-inference/)).
- **Positron / MatX / d-Matrix:** the new cohort explicitly rejects SRAM-only. Positron bets on LPDDR cost structure (Asimov 2027: ~2TB LPDDR5X, 2.76 TB/s, 400W); MatX (ex-TPU architects, $500M Series B) targets big-MoE with HBM for KV, shipping 2027; d-Matrix Corsair (digital in-memory compute + LPDDR) in production June 2026 for small-batch/low-latency niches.
- **Hyperscalers are the real proof:** TPU v7 at ~44% lower TCO/chip and ~1/3 NVIDIA capital cost; Trainium 3 at ~$1/chip-hr vs B200 $5.5 list; MTIA v2's 256MB SRAM + 128GB LPDDR5 @ 205 GB/s shows what owner-controlled co-design chooses (capacity/cost over bandwidth). Vertical integration delivers 2–5x — this, not Etched's 12x, is the honest comparable for sartor's ASIC endgame.
- **Exit landscape:** NVIDIA paid $20B for Groq's IP; Meta paid ~$2B for pre-product Rivos; Cerebras IPO'd. Credible acqui-hire/IP floors exist, but NVIDIA is absorbing latency-chip tech and marketing $/Mtok directly, compressing the window.

**Mitigant that makes a per-family ASIC plausible anyway:** architecture convergence plus additive version churn (V3→V3.2 added only an indexer) means an MLA+DSA+small-expert-GEMM chip on N4 (~$50–150M lean NRE, ~5–10K units to pay back at 2x perf/$) plausibly survives 2–3 model generations. It is a per-family bet with a decode-throughput memory system, taken only after the software layers prove the demand.

---

## 4. Model-Side Lever Evidence

Owning the model is what makes aggressive formats safe — PTQ at sub-2B loses several points, but QAT/distillation closes the gap with modest token budgets.

**Quantization**
- NVFP4 PTQ: DeepSeek-R1 MMLU 90.8→90.7 (−0.1pt vs FP8); ~2.3x throughput vs FP8 on Blackwell, ~3.5x memory vs FP16 ([NVIDIA](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/)). Sub-2B results unpublished.
- Scale dependence (W4 PTQ, Qwen-2.5): 7B −6.8%, 32B −2.0%, 72B +0.7% ([IJCAI 2025](https://www.ijcai.org/proceedings/2025/0902.pdf)). Small models need QAT/distillation.
- QAT moves the small-model frontier to 2–3 bits ([ParetoQ](https://arxiv.org/abs/2502.02631)); BitNet b1.58-2B-4T (native ternary) within 1–2pts of FP peers but requires training from scratch ([arxiv 2504.12285](https://arxiv.org/abs/2504.12285)).
- **Caveat:** overtrained models quantize worse — degradation grows with training tokens ([arxiv 2411.17691](https://arxiv.org/abs/2411.17691)); modern 10T+-token small models will degrade more than 2023-era results imply.
- Salient-weight evidence: ~1% of weights (outlier channels, FFN output projections) carry most sensitivity — SpQR 3.4x compression at <1% ppl loss ([arxiv 2306.03078](https://arxiv.org/abs/2306.03078)); supports the "modify a small % of weights" hypothesis; realizing the bandwidth win needs custom mixed-format kernels (favors full-stack control).
- Production proof of native low-bit: Kimi-K2-Thinking ships INT4; gpt-oss ships MXFP4 MoE weights; Apple ships ~3.7-bit palettized on-device.

**MLA / KV compression**
- MLA needs ~70 KB/token vs 192–328 KB/token for comparable GQA (2.7–4.7x), and DeepSeek reports MLA outperforms MHA in quality ([arxiv 2505.09343](https://arxiv.org/html/2505.09343v1)).
- Retrofits are cheap: TransMLA −68.75% KV at −1.65% accuracy training-free, 93% compression restored with a 6B-token fine-tune ([NeurIPS 25 Spotlight](https://arxiv.org/abs/2502.07864)); MHA2MLA works at 135M–7B for 0.3–2.6% accuracy using 0.6–1% of pretraining data ([ACL 25](https://arxiv.org/abs/2502.14837)). This is a concrete, defensible product motion.
- KV quantization: 4-bit nearly free; 2-bit task-dependent (KIVI ok on GSM8K per original paper; 2025 Kitty/KVarN papers show hard-reasoning failures).
- Architecture changes: Gemma 3's 5:1 local:global attention cuts KV from ~60% to <15% of inference memory ([arxiv 2503.19786](https://arxiv.org/abs/2503.19786)); CLA2 gives 2x KV at near-equal accuracy at 1B–3B scale ([arxiv 2405.12981](https://arxiv.org/abs/2405.12981)).

**DSA (sparse attention)**
- DeepSeek-V3.2 and GLM-5.x share a top-k=2048 lightning indexer — attention cost near-constant in sequence length. **A cost simulator that does not model DSA (indexer FLOPs + top-k gather) will overestimate long-context decode cost for these models by ~an order of magnitude at 100K+ contexts.**
- MiniMax abandoning linear attention (M1 hybrid → M2 full softmax) suggests linear attention underdelivered; sparse top-k is the industry's chosen long-context lever — bet co-design effort there.

**Sparsity / distillation**
- 2:4 sparsity: 1.24–1.27x e2e decode, 98% recovery with sparse recovery training (~tens of B tokens), 1.2–3.0x combined with INT4/Sparse-Marlin ([Red Hat/Neural Magic](https://developers.redhat.com/articles/2025/02/28/24-sparse-llama-smaller-models-efficient-gpu-inference)).
- Minitron prune+distill: bespoke right-sized model at ~1/40 pretraining cost ([arxiv 2407.14679](https://arxiv.org/abs/2407.14679)) — per-customer model tailoring is economically feasible.
- Workload branching rule: short-context/high-batch is weight-bandwidth dominated (quantize/sparsify weights); ≥32K context flips to KV-dominated (MLA retrofit + KV quant + local:global). The simulator should branch on batch × context.

---

## 5. Simulator Design Implications (from prior art)

- **Don't build from scratch.** Proven recipe: per-kernel roofline × measured/learned efficiency factor + hard launch-overhead floor ([KernelSight-LM](https://arxiv.org/html/2606.28565v2)), feeding a discrete-event serving layer with a faithful scheduler reimplementation ([Vidur](https://arxiv.org/abs/2405.05465)/[Frontier](https://arxiv.org/html/2605.21312)). Reuse [GenZ](https://github.com/abhibambhaniya/GenZ-LLM-Analyzer) or [LLMCompass](https://arxiv.org/abs/2312.03134) as the analytical/hardware-DSE core, ASTRA-sim's analytical backend for collectives, Timeloop+Accelergy or SCALE-Sim v3 only for silicon-leg validation.
- **<5% throughput/$-per-token error is demonstrably achievable** (KernelSight-LM 2.7%, Frontier <4%, LLMServingSim 2.0 0.95% self-reported) — precise enough to defend a claimed 5–10x. TTFT stays ~14% — pitch cost claims on throughput, not tail latency.
- **Naive spec-sheet rooflines are disqualifying:** they miss 32–60% launch/CUDA-Graph effects, inflate KV budgets ~27% (throughput +32%), mishandle batch heterogeneity (21–33% op error), and wrongly predict decode goes compute-bound at large batch (memory controllers saturate first — [Mind the Memory Gap](https://arxiv.org/pdf/2503.08311)). Use measured achievable-bandwidth curves and per-request length distributions.
- **The simulator must be a (throughput, interactivity, cache-hit-rate) frontier model** driven by [Mooncake traces](https://github.com/kvcache-ai/Mooncake) and TraceLab distributions, and must model DSA.
- **Calibrate against four anchors, each within ~20%:** DeepSeek H800 (9.2k prefill / 1.85k decode tok/s/GPU), SGLang 96xH100 ($0.20/M), vLLM H200 (2.2k), SGLang GB200 (26.1k/13.4k).
- **The genuine research gap:** no published tool jointly sweeps model architecture, kernels, silicon, and serving policy. The Vidur datapoint (1 CPU-hour replacing ~$218K of GPU search) is the economic argument for building that loop.

---

## 6. Open Questions

Top-priority first (as ranked by the synthesis):

1. **Achieved HBM MBU/MFU at large decode batch in the wide-EP regime** on H100/H200/B200 — the cited ~60% MBU is a 2023-era small-batch figure; derive from GB200 13.4k decode vs HBM bandwidth and measure directly. Sets the kernel-layer ceiling in the simulator.
2. **Primary tok/s/GPU benchmarks for GLM-4.5/4.6/5 and Qwen3-30B-A3B** under vLLM/SGLang at production batch on H100/H200/B200 — none exist publicly; cheap to run; these are sartor's target models.
3. **True marginal cost of a KV-cache hit served from DRAM/SSD tiers** (vs DeepSeek's 2%-of-miss price) — the load-bearing number for the cache-economics wedge; no provider publishes it.
4. Do NVFP4/MXFP4 and 2–3-bit QAT hold on modern overtrained sub-2B models, and do quantization + 2:4 sparsity + MLA retrofit stack multiplicatively in accuracy loss? No paper combines all three; run SmolLM/Qwen-0.6B experiments ± QAD.
5. MTP acceptance rates and realized speedup on agentic workloads for GLM-5 and DeepSeek-V3.x under a custom engine (the 1.5–2x is inferred, not measured on this traffic).
6. End-to-end $/Mtok at matched SLA (same model, batch, interactivity) across Groq/Cerebras/B200/TPU/MI355X — all public comparisons mix regimes.
7. DeepSeek-V4 architecture verification: config gated (HTTP 401); the 1.6T/49B-active, CSA+HCA, "27% FLOPs / 10% KV" claims are secondary-only. Obtain the tech report before encoding V4.
8. First-party overhead decomposition of vLLM vs SGLang across model sizes (host CPU, scheduler, launch gaps) — feeds the "barge" lean-engine case and the simulator's launch-overhead floor.
9. Independent benchmark of Etched Sohu at batch 32/256 with pricing — the most load-bearing per-architecture-ASIC datapoint is vendor-only.
10. Measured wall power during LLM decode on B200/GB200/MI355X (only H100 anecdotes exist) — needed for the owned-hardware TCO line.
11. LPDDR5X and GDDR7 contract $/GB mid-2026 — determines whether the cheap-memory ASIC/tiering arbitrage survives the DRAM super-cycle.
12. Build the per-family ASIC break-even model ourselves: NRE amortization vs model-family half-life, minimum economical volume, N4 defect-density assumptions — no rigorous public treatment exists.
13. GLM-5 exact total parameters (zai card 744B vs media 753–754B): recompute from safetensors index; enumerate official GLM-5.x INT4/FP8 repos.
14. Simulator validity at batch 1–4 interactive agentic decoding on Blackwell (launch overhead and CPU scheduling dominate) — no published accuracy data.
15. Is DeepSeek's Feb-2025 economics disclosure still representative post-V4/DSA? No update exists; consider replicating their setup on rented H200s to re-anchor.

---

## 7. Researcher-Flagged Gaps (by area)

**Model architectures:** DeepSeek-V4 config gated (401) — all V4 numbers unverified; GLM-5.x total-param discrepancy (744B vs 753–754B); DSA indexer key-cache footprint excluded from KV totals; MiniMax-M1 linear-attention state size not derivable from config; Qwen3-235B-A22B-Instruct-2507 config not pulled; GLM-5.x quant repos beyond FP8 not enumerated.

**SOTA serving:** no public 2025–26 update to DeepSeek's economics disclosure; no public GLM-4.5/4.6 or Qwen3-30B-A3B production-batch benchmarks; MI300X/MI355X absolute tok/s/GPU for DeepSeek-class not extracted (scrape the InferenceMAX dashboard); large-batch wide-EP MBU unpublished; no systematic vLLM-vs-SGLang overhead decomposition; Artificial Analysis hardware benchmark page worth scraping.

**Hardware economics:** LPDDR5X/GDDR7 $/GB missing; measured decode power on B200/GB200/MI355X missing; modern-node (N4/N3) FP8/FP4 MAC energy table not public (need ISSCC 2024–26); N3/N4 defect density undated; minimum economical ASIC volume has no rigorous public model; GB200 reserved/contract pricing private.

**Simulators:** no head-to-head roofline-vs-measured $/token study across models/GPUs at production batch; ASTRA-sim validation figures secondhand — verify in primary papers before deck use; self-reported simulator errors lack independent replication; no accuracy data for batch 1–4 agentic workloads on Blackwell; none of these tools cover the TCO layer (sartor builds its own).

**Custom silicon:** no independent Etched benchmark; no matched-SLA cross-vendor $/Mtok; Groq/Cerebras internal cost per token unknown; Maia 200/MTIA v2 have no external $/token data; TPU $15K unit cost is secondhand; no analyst treatment of weights-frozen per-model ASIC economics.

**Model-side levers:** no NVFP4/MXFP4 numbers on sub-2B models; 2-bit KV quality on reasoning-tuned small models contested; no e2e $/token measurements for MLA retrofits under real serving; quantization × sparsity × MLA stacking unmeasured; per-tensor bandwidth breakdown for sub-2B unpublished; no ternary retrofit evidence; Minitron economics below 500M unpublished.

**Market prices:** SemiAnalysis margin figures paywalled (via snippets — verify before external use); DeepSeek off-peak discount status unclear; Groq/Cerebras prices via aggregators, not primary pages; no provider publishes actual cache-hit serving cost; Anthropic fleet cache-hit rates are client-side telemetry, not official.
