# Sartor — full-stack inference co-design research

Started 2026-07-11. Question: can per-model co-design (custom serving software,
finetune-healed model surgery, and eventually model-family-fitted silicon) host
open-source LLMs materially cheaper than Fireworks/Baseten-class providers?
This is the working research environment, not a product — read `docs/REPORT.md`
for the living evidence ledger and verdict.

## Start here

1. **`docs/REPORT.md`** — the living report. Opens with an executive summary
   and a "morning summary" of the most recent overnight research push. This is
   the single most information-dense file in the repo.
2. **`docs/sartor-report.html`** — the shareable, non-technical version (open
   it in a browser). Same findings, written for a founder/investor audience,
   with expandable technical detail.
3. **`docs/calibration.md`** — how much to trust any given number (realization
   factor, duty cycle, known gaps). Read this before quoting an absolute
   $/Mtok figure from anywhere else in the repo.
4. **`docs/business-model.md`** — unit economics, margin phases, capex gates.

## Current headline verdict (see REPORT.md for the up-to-date version)

Co-design gain vs provider-best practice: **median ~3.9× [P10 2.9, P90 5.0]**,
P(≥3×) ≈ 88%, stable across three generations of priors including ones
corrected downward by real experiments (see twin-surgery-round2.md — matched
controls overturned an early optimistic read on head-pruning and CLA surgery).
Per-model headroom varies 4–7× — target under-optimized model families first
(MiniMax-M2 class), not the most famous ones (GLM/DeepSeek already harvested
their own efficiency).

## Repo structure

```
crates/
  spec/      shared config schemas (ModelSpec incl. GQA/MLA/MoE/DSA, HardwareSpec,
             KernelSpec, ServingSpec, WorkloadSpec, CostSpec, ParallelSpec)
  perf/      performance simulator: per-op roofline + closed-loop serving-loop
             replay + trace.rs (byte-exact per-op decode trace)
  cost/      $/Mtok model (amortized capex + power)
  engine/    "barge" — real from-scratch Rust LLM serving engine (candle/Metal),
             the calibration ground-truth + functional twin for model surgery
  cli/       "sartor" — run/sweep/trace/calibrate commands over TOML stack configs

experiments/
  configs/   stack-config TOMLs (lab models + datacenter anchors incl. DeepSeek
             H800, SGLang GB200, GLM-5.2)
  anchors/   measured-vs-simulated calibration anchor files
  results/   raw output of every study/sweep/MC run (jsonl/txt)
  moat_study.py, moat_mc.py, moat_sensitivity.py  — the co-design study harness
             (Python driving the `sartor` CLI; these are the reusable
             experiment scripts, re-run any time with updated priors)

twin/        real-weights surgery + finetune-healing scripts (transformers/
             torch on MPS): head pruning, CLA KV-sharing retrofit, KV
             fake-quant sensitivity, MoE routing analysis (granite)

docs/
  REPORT.md                    living report + evidence ledger (START HERE)
  sartor-report.html           shareable non-technical version
  calibration.md               trust levels, known gaps
  business-model.md            unit economics
  PLAN.md                      original phased plan (P0-P4 gates)
  vllm-cost-dissection.md      12-agent audit of vLLM's abstraction tax
  experiments/*.md             per-study writeups (GLM-5.2 co-design + moat
                                studies, engine optimization rounds, twin
                                surgery rounds 1+2, per-model optimization logs)
  baselines/*.md               vLLM-CPU, llama.cpp, barge-server benchmarks
  research/*.md                131-source economics/hardware research corpus
  model-configs/                real config.json for GLM-4.5/4.6/5/5.2,
                                DeepSeek-V3.1/R1, Qwen3, Kimi-K2, gpt-oss

bridge/       live progress dashboard + prompt inbox, served at
              slackhog.ngrok.dev (see "Continuing this work" below)

models/, vendor/, data/   downloaded weights, reference repos (llama.cpp,
              sglang, LLMCompass, vidur, candle...), datasets — gitignored,
              21GB, present in the working copy at ~/dev/gradiated/research/fable
```

## What's real vs simulated (see calibration.md for full detail)

- **Measured on this machine**: barge engine correctness (parity to ~1e-5 vs
  candle-transformers), barge vs vLLM-CPU (2.1× measured), barge vs llama.cpp,
  op-level probes, real model surgery (head-pruning, KV quantization, CLA
  retrofit) with matched-control healing evaluations, MoE routing statistics
  on a real model (granite).
- **Simulated, anchored to public benchmarks**: everything at datacenter GPU
  scale (H800/B200/GB200) and all MoE-at-scale numbers — anchored to
  DeepSeek's and SGLang's published throughput, not our own GPU runs. The
  #1 de-risking experiment is renting real datacenter GPUs to replace this
  anchor with a direct measurement (~$15-25k, see REPORT.md next-experiments).

## Continuing this work

- **Resume the simulator**: `cargo build --release && ./target/release/sartor run --config experiments/configs/<name>.toml`
- **Resume the engine**: `cargo test -p barge --release` (parity gate — must
  stay green) then `./target/release/barge bench ...`
- **Re-run the co-design study**: `python3 experiments/moat_study.py` (edit
  priors/levers inline, or `moat_mc.py`/`moat_sensitivity.py` for uncertainty
  analysis)
- **The bridge** (live dashboard + prompt-to-Claude inbox): server is
  `bridge/server.py` (stdlib Python, run with any python3), tunnel is
  `ngrok http 8710 --domain=slackhog.ngrok.dev`. `bridge/lablog.jsonl` has a
  timestamped log of every research result from the session (58 entries as of
  the overnight run); `bridge/inbox.jsonl`/`outbox.jsonl` are the prompt/reply
  channel.
- **This repo**: working copy is `~/dev/gradiated/research/fable`
  (`~/dev/sartor` is a symlink to it for backward compatibility). Private
  GitHub: `github.com/joshsny/gradiated`. Commit directly in
  `~/dev/gradiated` and push.

## Honest open questions (not yet answered)

1. Does the cost model hold on real rented datacenter GPUs, not just public
   benchmark anchors?
2. Does model surgery survive a real healing campaign at 30-100B scale with
   distillation (twin experiments at 135M scale showed naive healing recipes
   fail the quality gate — recipe quality, not the concept, is unproven)?
3. What's the real achievable prefix-cache hit rate on live agent traffic
   (vs the 90-95% assumed)?
4. Can the business land enough steady batch volume early to hit the
   utilization assumptions the economics depend on?

See `docs/REPORT.md` → "Decisive next experiments" for costed answers to (1)-(3).
