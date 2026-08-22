# Gemma 4 H200 decode task-graph hot block

## Question

Can one production-shaped, semantics-preserving task-graph boundary reduce
host/launch and intermediate-memory overhead across a recurring Gemma 4 c32
decode block—RMSNorm, dynamic-FP8 quantization, GEMM, residual/activation, or
the adjacent attention/MLP handoff—enough to justify a target-H200 component
measurement?

## Why this matters

The campaign needs `0.500119281574996 s/request` against the fixed qualified
H200 denominator `0.625149101968745 s/request`. The consumed QKV endpoint did
not yield an eligible result, and the frozen output-head PQ proxy is blocked
in a long producer. This lane attacks an independent full-stack source of
time: repeated launch, synchronization, and materialization boundaries rather
than attention placement or output-head representation.

## Evidence and exact scope

- Exact checkpoint: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Pinned runtime/image: SGLang `v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2`
  in `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Workload: the campaign's exact non-reasoning c32 request geometry around
  4,214 prompt and 358 output tokens.
- Read the current QKV endpoint packet/archive and pinned runtime source
  read-only only as needed to identify one actual producer-to-consumer block.
  Do not reconstruct the missing QKV path proof or replay its endpoint.

Build a typed observation-to-opportunity register, localize one concrete
source path and tensor geometry, then produce either:

1. one source-complete lifecycle-pure exact-shape hot-block runner with a
   correctness oracle and a predicted non-overlapping wall/counter movement;
   or
2. a measured/source-backed falsifier showing that the modifiable
   launch/materialization fraction is too small or inaccessible in the pinned
   stack.

This is mechanism research, not a generic executor design or another
readiness ladder. Do not claim a GPU in this cycle.

## Resources and limits

- Wall clock: 45 minutes.
- Spend: `$0`; CPU/source analysis and local deterministic tests only.
- Storage: 2 GiB additional.
- Forbidden: `gpu_pool`, SSH, Docker, CUDA, endpoint traffic, provider APIs,
  and mutation of another project.
- Required terminal: `TASKGRAPH_HOTBLOCK_DISCRIMINATOR.json`.

## Portfolio-changing result

A source-complete exact-shape runner with a credible scope-matched wall bound
promotes to the retained or next H200 component measurement. A localized
negative closes only that selected block and returns the residual source path
and next best boundary; it does not close cross-operator execution generally.
