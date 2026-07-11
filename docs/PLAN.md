# Sartor — Master Plan

*Living document. Started 2026-07-11. This is the plan for validating the company thesis; edit freely, I (Claude) keep it current as work progresses.*

## 0. Thesis

**Company**: an auto-research platform that, for each open-source model, co-designs the entire serving stack — serving software, kernels, hardware configuration, eventually custom silicon — and applies small model-architecture modifications, to minimize **$/token** (a TPS-optimized variant later; the objective is a pluggable function).

**Why now**: software is approaching zero marginal cost to produce (AI writes it). The prevailing stack (vLLM/SGLang on NVIDIA, hosted by Fireworks/Baseten) pays a large *abstraction tax* to be general across hundreds of models, hardware targets, and latency SLOs. A per-model, per-objective, ground-up stack should recover that tax. Separately, decode cost is dominated by memory bandwidth; small model-side modifications (mixed-precision tensor assignment, KV compression, attention restructuring) attack the physics directly, not just the software.

**End goal**: compete with Fireworks/Baseten on $/token for hosted OS models. Near goal: build the **end-to-end simulation environment** that makes cross-layer hypotheses cheap to test, and use it + a real local lab to prove (or honestly disprove) that ~5–10× $/token vs today's norms is achievable per model.

**Kill criteria are as valuable as success**: if the calibrated environment shows the ceiling is ~1.5–2× and shrinking, that is a decision, documented for investors, not a failure of the project.

## 1. What we're building

Two coupled artifacts, one repo:

1. **The real lab** (`crates/engine` — "barge"): a from-scratch Rust serving engine (candle backend, Metal+CPU) that actually serves small models on the M4 Pro. It is simultaneously:
   - the proof that a custom stack beats vLLM serving the same model on the same hardware,
   - the calibration source for the simulator (measured MFU/MBU/overhead curves),
   - the *functional twin* for model-side interventions (does the tweaked model still work? perplexity/task checks + real speedup measurement).

2. **The simulator** (`crates/spec`, `crates/perf`, `crates/cost`): an analytical roofline + discrete-event model of the full stack. A run is a pure function: `(ModelSpec, HardwareSpec, KernelSpec, ServingSpec, WorkloadSpec, Objective) → {tok/s, joules/tok, $/Mtok, breakdowns}`. Hardware specs range from real (M4 Pro, H100, H200, B200, MI300X) to hypothetical (LPDDR-heavy decode chips, per-model ASICs). **Trust discipline**: the sim is only trusted where pinned by (a) our lab measurements or (b) public benchmark anchors; every prediction carries a calibration status.

**The experimentation loop that IS the product**: hypothesis → edit one spec (or one engine component) → sim predicts Δ$/token → (when local) lab verifies → ledger entry. The environment's quality is measured by how cheap that loop is and how small the sim-vs-real error is.

## 2. Repo layout

```
sartor/
  crates/
    spec/      shared schemas: ModelSpec, HardwareSpec, KernelSpec, ServingSpec, WorkloadSpec, Objective
    perf/      performance sim: per-op roofline + batching/parallelism + serving DES
    cost/      $ model: BOM, amortization, power, PUE → $/Mtok; pluggable objectives
    engine/    barge: real Rust serving engine (candle; Metal+CPU)
    cli/       sartor CLI: run experiments, sweeps, calibration checks, ledger
  experiments/ stack configs (TOML) + results (JSONL) — committed, reproducible
  models/      local weights (gitignored): SmolLM2 135M/360M/1.7B, Qwen2.5-0.5B, Qwen3-0.6B,
               granite-1b-a400m (MoE), GGUFs incl. Qwen3-30B-A3B Q4
  data/        ShareGPT (workload), wikitext-2 (quality proxy)
  vendor/      reference clones: vllm-study (../vllm-study), sglang, llama.cpp, LLMCompass,
               vidur, candle, GenZ, accelergy, flashinfer
  docs/        PLAN.md (this), REPORT.md (living findings+ledger), DESIGN.md, calibration.md,
               vllm-cost-dissection.md, papers/, model-configs/ (GLM/DeepSeek/Qwen3/Kimi/gpt-oss)
```

## 3. Workstreams (subagent-parallelizable)

**WS1 — Real lab** *(critical path; main thread + review agents)*
- barge engine: llama-family forward, slot-based preallocated KV (no paging — measured bet, see DESIGN.md), continuous batching with chunked prefill, minimal sampling, OpenAI-compatible axum server, offline bench harness producing vLLM-comparable metrics.
- Baselines on the same machine, same model, same workload: vLLM (CPU backend — its only macOS option; also its Python overhead measured directly), llama.cpp (`llama-server`, Metal — the strong local incumbent), HF transformers (naive floor).
- Correctness: logits parity vs candle-transformers reference; batch-of-1 ≡ batch-of-N invariance; streaming detok correctness.
- Model interventions v1: per-tensor mixed precision (which tensors eat bandwidth → quantize exactly those), KV dtype (f16 vs q8), tied-embedding exploitation; each measured for speed AND wikitext perplexity delta.

**WS2 — Simulator** *(main thread designs schemas; subagents implement + test components)*
- spec: serde schemas + validation + builders from real config.json files.
- perf: op graph from ModelSpec → per-op (FLOPs, bytes) → time via hardware roofline with efficiency curves; serving DES on top (arrivals, batching policy, KV occupancy, tiering); MoE + TP/EP/PP comm terms for big-model mode.
- cost: BOM/energy/amortization tables (constants from WS3 research) → $/Mtok with prefill/decode split and utilization.
- Calibration harness: `sartor calibrate` runs sim against (a) barge measurements on M4, (b) public anchor table; reports error per anchor; CI-style regression.

**WS3 — Research/data** *(workflows; running now)*
- vLLM dissection ✅ done (12 agents) → distill to docs/vllm-cost-dissection.md.
- Economics/SOTA research workflow → docs/research/*.md + calibration constants table.
- Assets: models, datasets, repos, papers, configs ✅ downloading.

**WS4 — Experiments & ledger** *(after G2; sweeps via cli, analysis agents)*
- Layered ledger: each lever gets baseline → delta → cumulative, with calibration status (measured / sim-calibrated / sim-extrapolated).
- First campaign on SmolLM2-135M + Qwen2.5-0.5B (below). Second campaign: Qwen3-30B-A3B (GGUF real; sim for GPU-class hardware). Third: GLM-class (sim-only, config-parameterized).

**WS5 — Reporting** *(continuous)*
- docs/REPORT.md: findings + optimization ledger, updated every session.
- Investor memo at the end: environment demo, calibration table, ledger, Pareto charts, verdict on 5–10×, roadmap to custom silicon (NRE math from WS3 data).

## 4. Phases & gates

**P0 — Foundations** (today)
Assets downloaded; workspace builds; plan agreed.
*Gate G0*: engine generates correct text from SmolLM2-135M on Metal (parity test passes); ≥1 baseline (llama.cpp or vLLM-CPU) runs the same model locally.

**P1 — Beat vLLM on a small model, real hardware** (days 1–3)
Full barge serving loop + bench harness; tuned baseline runs; first ledger entries (software-layer wins, quantified: scheduler overhead/token, detok, IPC, batching curves).
*Gate G1*: barge > vLLM on tokens/sec/$ for the ShareGPT-derived workload on this machine — target ≥2× vs vLLM-CPU like-for-like (barge-CPU), with barge-Metal reported as "use all the silicon" headline; honest caveats recorded. Also: barge within ~1.3× of llama.cpp-Metal throughput (sanity that we're not just beating a strawman).

**P2 — Simulator calibrated** (days 3–6)
Sim v1 + calibration harness.
*Gate G2*: sim reproduces barge M4 measurements (batch sweep 1→64, prefill+decode, 2+ model sizes) within ±20%; reproduces ≥5 public GPU anchors (H100/H200 class from research WS3) within ±50%; every constant sourced.

**P3 — Close the auto-research loop** (days 6–9)
Model-side + serving-side interventions driven BY the sim, verified in the lab.
*Gate G3*: ≥1 intervention where sim predicted Δ$/token within ±30% of measured, with quality proxy loss ≤1% (e.g., mixed-precision tensor assignment chosen by the sim's bandwidth model). This gate is the company: prediction → cheap experiment → verified win.

**P4 — Co-design study & verdict** (days 9–14)
Full-stack optimization campaign per model (software × model-mods × hardware specs incl. hypothetical silicon); Pareto frontiers; extrapolation to GLM-class MoE with error bars; NRE/volume math for per-model ASICs.
*Gate G4 (the verdict)*: documented multiplier vs "vLLM on H100 at Fireworks-like utilization" baseline, decomposed by layer, with confidence tiers — and a go/no-go recommendation.

## 5. First experiment campaign (small model, concrete)

Model: SmolLM2-135M-Instruct (+ Qwen2.5-0.5B to avoid overfitting to one config). Workload: ShareGPT-derived, batch-API style (no latency SLO), fixed token budget. Metric: tokens/sec at saturation on fixed hardware ≡ relative $/token.

| # | Lever | Layer | How tested |
|---|-------|-------|-----------|
| 1 | Kill Python/IPC/abstraction tax (whole custom engine) | serving | barge vs vLLM, same hardware+model |
| 2 | Slot KV vs paged KV bookkeeping | serving | barge ablation + vLLM block-size sweep |
| 3 | Chunked prefill ratio / token budget | serving | barge ablation |
| 4 | Batch size → saturation curve | serving | barge sweep (the $/token vs latency frontier) |
| 5 | Sampling placement (GPU argmax vs CPU top-p) | kernel | barge ablation |
| 6 | f16 vs bf16 vs mixed per-tensor precision | model | barge + perplexity check |
| 7 | KV cache dtype (f16 → q8) | model | barge + perplexity |
| 8 | Weight layout / fusion opportunities (QKV fuse, gate+up fuse) | kernel | barge ablation |
| 9 | Tiered KV (RAM↔SSD) for oversubscription | serving | barge (Mac unified mem) + sim |
| 10 | Hypothetical: same model on LPDDR-rich vs HBM chip | hardware | sim (calibrated by 1–9) |

## 6. Metrics

- **$/Mtok** = (hardware $/hr ÷ 3600 + watts × $/J) ÷ (tokens/sec) × 10⁶, computed separately for prefill/decode and blended by workload mix. On the local lab, hardware is fixed → relative $/token ≡ relative throughput at saturation; the cost crate supplies real $ for datacenter specs.
- **Quality proxy** (for model mods): wikitext-2 perplexity delta + a small instruct sanity suite; hard gate at ≤1% relative ppl unless explicitly exploring the frontier.
- **MBU/MFU**: achieved vs roofline — the sim's core internal currency.
- **Loop cost**: wall-clock from hypothesis to ledger entry (the environment's own KPI).

## 7. Risks & honesty clauses

1. **M4→datacenter transfer**: Apple silicon ≠ H100. Mitigation: sim carries per-hardware efficiency curves calibrated separately; all extrapolations labeled.
2. **vLLM-on-Mac is a weak baseline** (CPU-only): we report barge-CPU vs vLLM-CPU (like-for-like) AND barge-Metal vs llama.cpp-Metal (strong incumbent) — never only the flattering one.
3. **Small-model overhead bias**: tiny models exaggerate software-tax wins. Mitigation: replicate key results at 1.7B and 30B-A3B (GGUF); sim separates fixed overhead from scaling terms.
4. **Sim wishful thinking**: no redesign claim ships without a calibration-status label; G2 error bars propagate to every extrapolated number.
5. **SOTA moves** (vLLM v1 improves, SGLang, TRT): baseline table dated; thesis rests on structural tax, not a snapshot.
6. **Per-model ASIC economics**: model release cadence vs 12–18mo silicon cycle + NRE — addressed head-on in P4 with WS3 numbers; "per-model" may soften to "per-architecture-family" (the honest version).
7. **Quantization quality claims at small scale**: small models degrade faster; we measure, not cite.

## 8. Immediate next actions

1. ✅ All downloads + research workflow running.
2. Distill vLLM dissection → docs (agent).
3. barge engine core (main thread): G0 by end of day.
4. llama.cpp Metal build + baseline harness (agent).
5. vLLM CPU build finishes → baseline harness (agent).
6. spec crate schemas once research constants land.
