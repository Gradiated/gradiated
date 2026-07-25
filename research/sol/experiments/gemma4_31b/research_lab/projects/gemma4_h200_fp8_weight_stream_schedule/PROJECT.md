# H200 FP8 weight-stream schedule

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

- Exact model: `google/gemma-4-31B-it` at the campaign's pinned checkpoint.
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
