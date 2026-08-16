# Gemma 4 H200 fixed-M384 target-verifier executor rewrite

## Question

Can a cohesive exact-shape rewrite of the native-NGRAM target-verification
executor reduce the current quality-qualified H200 endpoint from
`0.625149101968745` to at most `0.500119281574996 s/request`?

## Why this is a 20%-class route

The repaired c32 verification trace placed 94.4% of its measured verification
window behind the first acceptance synchronization while queued GPU target
work completed. Cheap surrounding work is not the answer:

- native NGRAM already accepts almost the full 12-token block and a causal
  proposal ensemble changed endpoint target work by 0%;
- an 84.42% penalty-component reduction moved the endpoint only 0.107%;
- a 13.46% packed-mask component reduction moved the endpoint only 0.158%;
- removing the dominant allocator staircase did not remove release drift.

At c32 and depth 12 the repeated target shape is approximately `M=384`.
Current kernels and dataflow are general-purpose. This project asks whether a
fixed-geometry, graph-owned executor can materially lower the complete target
forward rather than polishing another small preparatory operation.

Use `$researcher`, `$kernel-research`, and `$experiment-run`.

## Immediate experiment

Use `EVIDENCE_BINDING.json` and the persisted trace before collecting anything
new. Construct a non-overlapping request and verification critical path. Name
the top target-forward kernel families, their exact shapes/layouts/dtypes,
producer and consumer symbols, launch counts, registers/shared memory/spills,
and decisive HBM/L2/tensor/occupancy evidence. If the existing capture cannot
establish that target-forward work is at least 80% of the current request, make
one short profiler capture on the retained H200 after DFlash releases and use
that result as the bound.

When the 20% ceiling is physically open, implement one cohesive executor
rewrite against the hottest recurring boundary. It may combine adjacent
operations when that is necessary to remove material traffic or launches. The
leading design space is:

- fixed-`M=384` warp-specialized FP8 projection schedules rather than another
  replay of the rejected `1x2x1` cluster orientation;
- graph-owned workspaces and stable depth-major row ownership;
- residual/RMSNorm/FP8-quantization fusion that preserves the pre-rounding
  residual semantics the prior generic fusion violated;
- QKV or MLP epilogues that avoid materialized activation traffic;
- accumulator partitioning or work decomposition for the 255-register global
  attention kernel, but only if its non-overlapping share justifies inclusion.

The researcher may choose a better source-backed decomposition. The result
must be an actual implementation and exact-consumer measurement, not a design
document. Test production M384 plus only discriminating boundary shapes,
consume the real downstream operation, then run one matched endpoint pair if
the measured component and critical-path bound remain capable of a material
whole-request gain. Retain compatible smaller gains, but do not claim the 20%
objective without the endpoint.

## Contract

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Baseline: quality-qualified native NGRAM at
  `0.625149101968745 s/request`.
- Target: `<=0.500119281574996 s/request`, 32 concurrent requests, depth 12,
  exact campaign token geometry and accounting.
- Hardware: H200 SXM. Reuse the protected DFlash H200 after its owner releases
  when lifecycle and resident state permit; researchers never create or
  destroy provider resources.
- Correctness: exact target consumer outputs, request ownership, positions,
  cache accounting, graph replay, and deterministic greedy semantics before
  performance promotion.
- Spend: at most `$8` new provider exposure; local/source work may begin now.
- Current phase: complete the critical-path proof, cohesive source
  implementation, and exact-consumer oracle offline by
  `2026-07-25T20:30:00Z`; do not inspect or claim either active bench.
- Later GPU phase: only after a director rebind following DFlash release,
  with at most three claimed H200 hours under the `$8` ceiling and a
  compatible absolute watchdog.
- Artifacts: bound identities, critical-path union, exact shape register,
  source/build manifest, correctness fixtures, warm timing distributions,
  decisive counters, endpoint pair if admitted, economics, and concise log.

## Deep exactness continuation after the mixed-M8 terminal

`MIXED_LOCAL_M384_TERMINAL.json` closes the exact local-M8 implementation, not
the measured local-attention opportunity. Its mixed dispatch and component
were valid and positive, but the completed 32/32 target-decision guard failed
semantic equality. Do not replay that endpoint or reopen its operational
repairs.

Work offline from the persisted guard, component outputs, NCU counters, and
pinned Triton sources. Localize the earliest divergent target decision or
accumulation boundary and implement at most one materially different schedule
that preserves stock reduction order—or provides an exact target-decision
equivalence argument—while retaining a credible reduction in accumulator,
register, or shared-memory pressure. Return source plus an exact-consumer GPU
falsifier or a typed `none`. This continuation has `$0` spend and may not claim
or mutate a provider bench.
