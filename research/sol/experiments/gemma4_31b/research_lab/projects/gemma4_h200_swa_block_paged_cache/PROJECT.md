# Prefix-compatible block paging for local SWA on H200

## Question

Can Gemma 4's 50 local-attention layers preserve the exact 1,024-token SWA and radix-prefix contract while replacing page-size-one local KV addressing with one fixed 16-token physical page, improving locality without the request-owned circular state that failed multi-token decode?

## Why this matters

The closed request-owned ring was bit-identical to the control in its exact component and reduced the conservative local producer-consumer boundary by `24.834648%`, but it became incoherent on the first multi-token endpoint discriminator. That failure binds to circular request ownership and wrap-state integration, not to the measured locality benefit. Its own physical model showed index bytes were only `0.09765625%` of KV bytes, so the useful signal is coalesced physical locality rather than removing integer loads.

This project keeps canonical token order, radix-prefix ownership, reference counts, and logical token-to-KV semantics. It changes only the 50 local E5M2 pools from one-token physical pages to one fixed 16-token page and gives the actual Triton producer/consumer a block offset plus in-page token offset. All ten global layers remain on the existing page-size-one E5M2 path. The predicted physical movement is fewer discontinuous L2 sectors and address translations per 1,024-token local read, with no circular wrap state and no prefix copying.

## Immutable identity

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, pinned Linux/amd64 image digest `6113665a…`.
- Workload: c32, 32 requests, 4,214 prompt and 358 completion tokens each, exactly 17,120 cached and 117,728 fresh prompt tokens.
- Control: qualified E5M2 endpoint at `0.6743258590313417 s/request`.
- Local geometry: 50 layers, 32 query heads, 16 KV heads, head dimension 256, exact 1,024-token window, E5M2 KV.
- Global geometry: ten layers, 32 query heads, four KV heads, head dimension 512, unchanged page-size-one paged E5M2 Triton.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically bind these identities, the current profile, exact control, live SWA source binding, and the closed ring's measured component evidence.

## Immediate experiment

Use `$kernel-research`. Bind the live `SWAKVPool` allocation, radix-prefix reference/eviction path, `set_kv_buffer`, CUDA-graph metadata, and local Triton prefill/decode consumer. Implement exactly one 16-token physical page for local layers while preserving canonical logical token indices. Do not retain or repair any request-owned ring, wrap pointer, or prefix copy.

After the `$14` reservation is durable, claim `h200-sync-linear-e00vhh6h29fj68x91g` and reuse its read-only checkpoint, pinned image, and caches. First run one actual-producer/consumer component at c32 decode context 1,024 and the observed prefill boundary. Consume all outputs and cover shared-prefix aliasing/refcounts, eviction/reuse, partial first/last pages, negative padded slots, CUDA-graph padding, and contexts crossing 16-token boundaries. Require candidate/control equivalence under the production E5M2 contract and exact proof of 50 local block-paged versus ten untouched global paths.

Measure warm distributions and only the L2 sectors, address/global-load instructions, registers/spills, and grid waves needed to test the hypothesis. Promote immediately to one profiler-off exact c32 control/candidate pair if the conservative scope-matched bound is positive and material. Require 32/32 sane responses, exact cache accounting, and a multi-token semantic discriminator before candidate timing. A minimum post-positive trace may verify the predicted physical movement.

## Stop rules and resources

Close on any prefix/refcount/eviction semantic failure, numerical failure, partial-page or padded-graph failure, component regression, insufficient bound, invalid accounting, or endpoint regression. Do not change precision, window, heads, global layers, FA3, Triton tile parameters, batching, or page size after the 16-token choice. No repair or replay of the circular ring is allowed.

- Researcher profile: `deep`.
- One retained H200; at most 120 claimed GPU-minutes and 210 wall minutes from first claim.
- Project authorization: `$14.00`.
- At most 10 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
