# Text-only vision unload and 24-GiB placement bound

## Decision question

Can the initial text-only, non-reasoning Gemma 4 31B mode omit the vision tower/projector at load time without changing text outputs, and does that create a credible 24-GiB W4 placement with materially lower all-in cost?

## Why now

The campaign explicitly treats vision as a later separate product mode. The corrected W4 accounting places 3.753 GB of vision/small higher-precision remainder in residency but not active text decode traffic. Removing only truly vision-exclusive tensors could create a capacity discontinuity from 48-GiB L40S to cheaper 24-GiB hardware; unlike another isolated kernel benchmark, this changes placement economics.

## Authoritative inputs

- `../gemma_l40s_w4_c16_economic_bound/W4_C16_BOUND_V2.json`, SHA-256 `b697e8c43bcdecac9b0261ab79e363b39e11e9c37a0be282d357a21c9e24fe9d`.
- `../exact_geometry_runtime_opportunities/GEOMETRY.json`, SHA-256 `024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72`.
- `../exact_market_venue_decision_surface/MARKET_TARGET.json`, SHA-256 `5d636809dc25450050c565cdc108bf7e91eaa60ce07c027ca390c8011e3b8e51`.
- Shared accelerator inventory SHA-256 `bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8` and fresh price SHA-256 `3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01`.

## Required evidence

Use exact checkpoint index metadata and first-party/current runtime source to separate byte-exact vision tower, multimodal projector, text embedding/head, language layers, and shared tensors. Do not subtract the existing combined remainder wholesale. Determine whether the runtime can avoid allocating/loading vision-exclusive tensors for text-only requests while preserving tokenizer, chat template, text layer graph, tied embedding/head, stop behavior, and local/global attention. A code-path proposal is allowed as an explicitly non-quality-certified intervention; source inspection is not proof of output equality.

Recompute W4 plus runtime reserve plus source-bound FP8 KV at c1/c2/c4/c8 and 10K on a conservative usable envelope for 24-GB cards. Include allocator/page rounding and at least L4, A10, and RTX 4090-class inventory priors when present, but do not transfer throughput or invent missing production prices. Derive the maximum price/throughput ratio needed to beat L40S and identify whether bandwidth makes the placement uneconomic even if it fits.

Return at most one direct 24-GiB nominee only if byte-exact capacity leaves at least 1 GiB post-reserve headroom at a decision-relevant concurrency, current runtime/source has an implementable text-only unload path, and a 10% all-in cost improvement is plausible. The later measurement must use raw text-output/logit comparison against the unmodified exact checkpoint and must explicitly forfeit vision eligibility. Otherwise emit typed `none`. Do not wait for or poll the W4 owner.

## Budgets and artifacts

- Wall clock: 45 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 1 GiB project-local and at most 128 MiB bounded metadata/source probes; no shared `/tmp`.
- Spend: `$0`; no provider mutation, full weights, compilation, or quality execution.

Write `VISION_UNLOAD_BOUND.json`, concise `DECISION.md`/`RESEARCH_LOG.md`, and terminal `STATUS.json`.
