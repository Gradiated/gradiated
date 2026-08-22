# Lossless Gemma output-head branch-and-bound

## Question

Can the exact `262,144`-way Gemma 4 output projection be evaluated with a
hierarchical or blockwise upper-bound search that provably preserves the
stock top logits while skipping a decision-relevant fraction of weight reads
for the campaign's prompt-heavy decode workload?

## Why it matters

The campaign needs a complete endpoint below `0.500119281574996 s/request`.
The very large dense vocabulary head is compulsory work and is materially
independent of the current gated-activation fusion. A lossless shortlist or
branch-and-bound implementation could reduce weight traffic without changing
the checkpoint, token semantics, or quality contract.

## Relevant evidence

- Exact model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Fixed qualified denominator: `0.625149101968745 s/request`.
- Vocabulary size: `262,144`; initial mode is text-only, non-reasoning.
- Current H200 gated-activation work is a separate serial lane and must not be
  claimed or modified by this project.

## Scope

Use `$researcher` with the deep profile and `$experiment-run`. Reconstruct the
exact output-head geometry and stock consumer from the pinned checkpoint and
runtime. Design one lossless bound or exact two-stage search, implement its
CPU/reference form, and test pruning on any already-durable exact hidden-state
captures that can be located directly. If no such capture exists, derive the
strongest weight-only bound and report whether it is intrinsically too loose;
do not manufacture a synthetic performance claim.

The first result must explain the causal chain from head geometry and H200
memory behavior to the proposed search and quantify either exact pruning or a
falsifying bound. It may recommend a later target-H200 component but may not
claim a GPU, reserve spend, or create provider resources.

## Resources and limits

- Wall clock: 45 minutes.
- GPU/provider spend: `$0`.
- Additional storage: 2 GiB.
- Shared tools: `research/factory/tools` and
  `research/factory/SCIENTIFIC_TOOLS.md`.

## Portfolio-changing result

Continue to an exact H200 consumer only if the lossless reference preserves
stock top logits and shows a credible path to avoid enough head-weight traffic
to matter at request level. Close this exact bound/search if it cannot prune
substantial work without approximation; that does not close learned or
quality-recovered sublinear heads.
