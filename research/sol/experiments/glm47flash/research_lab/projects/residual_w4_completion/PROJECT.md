# Residual W4 completion

## Question

Can the checkpoint's existing compressed-tensors W4A16 group-32 scheme be extended to the currently ignored BF16 output head, dense layer-0 linears, and serving shared experts strongly enough to reduce L40S c16 cost by at least 10% or make a faster BF16-KV c32 point memory-admissible?

## Why it matters

The current AWQ config already targets `Linear` with symmetric 4-bit group-32 weights, but its explicit ignore list leaves `lm_head`, all dense layer-0 attention/MLP linears, and every shared expert in BF16. Prior exact-header accounting put this residual near 1.61 GiB, although that artifact included layer 47's separate MTP payload; stock serving has 46 shared-expert layers and must be recounted accordingly. The retained vocabulary-projection interval ceiling is 14.09%, and the lower shared/standard-Marlin ceiling is 7.10%. These are upper bounds rather than wall-time shares, but the joint residual is one of the few remaining measured paths with enough ideal headroom to cross the campaign gate.

This route is materially different from the closed selective-FP8 screen. It uses the checkpoint's existing W4 representation and Marlin family rather than introducing a second FP8 scheme and mixed loader. It may also save more than the roughly 808 MiB by which the stock BF16-KV c32 linear memory projection exceeds the L40S envelope. Memory admission alone is insufficient: the candidate still needs a credible path to at least 594.466 output tok/s at the `$1.10/hour` planning rate.

This is representation-changing architecture-cost evidence. Full quality and any recovery remain deferred until the cost mechanism is demonstrated.

## Scope

At zero provider spend, bind the exact current-AWQ config, safetensors index/headers, serving graph, vLLM 0.15.0 derived runtime, and retained c16 telemetry. Correctly separate stock layers 0–46 from layer 47's MTP payload. Recount the BF16 residual and evaluate three nested scopes—head only, shared experts only, and all ignored stock-serving linears—without opening separate projects.

For each scope, derive exact W4 packed-weight and scale tensor names, shapes, bytes, group-32/tile legality, quantization error on the existing BF16 tensors, and the compressed-tensors config changes. Prove or falsify loader and dispatch support for `lm_head`, dense layer-0 projections, and shared-expert modules in the actual derived serving image. Source presence is not a pass: build the smallest source-bound synthetic exact-shape fixture that exercises config selection, parameter mapping, and the intended Marlin method without transforming the full checkpoint or materializing a second model.

Map the exact c16 `M/N/K` shapes to the L40S's 142 SMs, 96 MB L2, register/shared limits, and W4 Marlin tiles. Use retained trace intervals only as ceilings and seek existing scope-matched component evidence where available; do not infer speed from the 4-bit byte ratio or nominal bandwidth. Recompute c16 and BF16-KV c32 peak memory with allocator/KV headroom and explain whether any admitted c32 geometry can actually improve background throughput once the residual kernels change.

Do not convert the full checkpoint, run a GPU, mutate a provider, train, repair unrelated loaders, change routed-expert weights, alter KV precision, edit the shared launcher, or perform broad quality evaluation. Do not attach this work to the live FP8 allocation.

## Resources

- Exact checkpoint and config: `/root/.cache/glm47flash-awq-ab31d120`.
- Residual tensor accounting and exact shapes: `../selective_fp8_residual_architecture/`.
- Output-head trace and spectrum evidence: `../output_head_architecture/`.
- Shared-expert trace bounds: `../adaptive_moe_architecture/artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json`.
- Current c16 control and saturation/memory bound: `../nebius_current_awq_c16_direct/` and `../current_awq_saturation_bound/`.
- Derived serving runtime identity: `../derived_runtime_mtp_binding/` and `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/`.
- L40S dossier and shared tooling: `../../hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Nominate at most one later matched L40S cost-proxy session only if the exact W4 config/loader/dispatch fixture passes and conservative transfer supports either c16 or an admitted BF16-KV c32 point at or above 594.466 output tok/s. The nomination must name one stock/candidate pair, exact checkpoint derivation inputs, semantic diagnostics, peak-memory and kernel counters, a bounded spend/timeout, and later quality requirements. A loader failure, sub-gate conservative bound, or memory-only c32 result closes residual W4 without checkpoint conversion or provider spend.
