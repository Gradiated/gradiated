# Layer-depth architecture proxy

## Question

Can removing a small, recoverable set of complete GLM-4.7 Flash transformer blocks reduce L40S c16 cost by at least 10% or unlock a materially better memory operating point?

## Why it matters

The output-head and MLA-rank lanes are closed, while fixed top-k/shared execution has only one narrow paid candidate. GLM-4.7 Flash has one dense block followed by 46 repeated MoE blocks. Removing five complete blocks is an idealized 10.6% depth reduction and simultaneously removes attention, routing, routed/shared expert work, weights, and one MLA cache slice per block. At the existing full c32 geometry, five of 47 KV slices represent about 1.58 GiB before weight savings; this can cross a capacity boundary that rank-only MLA did not convert into endpoint value. The proxy changes semantics and assumes later distillation or recovery training.

## Scope

Use the exact AWQ/BF16 tensor indexes, 47-layer configuration, retained c16 traces, current memory bounds, and [`../../hardware/L40S.md`](../../hardware/L40S.md). At `$0` provider spend, quantify per-block weight bytes, KV bytes, kernel launches, traced work, and the minimum number of removable blocks needed for the committed-price 10% gate and for c32 or a cheaper memory tier. Compare only a few defensible whole-block patterns—such as evenly distributed versus a model-derived low-sensitivity set—and explain the recovery burden. Do not change top-k, shared-expert execution, ranks, widths, precision, or the output head.

Build the smallest executable vLLM model-forward proxy that bypasses one selected set of complete blocks while preserving hidden-state shape, residual flow, model identity reporting, and a fail-closed stock mode. Prove the exact source switch and tensor/load implications locally; do not run a provider, train, or perform broad quality evaluation. Use cheap checkpoint-derived sensitivity evidence when available, but do not turn this into a literature survey or claim that static norms establish quality.

Map the candidate to L40S: report eliminated routed/shared expert weight traffic, MLA/cache state, launch waves across 142 SMs, and whether the reduced footprint actually changes c16/c32 admission or a cheaper-chip placement. Calibrate trace-derived work against measured endpoint transfer and keep overlapping summed durations out of the wall-time claim.

## Resources

- Current control: 535.286 output tok/s and about `$0.571/M` at the `$1.10/hour` planning rate.
- Current checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Complete BF16 tensor geometry: `/root/.cache/glm47flash-bf16-33faccf4`.
- Retained traces and launchers: `campaign_100/`.
- Closed MLA evidence: `projects/l40s_model_chip_codesign/RANK_TILE_BOUND.json`.

## Decision

Nominate at most one whole-block skip pattern for a later matched c16 measurement only if its conservative endpoint and capacity accounting supports at least 10% lower sustainable cost, the executable proxy is source-bound, and modest recovery is plausible. Otherwise close depth reduction and return capacity to an early-exit or trained draft-head lane. This project has no provider authority or spend.
