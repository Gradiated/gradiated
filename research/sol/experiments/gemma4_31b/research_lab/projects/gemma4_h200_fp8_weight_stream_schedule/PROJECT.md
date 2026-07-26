# H200 FP8 weight-stream schedule

## 2026-07-26 warm-H200 exact-consumer reactivation

The graph-gap pair released
`h200-dflash-adapter-e00vyqp7gxsr34wrtz` warm and available. Resume the
existing `DIRECTOR_SM90A_BUILD_INCLUDE_REPAIR.json` contract as the sole H200
claimant. Repair only the already-localized redundant CUTLASS include, publish
one new content-addressed `sm_90a` module, run the one-call M32 correctness
discriminator, and proceed to the unchanged alternating M32/M384 consumer
only on a finite bitwise pass.

Claim by `2026-07-26T04:47:00Z`, stop and release by
`2026-07-26T05:12:00Z`, under the existing `05:20Z` watchdog. The cumulative
project cap remains `$2.00`, including the recorded `$0.40`. Do not run an
endpoint, tune a schedule, change geometry/scales/ABI, replay the consumed
`sm_90` module, or mutate provider lifecycle.

## 2026-07-25 pre-CUDA SM90a include repair

Consume `DIRECTOR_SM90A_BUILD_INCLUDE_REPAIR.json` and use
`$kernel-research`. The retained image accepted the required
`compute_90a/sm_90a` target, but compilation stopped before candidate CUDA
because the bound source included a CUTLASS callback header absent from the
retained include tree. Repair only that pinned include/build integration and
publish a new content-addressed source/module identity.

After the build passes, resume the unchanged one-call M32 discriminator. Only
a finite, bitwise-equal M32 result may proceed to the already-bound alternating
M32/M384 component. Do not change geometry, schedules, scales, ABI, output
type, workload, exactness gates, or run an endpoint. The older `sm_90` module
remains closed.

## 2026-07-25 corrected SM90a H200 reactivation

Consume `DIRECTOR_SM90A_H200_REACTIVATION.json` and use `$kernel-research`.
The consumed `sm_90` module remains closed. Build a new content-addressed
`compute_90a/sm_90a` module from the already-localized source and run exactly
one stock/candidate M32 gate-up correctness discriminator. If and only if that
output is finite and bitwise equal, use the same new module in the existing
alternating M32/M384 exact-consumer correctness and timing component.

This is the sole claimant for retained bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`. Reuse its pinned SGLang v0.5.13
image, exact checkpoint, runtime source, and caches. Do not replay the old
module, run an endpoint, tune the kernel, change precision or scales, change
workload geometry, or mutate provider lifecycle. Stop with
`FP8_WEIGHT_STREAM_SM90A_H200_TERMINAL.json` after the discriminator failure or
the conditional component result.


## 2026-07-25 M32 exactness-localization phase

The privileged retry consumed the M32 discriminator once. Candidate CUDA
execution began, but the immutable module produced a relative-L2 error of
`1.0`, final BF16 maximum absolute error `0.01092529296875`, and repeated
`sm90a` target diagnostics. This closes that static module, but it is evidence
of an implementation or exact-consumer failure rather than a physical timing
result for the weight-stream mechanism.

Consume `DIRECTOR_M32_EXACTNESS_LOCALIZATION.json` and use
`$kernel-research`. Work only from the immutable raw result, pinned runner,
module identity, and source. Locate the first build, dispatch, ABI,
scale/layout, output-commit, or accumulation boundary that explains the
failure. Return one content-addressed source discriminator or a typed
mechanism-level limit in
`FP8_WEIGHT_STREAM_M32_EXACTNESS_LOCALIZATION.json`.

This phase is zero-GPU. Do not replay M32, run M384, rebuild the consumed
module, claim the retained H200, or mutate provider lifecycle.

## 2026-07-25 exact-consumer H200 component phase

The source phase returned a buildable SM90 module that doubles only the
output-channel tile, preserves the production dynamic-FP8 ABI and K reduction
order, and cuts persistent-scheduler tiles by exactly 50% at both `M=32` and
`M=384`. Its conservative request mapping counts only the measured M384
projections, so the remaining question is physical rather than architectural.

Consume `DIRECTOR_EXACT_CONSUMER_H200_BINDING.json` and use
`$kernel-research`. Prepare without CUDA, then claim the retained H200 only
after the in-flight phase-selective owner and the higher-priority certified
lazy-head component have released or terminalized. Run one alternating paired
stock/candidate comparison through `exact_shape_runner.py` with the immutable
module. Require finite, bitwise-identical outputs at every bound consumer
boundary, graph-safe execution, and a strictly positive paired-bootstrap 95%
lower bound on saved full-MLP time at both row geometries.

Persist raw timing rows, checksums, graph behavior, and the typed terminal.
Do not tune tiles, rebuild the immutable module, run an endpoint, change
weights or quantization, or create provider resources. A positive component is
returned for director disposition; a non-positive or incorrect result closes
only this output-channel-wide schedule realization.

## Decision question

Can a source-level scheduling or dataflow change to Gemma 4 31B's dominant
dense-FP8 MLP path reduce exact c32 service time by streaming weights and
epilogues more efficiently on H200, without changing checkpoint values,
quantization semantics, row ownership, or model outputs?

This project is distinct from the already rejected static-FP8 producer ABI and
from the earlier isolated MLP proxy. It must identify and change the production
kernel/dataflow that actually owns the exact endpoint rows.

## Why it matters

The campaign's locked quality-qualified denominator is
`0.625149101968745 s/request` and its cumulative target is at most
`0.500119281574996 s/request`. The campaign names the dominant FP8 linear and
weight-stream path as a leading opportunity, and an earlier 16,384-wide MLP
proxy established a positive `2.6481%` conservative whole-request bound. That
prior is motivation only; this project must rebind the current exact model
geometry, production runtime, and c32 phases before transferring any timing.

## Bound inputs and scope

- Exact model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Target accelerator: NVIDIA H200 SXM.
- Production runtime: pinned SGLang v0.5.13 in
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Authoritative configuration:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`,
  SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Mechanically extracted text geometry: 60 layers, hidden width 5,376,
  intermediate width 21,504, 32 attention heads, and 16 KV heads.
- Phases to bind: exact c32 decode and depth-12 target verification. Treat
  `M=32` and `M=384` only as expected row geometries until production padding,
  batching, and ownership are proven from the pinned source and telemetry.
- The current retained H200 is exclusively claimed by
  `gemma4_hybrid_attention_placement_codesign`; this cycle must not claim it.

## Work contract

Use `$kernel-research`.

1. Reconstruct the production Gemma MLP producer/consumer chain, including
   gate, up, activation/product, down projection, quantization scales,
   accumulation/output dtypes, layouts, padding, tensor parallelism, graph
   capture, and all epilogues. Name and content-address the exact runtime
   symbols and libraries.
2. Bind the real c32 decode and target-verification shapes from current
   telemetry or an existing exact runner. Do not transfer the older
   16,384-wide proxy's shape or timing.
3. Explain the physical limiter on H200 using weight, activation, and scale
   bytes; arithmetic intensity; tensor-core tile realization; launch and
   synchronization structure; L2/shared-memory/register pressure; and the
   number of useful CTAs/warps. State one predicted counter or timing change.
4. Select the smallest production-compatible intervention: a current library
   kernel when it covers the semantics, otherwise a persistent/grouped,
   double-buffered, fused-epilogue, or related source implementation justified
   by the causal trace. A custom kernel is not an end in itself.
5. Produce buildable source plus a deterministic exact-shape correctness and
   timing runner. The runner must compare the exact consumer outputs and expose
   stock/candidate CUDA-event timing, but this cycle does not execute it on a
   GPU.
6. Derive a conservative whole-request bound from the scope-matched component
   share and state the minimum measured component result that would make one
   short retained-H200 falsification worthwhile. Do not impose an arbitrary
   percentage gate.

Label all evidence measured, analytical, derived, inferred, or synthetic. Do
not claim endpoint impact from the proxy or from CPU-only execution.

## Terminal and portfolio consequence

Write `FP8_WEIGHT_STREAM_SCHEDULE_RESULT.json` with one typed result:

- `source_complete_candidate`: exact producer/consumer and shape binding,
  buildable intervention and runner, predicted physical/counter change, and a
  positive conservative whole-request bound; or
- `mechanism_falsified`: evidence that the production path is not a material
  FP8 weight-stream limiter, the tested intervention is subsumed by a prior
  rejection, or its best physical bound is non-positive.

A positive terminal prepares, but does not authorize, a short exact-consumer
H200 component run after the current owner releases the bench. A negative
terminal closes only this scheduling/dataflow realization.

## Budgets and stop rules

- Wall clock: at most 120 minutes.
- Compute: CPU/source work only; no accelerator claim.
- Storage: at most 4 GiB of new durable artifacts.
- Spend: `$0.00`.
- Provider mutation: forbidden.

Stop after the typed terminal. Do not run an endpoint, claim a GPU, alter model
weights or quantization, relax exact output semantics, or reopen the rejected
static-FP8 producer ABI.
