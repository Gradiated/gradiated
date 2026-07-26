# MI355X background-batching co-design

## Question

Can a source-real continuous-batching schedule combine independent c32
background-agent cohorts into exact c64 or c96 Gemma 4 execution, amortizing
FP8 transformer weights, the BF16 tied head, and launch overhead enough to
reach the locked `$0.109725/M total tokens` target while keeping completion
time usable and preserving every request, token, layer, parameter, and output
semantic?

## Why this matters

The preserved MI355X FP8 screen derives `0.6000950932112802 s/request`.
Ordinary c32 decode alone charges `0.1370320896 s/request` for one 29.397-GB
FP8 transformer-weight stream per step, `0.01313865728 s/request` for the BF16
tied head, and `0.039301875 s/request` for launches. Several exact M32
transformer shapes expose only `0.1640625` to `1.3125` nominal waves across
256 CUs. Background-agent latency is explicitly secondary in `CAMPAIGN.md`,
so wider resident batches may improve sustainable cost without changing the
model.

The completed lossless-weight project is a typed negative: its sole
preregistered code expands the exact runtime FP8 stream to
`1.0676357239351908x`. Do not reopen compression. TPU, Trainium2, Gaudi3,
MXFP6, DFlash depth control, and prior head mechanisms are also not evidence
for or against this MI355X scheduling question.

## Bound evidence

- Campaign model and workload: `CAMPAIGN.md`, including the exact checkpoint,
  4,214-token prompt, 358-token output, 12.7% cache-hit mixture, and the locked
  `0.500119281574996 s/request` equivalent target at the `$2.60/hour` planning
  rate.
- MI355X geometry, current vLLM/ROCm consumers, per-family cost rows, and the
  c32 comparator:
  `../gemma4_mi355x_fp8_runtime_codesign/MI355X_FP8_RUNTIME_SCREEN.json`.
- Current source bindings:
  `../gemma4_mi355x_fp8_runtime_codesign/SOURCE_BINDINGS.json`.
- Preserve the funded c32 exact-shape falsifier in the survivor frontier; this
  project neither amends nor stacks with it.

## Scope and method

1. Bind the actual current scheduler, model-runner, graph/eager, attention,
   FP8-linear, and tied-head producer/consumer path needed to form c64 and c96
   from independent c32 cohorts. A tensor-shape substitution or an ideal
   batching spreadsheet is not a source-complete schedule.
2. Preserve every request and all 4,572 tokens/request. Preserve all 60
   layers, full hidden/intermediate widths, all attention heads and KV state,
   all checkpoint parameters, the BF16 tied embedding/head, sampling, cache
   mixture, and feature semantics. Do not use speculation, prompt compaction,
   recurrent attention, global-KV summaries, head approximation, compression,
   or any other survivor gain.
3. Recompute the exact c64 and c96 phase geometry from the bound c32 screen.
   Charge prompt work, ordinary decode, target-verification work, FP8 and BF16
   weight traffic, activations, KV reads/writes, attention pairs, padding and
   sequence-length divergence, graph/eager boundaries, launches,
   synchronization, scheduler/service overhead, and memory capacity. Do not
   transfer H100 batching throughput or grant better than the screen's settled
   20% tensor and 30% HBM efficiencies merely because M is larger.
4. Model cohort formation and draining under a finite offered load. Report
   the minimum requests/second needed to sustain the selected width, batch
   fill and queue delay, request completion p50/p95, starvation behavior, and
   the cost of falling back to smaller batches. The planning usability gate is
   queue-delay p95 at most 10 seconds and completion p95 at most 90 seconds;
   label this as a background-agent planning gate, not a production SLO.
5. Select at most one width and one deterministic admission/drain policy. It
   must be implementable in the current runtime path and must expose a finite
   target-MI355X exact-shape discriminator. Do not turn this into a flag,
   width, or arrival-rate sweep.
6. Emit `MI355X_BACKGROUND_BATCHING_SCREEN.json` with one classification:
   - `source_complete_background_batching_candidate`: the selected schedule
     is source-complete, all costs and fallback are charged, the conservative
     bound is at most `0.500119281574996 s/request`, memory fits, both planning
     latency gates pass at a finite stated offered load, and one bounded
     target-MI355X measurement can falsify it; or
   - `typed_none`: any source, semantic, capacity, offered-load, latency,
     physical, fallback, or economic gate fails.

## Invalid results

- Vendor peak division without the exact c64/c96 call and byte geometry.
- Dividing c32 time by batch width, assuming perfect wave utilization, or
  ignoring the compute roofline.
- Omitting queue/fill delay, padding, KV/attention growth, memory residency,
  fallback frequency, or partially filled drain batches.
- Treating a changed workload, dropped request/token, approximate head,
  reduced model capacity, or stacked survivor as background batching.
- Claiming target performance or production eligibility without target
  measurement and later quality, reliability, and feature validation.

## Resources and limits

- Wall clock: 3 hours.
- Compute: 12 CPU-hours.
- New storage: 2 GiB.
- Provider spend: `$0`.
- Use existing repository source, bound artifacts, and local simulation only.
- Do not download or copy the checkpoint, claim hardware, contact a provider,
  use paid APIs, create resources, or alter the preserved MI355X lifecycle.

## Portfolio-changing result

A passing candidate becomes a separate scheduling-aware target-MI355X
falsifier to compare with the preserved c32 frontier when funding exists. A
typed negative closes only c64/c96 cohort batching under this exact runtime,
workload, and planning-latency contract.
