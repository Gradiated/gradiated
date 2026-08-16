# FP8-KV byte and execution-contract reconciliation

## Decision question

What is the exact pinned vLLM FP8 per-token-head KV byte contract for Gemma 4 31B, and what per-layer or tiled CUDA arm can test it without materializing all layers and requests as one monolithic BF16 tensor?

This project is `$0` offline scientific reconciliation. It must not mutate, poll, repair, or wait for the live L40S owner. It does not gate the paid project's primary-result persistence correction and cannot claim CUDA support or endpoint performance.

## Why now

The live exact-shape owner reached CUDA and entered its conditional KV arm only after all primary FP8 linear gates passed. The KV harness then attempted a 28.29 GiB allocation for `tokens x 450560` BF16 scalars and OOMed before its buffered primary results were written. Separately, the completed local-window bound derives 0.363423 GiB per primary request from the source-stated one-byte value plus per-token-head scales, while the earlier FP8-KV packet reports 0.558736 GiB. The discrepancy changes L40S capacity claims and the corrected arm geometry, so resolve it independently while the durable owner retains exclusive provider control.

## Authoritative inputs

- `../fp8_kv_c8_retained_arm/FP8_KV_ARM.json`
- `../fp8_kv_c8_retained_arm/PINNED_SOURCE_EXCERPT.md`
- `../sliding_window_capacity_cost_bound/WINDOW_BOUND.json`
- `../exact_geometry_runtime_opportunities/GEOMETRY.json`
- `../gemma_l40s_fp8_exact_shape_microbench/gemma_exact_shape_microbench.py`
- `../gemma_l40s_fp8_exact_shape_microbench/artifacts/gemma-l40s-fp8-exact-shape-20260717t001000z/gemma-l40s-fp8-exact-shape.tar.gz`

Bind every conclusion to content hashes. Use only existing local source and artifacts; no network or provider calls.

## Immediate experiment

1. Reconstruct the exact scalar and scale bytes per token for each local and global layer from the pinned vLLM launch/scale contract. Explain whether scales are per tensor, token, head, and K/V, and identify every allowance responsible for the 0.363423 versus 0.558736 difference.
2. Recompute c1/c4/c8 and 10K residency under both interpretations, separating logical model KV residency, allocator/block rounding, workspace, and benchmark transient tensors. Mark which numbers are source-exact, conservative allowances, or inconsistent.
3. Diagnose the live harness geometry: compare its `tokens x 450560` all-layer BF16/FP8/recovered tensors with actual per-layer runtime allocation and access. Quantify peak transient bytes and why its OOM is a harness result rather than an FP8-KV capacity result.
4. Produce one corrected, start-ready arm specification for the existing paid project: atomically persist primary rows first; test actual local/global per-layer shapes with bounded tiles or streaming; record peak allocation, numerical checks, and the explicit scale identity; never infer endpoint throughput. It must fit the paid project's existing identities and budgets and require no checkpoint or second concurrent owner.

Close with one authoritative byte contract or a typed unresolved disagreement. Do not edit the paid project or create a provider resource.

## Artifacts and budgets

- Terminal artifacts: `KV_CONTRACT.json` and `CORRECTED_ARM.md`.
- Wall clock: 30 minutes.
- Compute: at most 1 local CPU-hour; no CUDA.
- Storage: at most 128 MiB.
- Provider mutation and spend: prohibited; `$0`.

