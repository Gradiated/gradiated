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

## Director iteration 2 — rolling slot admission

`MI355X_BACKGROUND_BATCHING_SCREEN.json` is a preserved typed negative for
the barriered policy that waits for three complete c32 cohorts. Do not
overwrite, relabel, or replay it. Its c96 physical row remains useful:
`0.47035474275794686 s/request` and memory fit pass, while the policy fails
because waiting for 64 additional requests requires at least
`30.102703536508603` seconds at stable c96 capacity.

Test one materially different scheduling mechanism in this same project:
source-real rolling sequence admission. Admit an individual request whenever
a resident slot becomes free, continuously compact live sequence rows, and
execute each step at its actual active width up to 96. Do not hold requests
behind immutable c32 cohort boundaries.

1. Bind the current runtime's request admission, prefill/decode interleave,
   live-row compaction, per-request token/position/KV ownership, graph/eager
   shape selection, sampling, completion, and slot-reuse consumers. A
   steady-state queue formula without this path is invalid.
2. Use one deterministic policy with maximum 96 live sequences and one
   explicit prefill budget. Do not sweep widths, token budgets, arrival rates,
   timeout values, or graph modes.
3. Simulate a finite deterministic arrival stream long enough to include
   bootstrap, steady state, and drain. Offer no more than 90% of the
   conservative service capacity. Report bootstrap and drain separately but
   charge their work in the all-request economic mean; do not preload 96
   requests for free.
4. At every event, recompute physical cost from the actual active M and exact
   prompt/decode/target-verification geometry. Charge partially occupied
   weight streams, compute, KV and attention, BF16 head, non-GEMM bytes,
   launches, scheduler/service work, prefill interference, graph padding or
   eager dispatch, compaction, fallback, memory, and idle time. Do not
   interpolate ideal c96 throughput or divide its time by occupancy.
5. Preserve all requests, 4,572 tokens/request, cache mixture, 60 layers,
   widths, heads, parameters, KV rows, sampling, and feature semantics. Stack
   no speculative, compression, attention-state, prompt-state, head, or other
   survivor gain.
6. Emit `MI355X_ROLLING_BATCHING_SCREEN.json` as:
   - `source_complete_rolling_batching_candidate` only if the one current-
     runtime policy is source-complete, every cost is charged, the finite-
     horizon all-request mean is at most `0.500119281574996 s/request`,
     memory fits, queue p95 is at most 10 seconds, completion p95 is at most
     90 seconds, offered load is no more than 90% of conservative capacity,
     starvation is zero, and one finite target-MI355X discriminator can
     falsify the path; or
   - `typed_none` if any source, semantic, physical, capacity, load, latency,
     reliability, memory, or economic gate fails.

Iteration-2 limits are 3 wall hours, 12 CPU-hours, 2 GiB new storage, and
`$0`. Do not download or copy the checkpoint, claim hardware, contact a
provider, use paid APIs, create resources, or alter the preserved c32 MI355X
lifecycle.

## Director iteration 3 — phase-aligned microcohorts

`MI355X_ROLLING_BATCHING_SCREEN.json` is a preserved typed negative for
immediate individual admission. Do not overwrite or relabel it. It fixes
queueing but settles at mean live width `65.07434471225507`; more importantly,
150,000 request-relative target cycles dephase into 52,127 small forwards,
repeatedly charging transformer/head streams and launches.

Test one preselected phase-aligned microcohort policy in this same project:

- Form immutable FCFS microcohorts of exactly 16 requests. Six cohorts fill
  the 96-sequence capacity. Sixteen is fixed because it divides 96 and its
  conservative full-cohort arrival budget at iteration 2's 90%-capacity rate
  is below the 10-second queue gate. Do not test another cohort size.
- Admit a cohort only when all 16 requests are present, then keep its request
  membership phase-aligned through prefill, 358 output rows, all 15 required
  depth-12 target cycles, sampling, and completion. Admit later cohorts
  independently as slots free; do not wait for all 96 requests.
- Bind the current scheduler, token-budget, prefill/decode interleave,
  cohort-local position/KV ownership, compaction, graph/eager dispatch,
  target-verification consumer, sampling, and cohort release path. The
  implementation may add one model-specific scheduler adapter but may not
  change model or request semantics.
- Use one deterministic 8,192-token prefill budget and eager exact-row
  execution. Do not sweep token budget, cohort size, load, timeout, graph
  mode, or policy.
- Simulate a finite arrival stream with bootstrap, steady state, and drain at
  no more than 90% of this policy's conservative capacity. Charge every
  actual-width prompt, decode, and target event; FP8/BF16 weights, compute,
  KV/attention, tied head, non-GEMM bytes, launches, synchronization,
  microcohort fill/barrier, idle time, compaction, memory, fallback, bootstrap,
  drain, and scheduler/service cost. Preserve partially filled final cohorts
  with an explicitly charged exact fallback; do not discard them.
- Preserve every request and 4,572 tokens/request, the exact cache mixture,
  all layers, widths, heads, parameters, KV rows, sampling, and features.
  Stack no speculative, compression, prompt-state, attention-state, head, or
  other survivor gain.

Emit `MI355X_MICROCOHORT_BATCHING_SCREEN.json` as:

- `source_complete_microcohort_batching_candidate` only if the single
  16-request policy is source-complete, the finite-horizon all-request mean is
  at most `0.500119281574996 s/request`, offered load is no more than 90% of
  conservative capacity, queue p95 is at most 10 seconds, completion p95 is
  at most 90 seconds, memory fits, starvation is zero, all costs are charged,
  and one finite target-MI355X discriminator can falsify it; or
- `typed_none` if any source, semantic, physical, capacity, latency, load,
  reliability, fallback, memory, or economic gate fails.

Iteration-3 limits are 3 wall hours, 12 CPU-hours, 2 GiB new storage, and
`$0`. Do not download or copy the checkpoint, claim hardware, contact a
provider, use paid APIs, create resources, or alter the preserved c32 MI355X
lifecycle.
