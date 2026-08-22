# Packed M384 Hopper target verifier

## Question

Can one packed heterogeneous target-verification execution boundary for Gemma
4's exact hybrid attention geometry expose enough independent work and shorten
enough live state to materially reduce target-verifier time on one H200,
without changing target semantics?

The first result is an offline falsifier, not a GPU readiness packet. It must
decide whether a concrete packed decomposition is worth an exact-shape H200
component measurement.

## Why this matters

The campaign's fixed qualified H200 denominator is
`0.625149101968745 s/request`; the current target is
`0.500119281574996 s/request`. Lossless parallel drafting can only improve
endpoint economics when target verification converts accepted draft work into
efficient GPU work. The campaign explicitly identifies an M384 verifier with
Gemma's five-local/one-global hybrid attention as a high-upside independent
mechanism.

This lane is independent of
`gemma4_h200_fixed_floor_crossop_executor`: it must not read, claim, mutate, or
wait on that project's R5 bench, runner, owner, packet, or endpoint artifacts.

## Bound scope

- Model: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime prior: pinned SGLang v0.5.13 source; current upstream implementations
  may be inspected as source-backed alternatives, but claims remain pinned
  until reproduced.
- Phase: decode-time target verification of a packed total of `M=384`
  proposed-token rows drawn from heterogeneous active requests.
- Geometry: Gemma 4 hybrid five-local/one-global attention, local head
  dimension 256 with window 1024, global head dimension 512, paged KV, and the
  exact GQA/KV-head mapping found in the pinned model source.
- Producer/consumer boundary to bind from source before proposing code:
  packed target token/position and request-slot rows entering
  `Gemma4Attention.forward`, through the runtime-selected local/global paged
  attention consumers, into target logits and the unchanged
  acceptance/verification consumer. Record the exact pinned symbols,
  layouts, strides, graph-padding rules, and fallback path; do not substitute
  a convenient synthetic attention API.
- Hardware: NVIDIA H200 SXM (`sm_90`), 132 SMs, 256 KiB register file per SM,
  228 KiB local/shared memory per SM, 50 MiB L2, 4.8 TB/s HBM, FP8 support,
  TMA, thread-block clusters, and 32-thread warps, as recorded in the shared
  accelerator inventory.
- Strongest baseline: the exact pinned runtime consumer for each local/global
  shape. Any fused or packed candidate must preserve paged-KV layout, online
  softmax, GQA indexing, CUDA-graph padding, output layout, and the unchanged
  acceptance consumer.

## Physical hypothesis

The current verifier likely presents heterogeneous local/global rows as
separate small grids with accumulator lifetime and launch fragmentation that
underfill 132 H200 SMs. Packing compatible rows into one task schedule, while
partitioning the d512 value accumulator or using an explicit
producer/consumer stage boundary, should increase full grid waves and shorten
register live ranges. The counter-movement prediction is more active
blocks/SM and fewer tail/idle SM intervals without spills or extra HBM traffic
large enough to erase the gain.

Competing explanations are that the verifier is already HBM/KV-bandwidth
limited, that global d512 accumulation dominates regardless of packing, that
local/global semantics prevent useful co-scheduling, or that target
verification is too small a non-overlapping endpoint share. The falsifier must
separate these cases.

## Immediate experiment

Use `$researcher` with the `deep` profile, `$kernel-research`, and
`$experiment-run`.

1. Trace the exact pinned producer/consumer and freeze the M384 row mix,
   local/global shapes, dtypes/scales, strides, paged-KV mapping, and graph
   padding. Label missing runtime telemetry as unknown.
2. Build a deterministic wave/register/shared-memory/compulsory-byte model for
   the stock decomposition and at least three legal alternatives: packed task
   scheduling only, partitioned d512 accumulation, and a TMA or
   producer/consumer staged variant. Include a negative control expected to
   regress from redundant KV traffic or spills.
3. Calibrate stock resource assumptions from existing compiler metadata when
   scope-matched; otherwise emit the minimum exact H200 metadata measurement
   required later rather than guessing.
4. Produce one concrete source-level candidate decomposition and an
   independent CPU/reference oracle for the indexing and online-softmax state,
   or kill the line when conservation-law and sensitivity bounds show that no
   legal candidate can materially affect the endpoint.
5. Preregister the shortest exact-shape H200 falsifier only if the offline
   result survives. Do not claim or reserve a GPU in this turn.

## Decision and evidence contract

Write `MECHANISM_TERMINAL.json` containing:

- a typed observation-to-opportunity register;
- exact source/runtime/model/hardware identities and producer/consumer symbols;
- stock and candidate grid waves, estimated registers/shared memory, useful
  FLOPs, compulsory and repeated bytes, arithmetic intensity, tail waste, and
  sensitivity ranges;
- competing explanations and the observation that would distinguish each;
- CPU/reference correctness evidence for the proposed mapping, if promoted;
- a whole-request upper bound normalized per completed request, with summed
  batch work kept separately;
- one promoted exact-shape GPU experiment contract or a typed analytical
  negative.

Label claims measured, source-backed, derived, inferred, or synthetic. A
simulation promotes only an exact-shape measurement; it cannot establish an
endpoint improvement.

## Budgets and restrictions

- Wall clock: 60 minutes.
- Paid spend: `$0`.
- GPU time: zero.
- Controller CPU: at most 30 core-minutes.
- Storage: at most 500 MiB under this project.
- Network: source/paper inspection only; no provider mutation.
- Do not claim the shared H200, replay an endpoint, create a provider resource,
  edit another project, or turn this into a generic literature survey.

The result changes the portfolio when it either identifies a legal candidate
with a credible and falsifiable endpoint-relevant bound, or proves that packed
M384 verification cannot compete with higher-value mechanisms under the exact
geometry.
