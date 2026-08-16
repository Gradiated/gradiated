# H100 local-KV transaction coalescing

## Question

For the exact Gemma 4 31B v0.5.15 NGRAM workload on H100, does the stock
page-size-one local-KV ownership path incur avoidable page-index gathers or
global-memory transactions that a request-owned contiguous E5M2 ring can
remove, independently of persistent L2 residency?

## Why this matters

The source-complete H100 L2 analysis closed persistent residency for this
workload: batch 32 exposes about 12.49 GiB of distinct local-prefix KV per
model step, while an optimistic full 50 MiB L2 bound saves only 0.39% of
local unique bytes. That result explicitly leaves address coalescing and
indexing distinct. A v0.5.13 H200 implementation of a producer-bound
contiguous ring was byte-exact and improved its scope-matched endpoint by
3.10%, but neither the gain nor its physical cause transfers to H100 or
v0.5.15.

This project asks the missing causal question before spending another GPU
sample: whether the exact H100 producer/consumer path has a source-bound,
non-overlapping transaction or indexing reduction at all.

## Bound scope

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: official SGLang v0.5.15 commit
  `f63458b5beaceabbd9d749b9fc956370e1b649e6`.
- Image:
  `docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd`.
- Accelerator model: NVIDIA H100 SXM with 50 MiB L2 and the shared
  accelerator-inventory identity.
- Phase and consumer: local-layer extend/target-verification and decode KV
  reads through the exact Triton attention backend; global layers remain
  unchanged.
- Geometry: 50 local layers, 1,023-token runtime prefix, 16 KV heads,
  head dimension 256, E5M2 K/V, page size one, NGRAM verification depth 12,
  exact 1,036-row request trace with batch groups up to 32.

## Evidence to produce

Use `$kernel-research` and bind the actual producer and consumer symbols,
strides, ownership, padding, request reuse, prefix aliasing, and accepted-KV
settlement. Reconstruct the stock allocator/address schedule from pinned
source and exact request rows; do not substitute the prior synthetic
round-robin fragmentation fixture for realized stock addresses.

Build a deterministic transaction model that reports, separately:

1. compulsory local K/V payload bytes, which no layout may claim to remove;
2. page-index and ownership metadata bytes;
3. predicted 32-byte sector and 128-byte transaction counts for stock and a
   request-generation-owned contiguous ring;
4. alignment, vector width, warp lane mapping, grid/tile geometry, and
   boundary waste;
5. the lower and upper whole-request relevance implied by the exact release
   groups, clearly labeled analytical or synthetic.

Specify one source-complete candidate only if the model finds a positive
non-overlapping reduction. The candidate must preserve canonical E5M2
producer bytes and cover CUDA-graph padding, request reuse, prefix
sharing/restoration, five-local/one-global separation, and NGRAM accepted-KV
settlement. Provide a CPU reference/oracle over exact and discriminating
boundary mappings; do not claim runtime correctness or performance without
CUDA.

## Resources and prohibitions

- CPU/source analysis only: no provider creation, bench claim, SSH, CUDA, or
  workload launch.
- Do not read, signal, or mutate the live endpoint owner or its H100.
- Do not replay the consumed 171-request discriminator or the sole
  791-request endpoint.
- The prior H200 endpoint is evidence that the question is worth resolving,
  not a transferable H100 baseline or result.

## Decision artifact

Persist `TRANSACTION_RESULT.json`, hash-bound to the pinned sources, exact
request trace, H100 L2 result, and H200 ring terminal. Return:

- `candidate` with a source-bound transaction/index reduction, complete
  lifecycle invariants, CPU oracle, and the smallest future checkpoint-free
  H100 counter/consumer test; or
- `typed_none` if stock addresses are already equivalently coalesced, the
  reduction is metadata-only or overlaps native tiling, realized addresses
  cannot be reconstructed without GPU evidence, or the bound is too small or
  uncertain to justify implementation.

A positive analytical result only nominates a future component measurement
after the live endpoint releases and a director confirms spend authority. It
does not authorize a GPU claim or endpoint run.
