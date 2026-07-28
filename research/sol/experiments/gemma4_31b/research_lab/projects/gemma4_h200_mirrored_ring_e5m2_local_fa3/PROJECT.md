# Mirrored E5M2 local ring consumed by one FA3 call on H200

## Question

Can a mirrored physical copy of the exact 1,024-token local E5M2 ring turn each circular logical window into one contiguous FA3 invocation, improving the quality-preserving ring endpoint after charging the doubled local producer writes?

## Evidence and causal change

The settled ring is quality-preserving and measured at `0.6556567115001144 s/request`, 3.1020% faster than its contemporaneous paged control but still above the `0.6381105231` ceiling. Its ownership, padding, fresh-extend producer, prefix state, first two decode transitions, 32/32 rows, and token accounting pass.

The first direct-E5M2 local FA3 implementation was a real production-shape CUDA result, not a dtype rejection. A circular window required two zero-copy FA3 calls and an output/logsumexp merge. It measured `0.3936319947 ms` versus the ring Triton consumer's `0.2680000067 ms`, a 46.8776% regression with a wholly negative confidence interval, and transition relative L2 reached `0.05278`. That exact decomposition is closed.

The candidate changes the storage geometry: write every local K/V token into both halves of a mirrored 1,024-token ring. Any logical window is then a single contiguous slice for one direct-E5M2 FA3 call. This removes one FA3 launch and the merge, while doubling local-ring storage and writes. The experiment must measure both sides of that exchange.

## Immutable `$kernel-research` scope

- Hardware/runtime: resident NVIDIA H200 SXM, pinned SGLang v0.5.13 image and existing checkpoint/caches.
- Phase and production shape: decode, batch 32, 1,024 context tokens, 32 BF16 query heads, 16 E5M2 KV heads, head dimension 256.
- Local path: exactly 50 local layers use a per-request mirrored contiguous ring and one direct-E5M2 FA3 v3-derived consumer call.
- Producer: the settled exact ring producer writes each local token to both mirror positions using the existing E5M2 scale convention. Measure its added stores.
- Global path: all ten head-dim-512 layers remain unchanged paged E5M2 Triton.
- Strongest baseline: the settled single-copy ring Triton component and its `0.6556567115001144 s/request` endpoint.
- Forbidden: two-call split/merge replay, full-cache BF16/E4M3 conversion, dtype/scale/tile/backend/layout sweeps, global-path changes, or a second candidate.

Physical prediction: eliminating one of two FA3 invocations and the output/logsumexp merge can reduce the prior `0.393632 ms` local consumer toward one-call territory, but only a component that includes doubled local writes can establish a positive bound. Record warm distributions, launches per consumer, HBM bytes or sectors, producer store traffic, registers/shared memory/spills, and numerical error sufficient to explain the result.

## Experiment and terminal

Prepare offline while the higher-priority stack owns the queue. After a durable `$14` reservation and bench release, claim `h200-sync-linear-e00vhh6h29fj68x91g`.

Run one actual-producer plus actual-consumer component against the settled ring Triton path. Cover the production shape, wrap boundary, negative padded rows, request-slot reuse, batch reorder, prefix restoration, fresh extend, and first two decode transitions. Require finite outputs and the existing ring's semantic tolerances. Consume every candidate output.

If and only if the complete producer-consumer measurement yields a credible positive whole-request bound, run exactly one profiler-off c32 endpoint against the persisted ring endpoint. No fixed percentage gate applies. Require 32/32 sane rows, exact `17120` cached plus `117728` fresh prompt-token accounting, 50-local/10-global route proof, mirrored-write proof, one-call proof, padding safety, and multi-token transition semantics. Retain any reproducible positive endpoint delta.

Close on inability to form one contiguous call, unacceptable numerical or transition error, non-positive full-bound result, invalid accounting, or endpoint regression. A pre-science integration failure is repaired in this same project without changing the intervention.

## Resources

- Researcher profile: `deep`.
- One retained H200; at most 90 claimed GPU-minutes and 180 wall minutes.
- Absolute deadline: `2026-07-23T20:15:00Z`.
- Authorization: `$14.00`.
- At most 12 GiB build/artifact storage; no checkpoint duplication.
- Researchers may claim and release the registered bench but may not mutate provider lifecycle.
