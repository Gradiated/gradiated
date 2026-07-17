# Gemma 4 native-MTP acceptance and economic bound

## Decision question

Can the official four-layer Gemma 4 assistant plausibly reduce sustainable cost by at least 5% for the exact 4,214-input/358-output background workload, and what measured acceptance/verification gate would justify one later matched MTP arm?

## Scope and inputs

This is independent `$0` decode-strategy evidence while the corrected W4 consumer owns provider mutation. Start from:

- `../exact_geometry_runtime_opportunities/ADJACENT_ARM_PACKET.json`, SHA-256 `53ad920c00ee4acf224ebb135b5dbff3488897e71e432c5ee93732190d2db08f`;
- `../exact_geometry_runtime_opportunities/GEOMETRY.json`, SHA-256 `024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72`;
- `../exact_market_venue_decision_surface/MARKET_TARGET.json`, SHA-256 `5d636809dc25450050c565cdc108bf7e91eaa60ce07c027ca390c8011e3b8e51`;
- fresh shared price SHA-256 `3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01`.

Bind the target and assistant revisions recorded in the packet. Freeze its old vLLM source assertion as historical; runtime support is a conditional and no result transfers across the currently observed image runtime without later execution.

## Required evidence

Build a reproducible analytical/simulation surface over accepted draft length, target verification cost, assistant cost/residency, decode fraction, batch/concurrency, and H100/L40S planning rates. Account separately for prompt prefill, 358-token decode, the 0.939-GB assistant, shared KV, target verification passes, rejected tokens, scheduler overhead, and quality-preserving exact-greedy versus sampled operation. Do not assume one accepted token eliminates one full target pass without source support.

Derive the minimum mean accepted tokens per draft and maximum proposer/verification overhead needed for 5%, 10%, and market-break-even all-in improvement on: exact BF16 H100, and conditionally W4 L40S if an exact-revision representation later exists. State capacity effects at c16/c32. Compare against async scheduling as the no-extra-weights fallback. Return at most one later matched arm with exact telemetry fields (`accepted_tokens`, draft/verify calls, output IDs, complete requests, phase wall times, HBM/power) and a hard negative gate. Emit typed `none` if the required acceptance or cost ratio is implausible even under optimistic bounds.

No provider, CUDA, full weights, quality execution, or waiting on the live project. This is derived/synthetic evidence, not endpoint performance.

## Budgets and artifacts

- Wall clock: 45 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 1 GiB project-local; no shared `/tmp`.
- Spend: `$0`.

Write a reproducible script, `MTP_BOUND.json`, concise `DECISION.md`/`RESEARCH_LOG.md`, and terminal `STATUS.json`.
