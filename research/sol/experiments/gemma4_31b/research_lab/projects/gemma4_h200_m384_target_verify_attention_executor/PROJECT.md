# M384 target-verification attention executor

## Question

Can the qualified Gemma 4 c32 NGRAM target-verification batch be executed
through a request-owned SM90a attention dataflow that reduces launch,
metadata, and paged-KV traffic without changing exact target logits, causal
masking, KV ownership, or completion semantics?

## Why this matters

The completed cross-tick scheduler project proved that the qualified endpoint
already presents every bound FP8 linear with `M=384`: 32 requests times 12
target-verification rows. Waiting for later scheduler ticks is both
semantically illegal and unnecessary. The remaining opportunity is inside
that already-available verification wave. Gemma 4 combines 50 local-attention
layers with head dimension 256 and a 1,024-token window, plus 10 global layers
with head dimension 512. A packed target-verification attention executor could
remove repeated per-position setup, intermediate materialization, or paged-KV
conversion while retaining the exact qualified model path.

This is materially independent of the claimed down-projection → residual →
next-normalization component. It is a zero-GPU source and mechanism lane while
that H200 claim runs.

## Bound evidence and scope

- Model: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 at
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2`.
- Qualified geometry: c32 NGRAM target verification, 12 target rows per
  request, full wave `M=384`, TP1.
- Decision-bearing predecessor:
  `../gemma4_fp8_decode_cross_tick_batch_coalescing/MECHANISM_TERMINAL.json`
  at `e33b23644177d2d7238b5532ff9b581020768bd7f66ecd2265cdd8d86b4bdf28`.
- Trace reconstruction:
  `../gemma4_fp8_decode_cross_tick_batch_coalescing/TRACE_RECONSTRUCTION.json`
  at `a616600a25949e6995c86c49af3f1cf6ec14b065fd2d8355ff9258fc919c3aad`.
- Target accelerator: NVIDIA H200 SXM / SM90a. Stable chip facts should come
  from the shared accelerator inventory.
- The stock control is the strongest exact attention consumer actually reached
  by the pinned qualified endpoint, not a convenient synthetic attention
  implementation.

Trace the exact Q/K/V producer, causal target-verification layout, local and
global paged-KV consumers, page/index ownership, dtype and scale conventions,
and the output's first real downstream consumer. Determine whether current
FlashInfer, FlashAttention, CUTLASS, SGLang, or another proven implementation
already covers the required semantics before proposing custom CUDA.

The primary hypothesis is a position-aware, request-owned packed dataflow over
the 12 target rows that reuses request/page metadata and directly consumes the
production paged-KV representation. It may use a current library kernel or a
small SM90a source candidate. It must not depend on future scheduler ticks,
increase admitted concurrency, change draft acceptance, alter the causal mask,
or substitute an unqualified synthetic layout.

## Immediate experiment

Use source tracing and the existing exact trace to build the physical model:
useful FLOPs, compulsory KV and metadata bytes, grid waves, launch count,
intermediate bytes, and a strict whole-request upper bound for both local and
global layers. Name the strongest stock symbols and one predicted physical
change such as fewer HBM/L2 bytes, fewer launches, or less underfilled work.

Then publish one of:

1. A concrete source-level executor candidate, a deterministic CPU/reference
   oracle covering the exact local/global causal and paged-KV semantics, and an
   exact H200 discriminator contract with the production layouts and first
   downstream consumer; or
2. A typed analytical/source negative proving that existing fusion, dependency
   structure, compulsory traffic, resource limits, or whole-request relevance
   closes this dataflow.

Write `MECHANISM_TERMINAL.json` last. Evidence must distinguish measured,
source-backed, analytical, derived, and inferred claims.

## Limits

- Zero GPU claims, zero CUDA invocation, and zero provider spend.
- No provider lifecycle mutation and no inspection of the live down-projection
  execution project.
- No endpoint replay, generic attention sweep, cross-tick coalescing retry, or
  quality campaign.
- Wall-clock budget: 110 minutes.
- Storage budget: 2 GiB.

## Portfolio-changing result

A source candidate with a passing exact reference oracle and a credible
scope-matched bound opens a later H200 exact-consumer measurement after the
current claimant releases and spend authority is adjudicated. A physical or
semantic negative closes only this M384 packed-attention dataflow and redirects
the independent lane to another qualified within-tick mechanism.
