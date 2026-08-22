# Streaming global-KV memory schedule

## Question

Can the activated Gemma 4 global-KV intervention be reformulated so its
temporary state is layer-local or chunk-streamed, preserving exact attention
semantics while making c32 memory-feasible and retaining the component-level
compute benefit?

## Why it matters

The campaign needs `0.500119281574996 s/request` or an equivalent
price-normalized 20% cost reduction against the fixed qualified
`0.625149101968745 s/request` denominator. The prior global-KV implementation
proved real activation on c1 with 6,086 telemetry rows, 26 compact entries,
and no fallback. Its c32 endpoint then persisted all 32 responses but OOMed at
global layer 35 on a 2 MiB allocation. That closes the exact materializing
implementation, not a memory-frugal schedule for the mechanism.

## Scope

- Start from the exact pinned Gemma revision and the production global
  `q32/kv4/d512` consumer.
- Trace the activated implementation's allocations and lifetimes from compact
  KV construction through attention consumption.
- Form one concrete layer-local, tiled, recomputed, or streamed schedule that
  removes the c32 peak allocation without deleting layers, heads, width,
  tokens, or model capacity.
- Build the smallest source-backed memory model or CPU simulation that accounts
  for every retained tensor and predicts peak bytes at c1 and c32.
- If the model supports a credible fit with a short endpoint path, implement
  the exact source change and emit a target-hardware experiment request. Do
  not claim a GPU or create provider resources in this cycle.

## Bound evidence

- Scientific terminal:
  `../gemma4_multiresolution_global_kv_codesign/artifacts/h200-global-kv-20260728t1210z/ENDPOINT_REPAIR4_TERMINAL_ADOPTION.json`
- Activated implementation:
  `../gemma4_multiresolution_global_kv_codesign/multiresolution_global_kv.py`
- Exact model revision:
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`
- Required endpoint workload: campaign c32 with the preserved qualified
  denominator and economic target above.

## Decision artifact

Write `MEMORY_SCHEDULE_DISCRIMINATOR.json` with:

- the causal allocation/lifetime chain for the layer-35 OOM;
- measured, source-backed, and inferred claims labeled separately;
- current and proposed peak-byte equations at c1 and c32;
- the exact source boundary and semantic invariant of the proposed schedule;
- either a hash-bound implementation plus bounded GPU request, or a typed
  rejection showing why memory feasibility cannot be recovered competitively.

## Budgets

- Wall clock: 120 minutes.
- Compute: up to 2 controller CPU-hours; zero GPU in this cycle.
- Storage: 2 GiB.
- Spend: `$0`.

This is a deep mechanism project. It must produce a causal model and a concrete
discriminator, not another readiness, observer, or general design report.

## 2026-07-29 H200 execution continuation

The zero-GPU cycle completed with corrected discriminator `1ea35e00…`, final
U=8 candidate `636cc6e6…`, and three passing CPU oracles. Director binding
`DIRECTOR_STREAMING_GLOBAL_KV_H200_RESERVATION_AND_OWNER_PREPARATION_20260729T1027Z.json`
authorizes a `$4.00` project ceiling and one execution-profile owner
preparation turn. This does not authorize provider creation or a claim until
the reservation and owner-ready terminal are durable.

The future paid phase preserves the question and all scientific identities:
one H200, at most 45 scientific GPU minutes inside a 90-minute lifecycle,
first-call correctness, C=64 memory boundaries, profiler-off component
comparison, then a new streamed-candidate c32 endpoint only if those gates
pass. The consumed materializing c32 arm remains non-replayable.

## 2026-07-29 fresh endpoint continuation

The corrected H200 CUDA producer
`CUDA_DISCRIMINATOR_R2_attempt0.json` (`0f7c32bb…`) passed its exact
`26/64/64` correctness and memory gates. The conditional candidate endpoint
submitted zero requests before the old lifecycle expired, so the endpoint
question remains open while the old instance, disk, claim, and watchdog are
retired.

Binding
`DIRECTOR_STREAMING_GLOBAL_KV_FRESH_H200_ENDPOINT_PREPARATION_20260729T1233Z.json`
reopens this same scientific project for one zero-GPU execution-profile owner
update. Prepare a cold-start, resumable, repair-capable candidate-only owner
that preserves all endpoint identities and never replays the passed CUDA
producer or the consumed materializing arm. The requested cumulative project
ceiling is `$8.00`: prior measured spend is `$3.485688`, and a conservative
100-minute H200 lifecycle adds at most `$4.083333`, for `$7.569021`
cumulative. No provider create or claim is authorized until the new
reservation and owner-ready artifact are both durable.
