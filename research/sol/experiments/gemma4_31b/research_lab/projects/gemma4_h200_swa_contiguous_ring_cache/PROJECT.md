# Exact E5M2 local-SWA contiguous ring cache on H200

## Question

Can Gemma 4's 50 fixed-window local-attention layers preserve exact 1,024-token semantics while replacing page-size-one radix lookup with a per-request contiguous circular KV layout, reducing the current local producer-consumer boundary enough to improve the qualified E5M2 endpoint?

## Why this matters

The E4M3 and FA3 branch is closed: mixed local E4M3 costs 4.1445% endpoint time, and numerically valid FA3 recovers only 24.0777% of that branch's local boundary. The qualified E5M2 profile instead attributes `3,050` local `_fwd_kernel` calls to 50 local layers over 61 forward batches inside a 15.312032% whole-request local-attention boundary. Its fixed 1,024-token window does not require unbounded radix addressing after a request's local state is materialized.

This project changes producer/consumer layout, not precision, window, heads, Triton tiles, or backend flags. The physical hypothesis is that a contiguous `[request, ring_slot, kv_head, head_dim]` E5M2 layout eliminates per-token page/slot gathers and converts the window read into aligned, wrap-aware spans. The predicted counter movement is lower index/global-load instruction count and fewer scattered L2 sectors, with at least a 35.1% conservative reduction of the exact local interval union needed to reach `0.6381105231 s/request` from the qualified `0.6743258590` frontier.

## Immutable identity

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, pinned Linux/amd64 image digest `6113665a…`.
- Workload: c32, 32 requests, 4,214 prompt and 358 completion tokens each, exactly 17,120 cached and 117,728 fresh prompt tokens.
- Control: persisted qualified E5M2 endpoint at `0.6743258590313417 s/request`; do not replay unless a contemporaneous pair is required by changed server state.
- Local geometry: 50 layers, 32 query heads, 16 KV heads, head dimension 256, exact 1,024-token window, E5M2 KV, page size one in the control.
- Global geometry: ten layers, 32 query heads, four KV heads, head dimension 512, unchanged paged E5M2 Triton path.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically bind the checkpoint/runtime/workload, qualified profile, exact control, and current SWA producer/metadata source evidence.

## Immediate experiment

Use `$kernel-research`. Prepare offline while the higher-priority FP8 producer project uses the bench. Trace the live `SWAKVPool`/`MHATokenToKVPool` producer, prefix-cache materialization, slot translation, CUDA-graph metadata, and local Triton prefill/decode consumer. Implement exactly one local E5M2 circular layout plus its wrap-aware consumer. Global layers, radix ownership, scales, cache capacity, request accounting, and all model/runtime settings remain unchanged. Cached prefixes must be copied or aliased with explicit ownership before local consumption; silently dropping prefix reuse fails.

After the `$14` reservation is durable and the higher-priority project releases `h200-sync-linear-e00vhh6h29fj68x91g`, claim it and reuse the read-only checkpoint, pinned image, and caches. The first GPU call is one actual-producer/consumer component pair at c32 decode context 1,024 plus the observed prefill boundary. Require complete output consumption, high-precision E5M2 reference error, wrap-boundary/negative-slot/padded-graph cases, exact 50-local/10-global path proof, and stable randomized timing. Collect only index/global-load/L2 sectors, registers/spills, and grid-wave evidence needed to test the layout hypothesis.

Promote immediately to one profiler-off exact c32 pair only if the component is numerically valid and its scope-matched conservative bound predicts a positive whole-request result; crossing the ceiling is the main goal. Require 32/32 sane responses and exact cache accounting, and preserve a minimum post-positive trace to verify that page/slot work disappeared.

## Stop rules and resources

Close on prefix/cache semantic failure, numerical failure, wrap/padding failure, component regression, insufficient bound, invalid accounting, or endpoint regression. Do not change KV precision, local window, head counts, global path, FA3, Triton tile parameters, batching, or add a second layout.

- Researcher profile: `deep`.
- One retained H200; at most 130 claimed GPU-minutes and 210 wall minutes from first claim.
- Project authorization: `$14.00`.
- At most 10 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
