# SM89 FP8 MLA KV kernel

## Decision question

Can one source-pinned SM89 kernel path write, scale, store, and attend over the exact GLM-4.7 Flash MLA cache in FP8 while retaining BF16 query/output compute, enough to improve every long-context B32 component point before a full-model c32 endpoint?

This is a kernel implementation project, not another stock-backend support survey. Use the cached vLLM `0.25.1` implementation only as a reference; preserve the campaign's `0.15`-derived serving-runtime identity. Offline `.to(fp8)`, decode-only dequantization, and a scale fixed to one do not answer the question.

## `$0` component contract

- Implement the smallest Triton backport containing both cache writer/quantization and attention decode, with an explicit scale policy and saturation diagnostics. The runner must actually invoke both kernels; source presence or byte arithmetic is not execution evidence.
- Freeze stock geometry first: page size 16; `BLOCK_H=16`, `BLOCK_N=32`, 4 warps, 2 stages, 4 splits; BF16 Q `[B,20,576]`; cache `[pages,16,1,576]`; value alias `:512`.
- Use seed 1234, shuffled page tables, a masked FP32 oracle, context lengths `8193, 8449, 8705, 8961, 9215`, and `B in {1,8,32}`.
- Record exact allocated cache bytes, compile/launch parameters, FP8 scales and saturation, output/LSE error, warmup, p50, and p95 for writer/stage-1/full-attention BF16 control versus FP8.
- Pass only if all outputs are finite, output is within `atol=0.03, rtol=0.03`, LSE within `atol=0.10, rtol=0.03`, no fallback or saturation occurs, allocated bytes are exact, and every B32 length improves p50 by at least 10% in both stage 1 and full attention with no p95 regression.

The exact c32 MLA BF16 cache band is `15,967,715,328` bytes (`15,228 MiB`). Under the implemented per-token FP32 scale policy, FP8-plus-scales saves `7,561.125 MiB` (`49.65278%`), projecting stock c32 to about `39,314.575 MiB`, or `5,217.425 MiB` below the robust memory ceiling. That is capacity evidence only until a correct kernel executes.

Use the already-local pinned image `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`, which contains Python 3, PyTorch 2.9.1+cu129, Triton 3.5.1, and nvcc 12.9. Do not install another stack. One material correction must bind shuffled page tables, head/page indexing, `BLOCK_N`, splits, masking, actual writer/decode invocation, and sampled CPU/static numerical checks before any GPU request. A serial `MAX_CONTEXT` loop, unused head index, or intentionally unwired runner closes the implementation.

## Endpoint admission

Do not create, mutate, or spend while the combined W4 owner is live. A component pass may nominate one later full47 c32 server arm using the proven durable launcher: actual peak `<=44,532 MiB`, 32 complete requests within 300 seconds, semantic pass, throughput `>=594.466 tok/s` for economic viability and `>=606.355 tok/s` for the robust target. The ordinary component controller cleans up. Component-to-server retention is allowed only through the existing retained-session recovery path, with one sequential owner/watchdog and a named preregistered trigger; otherwise clean normally.

## Starting evidence

- `../full_model_fp8_kv_c32_corrected/`
- `../../../campaign_100/allocations/nebius_l40s_mla_microbench_v23r1/`
- cached vLLM `0.25.1` MLA kernels as source reference only
- `../../hardware/L40S.md`
