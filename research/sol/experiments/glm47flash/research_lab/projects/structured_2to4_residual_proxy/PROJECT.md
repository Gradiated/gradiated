# Structured 2:4 residual cost proxy

## Question

Can Ada-native 2:4 structure applied only to the current AWQ checkpoint's BF16 residual families—output head, shared experts, and dense layer 0—create a source-supported, recoverable L40S cost mechanism with a conservative path from `552.171055` to at least `606.355` output tok/s?

## Why this matters

The campaign explicitly names supported 2:4 structure as an untested alternative to the mixed W4/BF16 representation. Routed experts are already W4, but approximately 605 MiB of output head, 828 MiB of shared experts, and 161.5 MiB of dense layer-0 linears remain BF16. Prior selective-FP8 work stopped because the immutable checkpoint has no mixed FP8 or sparsity scheme; it did not measure a newly imposed 2:4 architecture-cost proxy. The target mechanism is combined critical-path work and representation, not another head-only or shared-only ceiling.

## Fixed evidence

- Exact current checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, with config/index/manifest identities already retained by the r3 project.
- Current endpoint: `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`, `552.1710554232396` output tok/s at exact cache-off 8,192/1,024 c16.
- Economic gate: `$1.10/L40S-hour`, `$0.514/M`, ordinary threshold `594.466` tok/s and robust nomination threshold `606.355` tok/s; every later target arm must complete inside 300 seconds.
- Consume `../selective_fp8_residual_architecture/`, `../output_head_architecture/`, `../lm_head_w4_bridge/`, and `../minimal_change_c32_codesign/CANDIDATE_COMPARISON.json` as fixed evidence. Do not rerun their FP8, W4, factorization, or broad residual screens.
- L40S/SM89 supports structured sparse Tensor Core execution, but peak sparse FLOPS are only a prior. The pinned/current runtime must expose an exact format, loader, and kernel route for the candidate shapes; an empty checkpoint sparsity map is not such a route.
- The prior head/shared trace fractions are diagnostic ceilings from a different c8/128 observer geometry. Never add overlapping durations or treat them as target endpoint shares.

## Scope and stop rule

Within 1,200 seconds, 16 GiB RSS, 96 MiB new artifacts, and `$0`, bind the exact BF16 residual tensor set, shapes, bytes, and layer coverage. Apply one deterministic per-output-channel magnitude 2:4 mask proxy without changing routed W4 tensors. Report retained-weight and output-error diagnostics on exact weights, separately for head, shared experts, and dense layer 0; this is recovery-burden evidence, not quality.

Audit the pinned vLLM 0.15.0 stack and at most one current stable source tree for an unchanged SM89 semi-structured representation, loader, and GEMM path that supports the exact `[M,2048]` and 1,536-width families. A generic PyTorch API, CUTLASS example, source string, peak-FLOPS claim, or custom-kernel possibility does not pass. Quantify physical compressed bytes including metadata/alignment, c32 memory headroom against the 46,068-MiB envelope, exact small-`M` tile geometry, and the maximum endpoint/cost path under conservative transfer and conversion overhead. Distinguish a cost-only route from a capacity-discontinuity route.

Return exactly one terminal result:

- `NOMINATE_2TO4_COMPONENT`: exact source-supported SM89 representation/dispatch exists, the proxy's recovery burden is bounded, and conservative endpoint or cheaper-placement accounting reaches `606.355` tok/s-equivalent with one smallest later L40S component falsifier specified but not prepared;
- `RUNTIME_CLOSE`: no exact unchanged loader/kernel route exists for the combined residual families; or
- `ECONOMIC_CLOSE`: a valid representation exists but conservative endpoint/capacity economics miss the robustness gate.

Do not allocate CUDA/provider resources, mutate any checkpoint or shared runtime, write a custom sparse kernel/loader, train, run broad quality, or prepare a provider controller. Produce one compact decision JSON, a reproducible project-local proxy/source audit, and a concise research-log result.

## Available resources

Use `hardware/L40S.md`, the shared accelerator inventory, local checkpoint/source caches, the named project artifacts, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

