# H100 W4 Marlin exact-shape mechanism

## Decision question

Can actual H100 Marlin W4A16 weight-only linears at Gemma 4 31B's exact fused shapes plausibly improve whole-request economics by at least 5%, and is there one source-bound raw packing/consumer/oracle program ready for direct CUDA falsification?

This is a materially different `$0` deep mechanism project while the final FP8 owner cleans. It must not poll/edit/wait for that owner, query/mutate provider, invoke GPU/image/checkpoint/compilation, or claim W4 quality/performance. It must consume existing W4 producer/quality, synthetic Marlin bound, queue, price, and exact-shape evidence rather than repeat broad support research.

## Scope

Trace one concrete chain from exact Gemma linears and pinned Marlin source through:

- actual supported group size/zero-point/scales/packed-weight layout and raw installed producer/consumer symbols;
- SM90 tensor/INT4 realization, tile alignment for K/N=5376/8192/16384/21504 and N=5376/16384/20480/43008, occupancy or bandwidth limiter;
- deterministic varied-sign W/X construction with a correct dequantized-packed reference and separate representation-loss oracle;
- exact M8/M16/M32 and M3679 rows, matched BF16 comparator, architecture aggregation, and H100 `0.5479752315195353 s/request` boundary;
- smallest CUDA measurement that distinguishes packing/layout failure, launch/underfill, bandwidth, and compute limitation.

Consume `exact_w4_producer_quality_route`, `gemma_l40s_w4_c16_economic_bound`, `w4_background_batching_queue_bound`, `w4_48gb_hardware_price_screen`, the direct FP8 packet/terminal, and pinned source. Reject any path that needs a checkpoint or another offline readiness project before the first GPU call. Return either:

- `content_bound_h100_w4_direct_falsifier` with exact raw program/packing contract, sentinel and sweep, immutable inputs, oracles, budgets, stop rule, and no endpoint/quality claim; or
- typed none with the concrete unsupported packing/consumer reason.

Do not build a provider launcher or activate spend.

## Budgets

- Wall clock: 30 minutes.
- Compute: 3 local CPU-hours; no GPU.
- Storage: 768 MiB retained plus 384 MiB temporary.
- Spend: `$0`; no provider, image pull, checkpoint, compilation, or external mutation.

Write content-addressed `MECHANISM.json`, concise log/status, terminalize.
