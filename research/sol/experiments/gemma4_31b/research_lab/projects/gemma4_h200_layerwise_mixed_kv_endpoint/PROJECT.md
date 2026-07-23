# Layerwise mixed-format KV endpoint on H200

## Question

Can the exact retained SGLang v0.5.13 stack store only Gemma 4's 50 local-attention layers as FP8-E4M3 while preserving FP8-E5M2 for all ten global-attention layers, without the 4.146% regression measured when every layer used E4M3?

## Why this matters

The whole-cache E4M3 arm is a valid negative at `0.7022842786 s/request` versus the persisted `0.6743258590 s/request` E5M2 control. That result closes uniform E4M3, but it does not identify whether the penalty comes from the 50 local head-dim-256 consumers, the ten global head-dim-512 consumers, or their shared pool path. The completed source binding for the local-FA3 lane shows that both layer classes already pass through `SWAKVPool` into the shared paged pool and that the runtime can route attention by layer.

This project tests a materially different representation: two layer-indexed paged KV pools, E4M3 only where Hopper FA3 can later consume it and unchanged E5M2 everywhere else. The result is a direct endpoint measurement and the comparator for the independent local-FA3 lane. It is not a precision spelling or backend sweep.

## Immutable identity

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Checkpoint index SHA-256: `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, Linux/amd64 image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Workload: 32 requests at concurrency 32, each 4,214 prompt and 358 completion tokens; exact totals are 17,120 cached and 117,728 fresh prompt tokens.
- Control: persisted exact E5M2 terminal at `0.6743258590313417 s/request`; do not replay it.
- Negative evidence: uniform E4M3 Triton at `0.7022842785938792 s/request`; do not replay it.
- Geometry: local layers are the 50 nonmultiples of six, with 32 query heads, 16 KV heads, head dimension 256, and a 1,024-token window. Global layers are `[5,11,17,23,29,35,41,47,53,59]`, with 32 query heads, four KV heads, and head dimension 512.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically bind the authoritative stack, control, uniform-E4M3 negative, and completed producer/consumer source binding.

## Immediate experiment

Use `$kernel-research`. First bind the live pinned source for `SWAKVPool`, `MHATokenToKVPool`, the layer-to-pool selection, scale storage, graph capture, and Triton prefill/decode consumers. Implement exactly one layer-indexed mixed-format path: E4M3 local KV and E5M2 global KV, both page size one, both consumed by unchanged Triton attention. Preserve weights, QKV epilogue, local window, cache capacity, scheduler, chunking, graph geometry, and every other stack field.

After the `$12` reservation is durable, claim `h200-sync-linear-e00vhh6h29fj68x91g`. Reuse the manifest-verified read-only checkpoint, pinned image, and caches. Stop the retained uniform-E4M3 server only after the claim. Do not copy the checkpoint or mutate provider lifecycle.

Run one correctness-bearing exact-consumer component/path check proving all 50 local layers produce and consume E4M3, all ten global layers produce and consume E5M2, scales and slots are layer-correct, and no fallback or cross-pool alias occurs. If that passes, run exactly one profiler-off exact c32 mixed-format candidate against the persisted control. Require 32/32 complete finite nonempty responses, exact request identities and usage, exact 17,120/117,728 cached/fresh accounting, and retained per-layer producer/consumer audit.

## Decision

- `retain_mixed`: a valid candidate that improves the control or leaves a measured penalty small enough that the already-bound local FA3 component can conservatively recover it and beat `0.6743258590 s/request`.
- `close_mixed`: unsupported mixed pools, numerical/coherence failure, missing path proof, invalid accounting, or a penalty larger than perfect removal of the measured 15.312032% local-attention boundary can recover.

Do not run FA3, replay either historical endpoint, alter scale conventions, change cache capacity, sweep formats or flags, or add a second mixed candidate.

## Resources

- Researcher profile: `deep`.
- One retained H200; at most 100 claimed GPU-minutes and 150 wall minutes from first claim.
- Project authorization: `$12.00`.
- At most 8 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
