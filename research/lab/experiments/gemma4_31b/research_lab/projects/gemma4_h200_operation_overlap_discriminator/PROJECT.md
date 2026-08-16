# Gemma 4 H200 operation-overlap discriminator

## Question

Can resource-complementary Gemma 4 attention/KV and FP8-linear work from
different c32 nano-batches execute concurrently on H200 fast enough to justify
a narrow NanoFlow-style model-execution data plane?

## Evidence and physical hypothesis

Use `$kernel-research` and `$experiment-run`.

The exact v0.5.13 FP8+QKV profile assigns non-overlapping request wall time as:

- synchronization: 36.5787%;
- attention/KV: 28.2473%;
- FP8 linears: 22.9730%;
- scheduler gaps: 4.9963%;
- measured cross-family GPU overlap: only `0.001258721 s`.

The authoritative attribution is
`../gemma4_h200_v0513_fp8_qkv_residual_profile/artifacts/residual-profile-20260720t0821z/ATTRIBUTION.json`.
The hypothesis is not that the GPU is idle. It is that memory-intensive
attention/KV and tensor-core-heavy FP8 work are serialized even when a c32
nano-batch split could overlap complementary resources. The competing
explanation is destructive interference: both operations consume enough SM,
register, L2 or HBM resources that concurrency cannot lower the critical path.

## Bound scope

- Exact checkpoint and pinned v0.5.13 dynamic-FP8/QKV/ring stack.
- Exact H200 SXM and c32 workload.
- Use the existing retained bench
  `h200-sync-linear-e00vhh6h29fj68x91g` only after
  `gemma4_h200_ngram_production_validation` releases it. Prepare offline behind
  that explicit queue boundary.
- Extract the dominant exact attention/KV and FP8-linear producer, consumer,
  shapes, layouts, dtypes/scales, and source identities mechanically from the
  profile and existing component artifacts. Do not substitute convenient
  synthetic shapes or sum overlapping kernel durations.
- First candidate: split c32 into two fixed nano-batches and schedule one
  attention/KV region concurrently with one independent FP8-linear region on
  separate streams using stable buffers. Preserve outputs exactly.
- No broad tile sweep, generic runtime rewrite, new checkpoint transfer,
  provider creation, or quality suite.

## Immediate experiment

1. Build one exact-consumer component that executes the two selected regions
   serially and concurrently. Consume every output and require the existing
   numerical contract.
2. Warm/compile first, then run enough profiler-off repetitions to report serial
   sum, concurrent elapsed time, variance, and overlap efficiency.
3. Collect only counters needed to explain the result: tensor-pipe activity,
   DRAM/L2 traffic, registers/shared memory/occupancy, and dominant stalls for
   each region and their concurrent interval.
4. If concurrent elapsed time is at most 80% of the serial critical path with
   exact outputs, immediately prototype one layer-group/nano-batch scheduling
   slice in the pinned runtime and derive a conservative endpoint bound.
5. Run one c32 endpoint only when that integrated slice is narrow, correct, and
   its measured bound is positive. Retain any valid endpoint improvement.
6. If concurrency is at least 90% of serial time or counters prove destructive
   interference, close this operation pair and state whether a materially
   different resource pair remains; do not tune streams ceremonially.

The 80% component level is the hurdle for paying the implementation cost of a
new data plane, not a campaign rule for retaining endpoint gains.

## Contract

- Causal hypothesis: c32 has independent nano-batch work whose different
  physical resource signatures can overlap inside one H200.
- Quality gate: exact component outputs; any endpoint must retain 32/32 rows and
  exact prompt/cache accounting.
- Maximum spend: `$12`.
- Compute: retained H200, at most four claimed GPU-hours.
- Deadline: `2026-07-24T09:30:00Z`.
- Storage: at most 8 GiB.
- Artifacts: exact source/shape binding, serial/concurrent samples, numerical
  evidence, decisive counters, endpoint bound/result if admitted, spend, and
  resident-state handoff.
- Provider lifecycle: no provider mutation; release the retained bench without
  teardown.
