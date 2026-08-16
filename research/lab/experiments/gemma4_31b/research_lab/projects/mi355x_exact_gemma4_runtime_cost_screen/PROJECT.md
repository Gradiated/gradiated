# MI355X exact Gemma 4 runtime and cost screen

## Decision question

Does one MI355X offer a current, content-bound vLLM or SGLang route for the exact pinned Gemma 4 31B text checkpoint whose production economics are plausible enough to justify one later matched endpoint measurement, or should the AMD venue be closed for this cycle?

This is independent `$0` venue/runtime evidence while the H200 experiment executes. It must not infer throughput from price, MI300X results, generic ROCm peaks, or vendor claims; failure of a provider venue is not a hardware-mechanism result.

## Authoritative inputs

- Exact model/workload/economic target: `../../CAMPAIGN.md`.
- Exact geometry and prior AMD nomination history: `../exact_geometry_runtime_opportunities/GEOMETRY.json`, `OPPORTUNITY_RANK.md`, and `../fp8_l40s_fit_economic_falsifier/RESEARCH_LOG.md`.
- Shared accelerator facts: `research/factory/data/accelerator_inventory.json` from the repository root.
- Fresh shared planning price: `research/factory/data/gpu_prices.json`; use `amd-mi355x` and do not relabel it MI300X.
- Current exact-model runtime/benchmark evidence, including reproducible public Gemma 4 and AMD studies when available.

## Required result

Search current primary/runtime sources and reproducible model-specific evidence. Return `MI355X_SCREEN.json` and `DECISION.md` with exactly one of:

- a content-bound later matched endpoint packet naming exact model revision, tokenizer/template, runtime commit/image, representation, workload, MI355X topology, current production planning rate/range, venue/access facts, comparator, quality boundary, first scientific arms, and the throughput/cost result that would change the portfolio; or
- typed none with the shortest measured or source-backed blocker.

Separate official runtime support from model-load evidence, benchmark scope, hardware availability, and written production pricing. Normalize only the economic hurdle; do not transfer H100/H200/L40S or other-model throughput. Do not download weights or image layers, compile, run CUDA/ROCm, create provider resources, contact vendors, or perform quality evaluation.

## Budgets

- Wall clock: 50 minutes.
- Compute: 2 local CPU-hours; no accelerator.
- Storage: 1 GiB project-local, including at most 256 MiB bounded source/metadata probes; no shared `/tmp`.
- Spend: `$0`; provider mutation and external messages are forbidden.

