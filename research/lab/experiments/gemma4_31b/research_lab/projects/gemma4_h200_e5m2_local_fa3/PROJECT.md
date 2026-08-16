# Direct E5M2 local FA3 on H200

## Question

Can the already-measured Hopper FA3 local-attention consumer read the qualified E5M2 paged KV representation directly, avoiding the 4.14% E4M3 endpoint penalty while preserving all 50 local-layer and ten global-layer semantics?

## Why this matters

The prior actual-paged component established a strong but stranded signal: on the exact local geometry, FA3 v3 reduced consumer time by `26.5422%` and the conservative producer-consumer boundary by `24.0777%`, with relative L2 `0.004103` and cosine `0.99999446`. Its endpoint was correctly withheld because changing local KV to E4M3 made the comparator `4.1445%` slower. This project removes that representation change instead of tuning the closed E4M3 hybrid.

The physical hypothesis is that Hopper FA3's local decode path remains beneficial when its load/dequant template consumes the qualified page-one E5M2 pool. Storage, production, radix ownership, 1,024-token window, page size, scale convention, heads, and global Triton path remain unchanged. Applying the measured conservative local reduction to the measured local boundary predicts about `3.6868%` whole-request savings, or roughly `0.6495 s/request`. This would be an incremental qualified gain, not by itself a claim to cross the `0.6381105231` ceiling.

## Immutable identity

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, pinned Linux/amd64 image digest `6113665a…`.
- Workload: exact c32, 32 requests, 4,214 prompt and 358 completion tokens each, exactly 17,120 cached and 117,728 fresh prompt tokens.
- Control: qualified E5M2 endpoint at `0.6743258590313417 s/request`.
- Local path: 50 layers, 32 query heads, 16 KV heads, head dimension 256, page size one, exact 1,024-token window, E5M2 KV.
- Global path: ten layers, 32 query heads, four KV heads, head dimension 512, unchanged E5M2 Triton.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically bind the current stack, exact control, source router, and prior actual-paged FA3 component.

## Immediate experiment

Use `$kernel-research`. Inspect the pinned FA3 v3 interface and exact E5M2 producer/scale contract, then freeze one direct E5M2 load/dequant adapter or dtype specialization for the local FA3 consumer. This is not a backend, tile, dtype, or scale sweep.

After the `$14` reservation is durable, claim `h200-sync-linear-e00vhh6h29fj68x91g`. Run one actual-producer/consumer component at batch 32, context/window 1,024, page size one, query BF16, and E5M2 KV. Consume all outputs and require exact proof that 50 local layers use FA3 while ten global layers retain stock E5M2 Triton. Compare against the production-equivalent E5M2 Triton component, including scale handling, negative padded slots, CUDA-graph padding, and multi-token state.

Promote to exactly one profiler-off c32 candidate against the persisted qualified control only if the component is numerically within the existing E5M2 serving tolerance, graph-safe, and has a conservative scope-matched whole-request bound of at least 3%. Require 32/32 sane responses, exact cache accounting, path audit, and a multi-token semantic discriminator before timing. A minimum trace after a positive endpoint may confirm the consumer change.

## Stop rules and resources

Close on unsupported direct E5M2 FA3 consumption, any conversion back to E4M3, numerical or scale failure, padding/state failure, missing 50/10 routing proof, a bound below 3%, invalid accounting, or endpoint regression. Do not tune FA3, change global attention, change page/window/head geometry, add an intermediate full-cache conversion, or run a second candidate.

- Researcher profile: `deep`.
- One retained H200; at most 100 claimed GPU-minutes and 180 wall minutes from first claim.
- Project authorization: `$14.00`.
- At most 8 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
