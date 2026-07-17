# Corrected same-owner FP8-KV arm

Use this only after the existing paid owner has completed typed cleanup/reconciliation and elects its one in-place repair. This is a replacement specification for its broken conditional KV section, not permission to create an owner, a provider resource, or a second session.

## Fixed contract and accounting

Use `--kv-cache-dtype fp8_per_token_head` on the pinned Ada image. The cache payload is one E4M3 byte per K/V scalar plus one dynamic FP32 scale for each K token-head and each V token-head. For Gemma's local layers that is `4096 + 128 = 4224` bytes per resident token/layer; for global layers it is `4096 + 32 = 4128` bytes. `KV_CONTRACT.json` binds this calculation to the pinned input hashes.

At c8, source-exact logical KV is 2.907386 GiB at prompt end and 3.017492 GiB at the 4,572-token peak; with the inherited 39.350 GiB non-KV allowance, respective totals are 42.257386 and 42.367492 GiB. These are payload bounds. Emit the actual block size, rounded allocated bytes, PyTorch allocated/reserved/peak, and any backend workspace separately; do not turn them into throughput claims.

## Required sequence

1. Before any KV allocation, atomically write the complete primary linear rows and their `primary_fp8_pass` result to the owner artifact root (temp file, fsync, rename). A KV failure must leave those rows retrievable.
2. Consume the existing typed conditional trigger. If false, record it and let the existing `VerifiedRetainedOwner` clean up. Do not restart a server or allocate the KV arm.
3. If true, reset CUDA peak stats and run the cache writer/readback by layer kind, never as `tokens x 450560` or a tensor concatenating 60 layers.
   - Local arm: per layer, maintain the c8 resident cache shape `[8*1024, 2, 16, 256]` (65.0 MiB FP8 payload including scales); stream a 128-token tile through BF16 -> dynamic K/V-head scales -> E4M3 -> readback.
   - Global arm: per layer, maintain `[8*4214, 2, 4, 512]` for the primary input (132.716 MiB including scales); stream the same 128-token tile path. Extend only to `[8*4572, 2, 4, 512]` for the registered peak check.
   - Process all 50 local and then all 10 global layers sequentially, releasing each layer cache before the next. This is a cache-writer/readback component arm, not a claim that every live vLLM layer is simultaneously materialized by this harness.
4. For each kind and token point, record shape, cache value dtype, scale dtype/shape, scale mode (`dynamic_per_token_head`), max absolute error, finiteness, allocated/reserved/peak bytes, and the backend or PyTorch symbol actually called. The numerical oracle must consume the decoded tile output; fail on a nonfinite value, error above the registered `0.25` bound, missing scale identity, or dtype fallback.
5. Persist every KV row atomically after its kind completes. Evaluate the typed KV result, then invoke the existing owner's final completion/cleanup path. An OOM, ambiguity, or failed oracle is a typed KV negative, not a capacity or endpoint result.

## Why this repairs the observed failure

The failed script first allocated `[33712, 450560]` BF16: 28.292 GiB. Its second operation (`abs`) needed another 28.29 GiB while only 15.47 GiB was free. That peak is conversion workspace for all Gemma layers and is unrelated to the per-layer FP8 cache contract. The largest retained per-layer payload in the corrected c8 prompt geometry is the global layer at 132.716 MiB; a 128-token local tile adds at most 7.031 MiB of live BF16/FP8/recovered/scales tensors, and a global tile at most 3.504 MiB, before framework overhead.

This arm cannot establish endpoint throughput, allocator-fit, deterministic serving output, quality, or cost. Those require the later pinned vLLM consumer and existing campaign gates.
