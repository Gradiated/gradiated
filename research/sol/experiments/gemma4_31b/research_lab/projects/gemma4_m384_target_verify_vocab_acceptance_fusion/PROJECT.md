# M384 target-verification vocabulary and acceptance fusion

## Question

Can the qualified Gemma 4 c32 NGRAM target-verification wave consume the
262,144-way output head directly through the exact sampler and acceptance
logic without globally materializing every M384 vocabulary-logit row, while
preserving the target distribution, selected tokens, acceptance, KV ownership,
and completion semantics?

## Why this matters

The qualified endpoint already exposes 32 requests times 12 target rows in one
`M=384` verification wave. A BF16 `384 x 262,144` logit matrix is about
192 MiB before sampler workspace and downstream reads. If the production path
materializes and rereads that matrix, a request-owned tiled output-head
consumer could remove substantial HBM traffic and launches at a boundary
independent of the grouped paged-attention candidate.

This project tests an exact serving transformation, not vocabulary pruning or
a reduced model. It may stream exact logits through a production-equivalent
online sampler/acceptance reduction, but it may not approximate, shortlist,
delete vocabulary entries, change sampling policy, or use draft tokens to
alter target probabilities.

## Bound scope

- Model: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 at
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2`.
- Workload: qualified c32 NGRAM target verification, 32 requests, 12 target
  rows per request, `M=384`, TP1.
- Decision-bearing geometry source:
  `../gemma4_h200_m384_target_verify_attention_executor/MECHANISM_TERMINAL.json`
  at `1f2b98bbadf2cb05afad46fdd466fe89ee1adb09b4344825b81777d8b550695b`.
- Target accelerator: NVIDIA H200 SXM / SM90a; use the shared accelerator
  inventory for stable chip facts.
- Stock control: the exact pinned output projection, logits processors,
  sampler, target-token comparison, and acceptance/commit path reached by the
  qualified endpoint.

Trace the hidden-state producer through the output head and every consumer of
the target logits. Establish whether logits are needed as a full tensor for
any production feature or whether exact sampling and acceptance can be
computed by a tiled, request-owned consumer. Bind dtype, accumulation,
temperature/top-k/top-p/min-p or greedy branches, RNG ordering, logprob
requirements, draft-token comparison, accepted-prefix logic, and first KV
commit consumer.

## Immediate experiment

Build a physical model for stock compulsory weight/logit bytes, launches,
grid waves, workspace, and whole-request relevance at M384. Falsify at least
three legal decompositions, including a fused output-head/sampler reduction,
a tiled exact-logit consumer with bounded row workspace, and a materialized
control.

Publish either:

1. A concrete source-level candidate, deterministic CPU/reference oracle over
   exact sampling and acceptance branches, and an exact H200
   producer-to-acceptance discriminator contract; or
2. A typed source/semantic/physical negative proving that exact production
   consumers require materialization or that the removable traffic cannot
   matter.

Write `MECHANISM_TERMINAL.json` last. Separate source-backed, analytical,
derived, synthetic, and inferred evidence.

## Limits

- Zero GPU claims, zero CUDA invocation, zero reservation, and zero provider
  spend.
- Do not inspect or mutate the live/queued M384 attention project or the
  retained H200 lifecycle.
- No vocabulary pruning, approximate top-k, altered RNG, changed sampler,
  quality proxy, generic output-head sweep, or endpoint run.
- Wall-clock budget: 110 minutes.
- Storage budget: 2 GiB.

## Portfolio-changing result

A source candidate with a passing exact oracle and credible traffic/launch
bound opens a later exact-consumer H200 discriminator. A semantic or physical
negative closes only this materialization/fusion boundary and redirects the
independent lane to another qualified M384 target-verification operator.
