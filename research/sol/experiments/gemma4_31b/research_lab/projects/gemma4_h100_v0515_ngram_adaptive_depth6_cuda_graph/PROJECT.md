# Exact depth-6 CUDA-graph admission for adaptive NGRAM

## Question

Can SGLang v0.5.15 admit an exact depth-6 CUDA graph for the frozen adaptive
NGRAM representation at batches of eight or more, without padding, stale
metadata, graph-key aliasing, or ownership/KV errors?

## Why this matters

The exact H100 component established end-to-end correctness for both native
depths. Its batch-8/depth-6 arm used eager execution and had a 0.397040 ms
combined median, while batch-7/depth-12 used a CUDA graph and had a 0.414096
ms median. Those 100-sample arms are underpowered and confound batch, depth,
and graph mode, so they do not support a speed claim. They do identify a
specific potential limiter: halving verification rows at the adaptive
threshold may be partly hidden by losing graph execution.

The packed-mask project is independently measuring a direct endpoint and must
not be inspected or disturbed. This project uses only the immutable adaptive
depth artifacts and pinned v0.5.15 source.

## Hypothesis

Graph identity can include active speculative depth and the exact batch/token
geometry, allowing separate depth-12 and depth-6 captures. The depth-6 graph
should bind its own target-verify metadata, scheduler stride, output ownership,
and KV movement rather than borrowing depth-12 buffers or padding to capacity
12. If the capture path cannot maintain those invariants across 7→8→7
transitions, the result should be a precise negative localization.

## Scope

- Target runtime: official SGLang v0.5.15 commit
  `f63458b5beaceabbd9d749b9fc956370e1b649e6`.
- Target accelerator behavior: NVIDIA H100 CUDA graph capture and replay.
- Frozen adaptive rule: depth 12 for running batches 1–7; depth 6 for batches
  8 and above.
- Preserve the two native producers, active-depth metadata and scheduler
  stride, ragged result ownership, greedy acceptance, KV movement, and all
  fail-closed behavior.
- Inspect the exact graph key, capture pools, replay buffers, attention
  metadata, scheduler settlement, and ownership paths in the bound source.
- Produce a project-local source-complete implementation if feasible, plus
  deterministic graph-key and lifecycle fixtures covering at least
  7→8→7, permutations, cancellation/completion, slot reuse, empty/partial
  matches, and both positive and fail-closed key mismatches.
- Do not use a provider or GPU, load a checkpoint, run an endpoint, inspect the
  packed-mask project, or claim latency or economics.

## Resources and limits

- Authorized spend: `$0.00`.
- Provider/GPU: forbidden for this stage.
- Wall-clock deadline: `2026-07-25T16:00:00Z`.
- The immutable inputs and their hashes are bound in
  `DIRECTOR_BINDING.json`.

## Result contract

Persist:

- `ADAPTIVE_DEPTH6_CUDA_GRAPH_RESULT.json`
- `ADAPTIVE_DEPTH6_CUDA_GRAPH_DECISION.md`
- an immutable source/fixture manifest for any implementation

The terminal classification must be one of:

- `source_complete_h100_component_ready`: exact depth-6 capture is
  source-complete and all state/key fixtures pass;
- `localized_negative`: a concrete source or state invariant prevents exact
  depth-6 capture without padding or semantic risk;
- `invalid`: the bound artifacts or exact source identity cannot be verified.

The result changes the portfolio by either nominating one short exact H100
graph-versus-eager component after the current endpoint consumer releases the
warm bench, or removing dual-depth graph capture from the adaptive endpoint
candidate.
