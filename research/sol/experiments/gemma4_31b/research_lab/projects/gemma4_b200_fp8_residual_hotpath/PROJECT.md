# B200 runtime-FP8 residual hot path

## Question

What exact runtime, kernel, or scheduler boundary explains the residual
`0.633995593312477 s/request` B200 runtime-FP8 c32 endpoint, and what one
source-level change has the shortest credible path toward the fixed
`0.500119281574996 s/request` target?

## Why this matters

The authoritative absolute candidate terminal
`../gemma4_b200_dynamic_fp8_endpoint/artifacts/b200-dynamic-fp8-repair2-20260728t1517z/final-retrieval/handoff/DYNAMIC_FP8_TERMINAL.json`
(SHA-256
`4930d9666167e20096f0343736db6d0ed721ea30fad68f5fc4010ccfeeee9acf`)
proves real dynamic-FP8 consumption and 32/32 completed requests at
`0.633995593312477 s/request`. It remains 1.4% slower than the qualified H200
denominator and 26.8% above the campaign target. The aggregate
`FINAL_TERMINAL.json` BF16 and paired-delta fields are invalid because
duplicate endpoint execution could not be excluded and the BF16 terminal was
overwritten; do not use them for causal accounting. The next B200
intervention should follow the absolute FP8 residual critical path rather
than repeat representation work or guess flags.

## Scope

- Read only the hash-bound absolute FP8 terminal above, retained local server
  evidence, and the pinned vLLM runtime source needed to trace the active
  Gemma 4 FP8 consumer. Treat all BF16 and paired-reduction fields from the
  aggregate terminal as inadmissible.
- Reconstruct a non-overlapping analytical time/bytes model across prefill,
  decode, FP8 linears, hybrid local/global attention and KV traffic,
  normalization/activation, launch, and scheduler gaps. Label measured,
  derived, and inferred quantities separately.
- Trace the active source path through
  `CutlassFP8ScaledMMLinearKernel` and the exact Gemma 4 hybrid-attention
  consumer. Map production tensor shapes and c32 geometry onto B200 tensor
  core, memory, occupancy, and launch constraints.
- Select one source-level intervention whose predicted whole-request effect
  is large enough to be decision-relevant. Implement and hash-bind the
  smallest patch or exact-shape falsifier when feasible; otherwise write a
  typed rejection with the missing measurement that would decide it.
- Do not claim a GPU, operate the provider, submit endpoint requests, create a
  readiness project, or perform a generic literature/flag survey.

## Required artifact

Produce `B200_FP8_RESIDUAL_DISCRIMINATOR.json` containing:

1. authoritative identities and evidence hashes;
2. the causal chain from endpoint observation to physical limiter and exact
   source symbols;
3. the non-overlapping time/bytes accounting with uncertainty;
4. one concrete implementation or exact-shape runner and its hashes;
5. predicted counter and endpoint effects;
6. the smallest future GPU measurement and explicit stop condition.

Use `$kernel-research` for kernel-level source, shape, and B200 mapping.

## Resources and bounds

- Researcher profile: deep
- GPU/provider access: forbidden
- Spend: `$0`
- Wall-clock budget: 90 minutes
- Additional storage: 4 GiB

## Portfolio-changing result

A hash-bound intervention with a credible whole-request bound becomes the next
direct B200 experiment after the c64 saturation result. A typed rejection
redirects the warm bench to a different runtime or hardware mechanism rather
than another B200 launcher iteration.

## 2026-07-28 execution continuation

The valid c64 result is now durable. Prepare the discriminator's smallest
future GPU measurement as one stock-versus-patched exact-shape component
packet over the six bound M32 shapes. Hash-bind
`b200_m32_dispatch_component.py`, `b200_m32_dispatch_owner.sh`, and
`PRECLAIM_TERMINAL.json`; preserve the discriminator's numerical oracle,
production multiplicities, timing method, stop conditions, and conditional
c32 endpoint promotion rule.

This preparation is bench-free. The c96 saturation continuation is the sole
current B200 claimant. Do not claim or mutate that bench until this project's
reservation is durable, c96 has terminalized or safely released, and a fresh
director envelope marks the bench ready.

## 2026-07-28 M32 mechanism reopening

The measured M16 SwapAB dispatcher is closed after a correct paired component
regressed the weighted six-shape hot path by 3.5324%. The later 18-row
block-E4M3 table is only mixed-producer implementation evidence: installed
QuantFP8 produced activations, but its weights came from a hand-authored
adapter without the required production-producer equivalence ledger. It does
not close official block E4M3 and does not alter this project's qualified
dynamic-FP8 representation. Change only the SM100 M32 execution schedule.

Use `$kernel-research` to derive one materially distinct M32 dispatcher,
grouped schedule, or persistent consumer from the pinned vLLM CUTLASS source,
the exact six-family Gemma geometry, and identical quantized operands. Produce
`B200_FP8_M32_NEXT_MECHANISM.json` with the causal limiter, source and runner
hashes, exact stock/candidate oracle, predicted counter and request effect,
bounded owner/lifecycle contract, and a stop rule. This phase is bench-free.
Do not rebuild or replay M16 SwapAB, claim a GPU, or mutate provider lifecycle.
Paid execution requires a later director turn after the total `$16`
reservation is durable and an exact B200 has been provisioned or revalidated.

## 2026-07-29 endpoint promotion

The geometric runtime-`sm_count` rebind produced six complete, bitwise-equal
M32 family rows on B200. Weighted quantization-plus-GEMM time fell from
`11.7523196712 ms` to `10.5420797877 ms` per decode step, a `10.2979%`
reduction. With the bound c32 multiplicities and 358-token decode geometry,
the component projects `0.0135395587 s/request` saved, approximately `2.17%`
of the fixed qualified `0.625149101968745 s/request` denominator.

Promote the same mechanism to one scope-matched B200 dynamic-FP8 endpoint
comparison. Integrate source SHA-256
`1d1f5aba004d9e33e14a0c548eca2ea8c0e5f326fc60b1dac2334e482b30e425`
at the pinned vLLM `cutlass_scaled_mm` consumer without changing checkpoint,
workload, dynamic-FP8 producer semantics, KV representation, request
accounting, or c32 scheduling. Measure a contemporaneous stock/candidate
endpoint pair and require valid 32/32 requests, matching token/cache
accounting, finite coherent output, and a positive service-time delta.

This continuation requests a `$28` cumulative project ceiling and may not
claim or extend a provider lifecycle until that exact durable reservation is
visible. The current B200 remains maintenance-only under its existing
watchdog; a later director chooses retained-bench extension versus fresh B200
placement after reconciling the reservation and lifecycle.
