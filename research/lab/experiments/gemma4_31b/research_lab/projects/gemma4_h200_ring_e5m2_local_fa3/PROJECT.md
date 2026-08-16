# Contiguous E5M2 ring consumed by local FA3 on H200

## Question

Can a single FA3-compatible E5M2 load/dequant specialization consume the now-correct contiguous local ring and improve the quality-preserving ring frontier while all ten global layers remain on stock paged E5M2 Triton?

## Evidence and importance

The exact E5M2 ring is byte-correct across fresh extend, ownership, padding, prefix state, and the first two decode transitions. Its c32 endpoint is `0.6556567115001144 s/request`, 3.1020% faster than its contemporaneous control but still 2.75% above the `0.6381105231` ceiling.

The earlier actual-paged E4M3 FA3 component reduced the local consumer by 26.5422% and the producer-consumer boundary by 24.0777%, with relative L2 `0.0041030` and cosine `0.99999446`. Direct paged E5M2 then reached CUDA and failed only because the stock FA3 v3 operator accepts FP16, BF16, and E4M3—not E5M2. The contiguous ring removes paged addressing from the local path and creates a materially different implementation surface for an in-kernel E5M2 decode.

## Immutable kernel scope

Use `$kernel-research`.

- Phase: local-attention decode, with extend/prefill semantics preserved by the settled ring producer.
- Production geometry: batch 32, 1,024-token local window, 32 BF16 query heads, 16 KV heads, head dimension 256, 50 local layers.
- Input layout: contiguous per-request circular K/V ring, E5M2 bytes, exact existing scale convention, negative padded rows as no-ops.
- Candidate consumer: one FA3-v3-derived local consumer with E5M2 load/dequant into the supported compute path. Do not materialize a BF16 or E4M3 copy of the full cache.
- Baseline consumer: the settled contiguous-ring Triton consumer and its `0.6556567115001144 s/request` endpoint.
- Global path: ten head-dim-512 layers remain unchanged paged E5M2 Triton.
- Predicted physical change: preserve the ring's contiguous loads while replacing the local Triton online-attention consumer with the measured faster FA3 decomposition; expect lower local consumer latency without changing HBM-resident KV bytes.

## Immediate experiment

Prepare offline behind the higher-priority width-plus-ring interaction. After the `$14` reservation is durable and that project releases `h200-sync-linear-e00vhh6h29fj68x91g`, claim the same bench and reuse its checkpoint, image, ring patch, and caches.

Inspect the pinned FA3 v3 dtype dispatch and implement one E5M2 load/dequant specialization or minimal adapter inside the actual consumer. The prior stock dtype rejection is not a terminal here; implementing that missing specialization is the admitted intervention. There is no dtype, tile, backend, or scale sweep.

Run one actual-producer/actual-consumer component using the exact ring layout. Consume all outputs and compare against the settled ring-Triton path, covering the production shape, wrap boundary, padded row, and first two decode transitions. Report full numerical error, warm timing distribution, compiled registers/shared memory/spills, and only counters needed to explain the result.

If the scope-matched whole-request bound is credibly positive and integration is ready, run exactly one profiler-off c32 candidate against the persisted ring endpoint. No fixed percentage gate applies. Require 32/32 sane rows, exact token/cache accounting, 50-local/10-global route proof, CUDA-graph padding safety, and multi-token semantics. Retain any reproducible positive endpoint gain.

Close on inability to implement direct E5M2 consumption within one specialization, non-finite or unacceptable numerical behavior, ring/state regression, non-positive component bound, invalid accounting, or endpoint regression.

## Resources

- Researcher profile: `deep`.
- One retained H200; at most 90 claimed GPU-minutes and 150 wall minutes.
- Absolute deadline: `2026-07-23T20:15:00Z`.
- Authorization: `$14.00`.
- At most 12 GiB build/artifact storage; no checkpoint duplication.
- Researchers may claim and release the registered bench but may not mutate provider lifecycle.
