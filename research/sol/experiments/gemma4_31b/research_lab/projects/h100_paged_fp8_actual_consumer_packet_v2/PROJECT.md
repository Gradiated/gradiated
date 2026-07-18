# H100 actual paged-FP8 consumer packet v2

## Decision question

Can the already-selected H100 paged FP8 KV mechanism be expressed as one immutable, source-bound program that actually constructs and invokes the pinned vLLM paged-attention consumer at Gemma 4 c8 geometry, with matched BF16/FP8 arms, output oracles, timing, and discriminating counters?

This is routine execution after the deep mechanism result. Do not repeat mechanism selection, query or mutate a provider, use a GPU, pull an image/checkpoint, compile, or poll any owner. Consume the prior mechanism and failed-program audit. Return a start-ready direct packet or typed none.

## Required correction

Repair every scientific defect enumerated in `h100_actual_paged_fp8_program_audit/AUDIT.json`:

- construct/register the real attention layer, forward context, KV cache, layer slot, block table, slot mapping, sequence metadata, scales, and selected backend;
- invoke the actual pinned paged backend for local `[8,16,256]` and global `[8,4,512]` Gemma geometry rather than merely importing or hashing it;
- implement matched nonzero BF16 and E4M3 KV arms, alternating paired timing, synchronized output consumption, and separate kernel-correctness and representation-loss oracles;
- specify fail-closed H100 counter capture for DRAM, L2, cycles, active warps, and launch count over the same named interval;
- define an atomic local/global c8 sentinel, then c8/c16/c32 sweep and architecture-weighted 358-step aggregation against `0.027398761575976767 s/request`;
- bind exact staged program/source/spec/runtime identities transitively and measure setup, scored CUDA, provider exposure, and cleanup separately.

The packet must name the exact first CUDA calls, commands, raw artifacts, immutable hashes, stop rule, and explicit provider budget for a later director decision. Do not implement a provider launcher. Do not add an adjacent arm; a later owner may only prepare one after measured setup dominance under the campaign rule.

## Budgets

- Wall clock: 25 minutes.
- Compute: 2 local CPU-hours; no GPU.
- Storage: 512 MiB retained plus 256 MiB temporary.
- Spend: `$0`; no provider/image/checkpoint/compiler mutation.

Write content-addressed `START_PACKET.json` or `TYPED_NONE.json`, concise log/status, and terminalize.
