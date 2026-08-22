# Lossless clustered output-head MIPS

## Question

Can a hierarchical exact maximum-inner-product index over Gemma 4's tied
`262,144 × 5,376` output-head rows prune whole contiguous weight clusters for
the real decode-c32 hidden states, while certifying the exact stock sampler
candidate set and avoiding enough physical weight traffic to justify an H200
component?

## Why this is distinct

The completed fixed-coordinate residual-Cauchy method was lossless but avoided
only `3.7458%` of physical 32-row union bytes (`4.4325%` even with an oracle
incumbent). Its weakness was one global residual norm per vocabulary row after
reading common coordinates. This project instead groups nearby full weight
vectors and uses centroid/radius or equivalent tree bounds to reject entire
contiguous clusters before reading their member weights.

The output head streams roughly 2.82 GB of tied BF16 weights per dense
traversal, so a genuinely selective exact index remains economically relevant
to the fixed `0.625149101968745 s/request` denominator and
`0.500119281574996 s/request` target.

## Exact scope

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Geometry: tied output head, `262,144 × 5,376`, BF16 stock projection.
- Inputs: reuse read-only the exact 32-request hidden-state capture and weight
  identity accepted by predecessor terminal
  `../gemma4_lossless_output_head_branch_bound/LOSSLESS_BRANCH_BOUND_TERMINAL.json`
  (`29db51b9…`). Do not copy the large weights when a read-only link or view is
  possible.
- Stock consumer: mechanically recover the actual pinned sampler truncation
  and softcap contract. Certify every logit needed by that consumer; a top-1
  certificate alone is insufficient if the stock sampler consumes a larger
  set or tail mass.
- Candidate: one multi-level centroid/radius, ball-tree, or equivalently
  stronger exact cluster bound. Cluster membership and radii may be built
  offline, but every pruning inequality must be conservative in the stock
  numeric scope.
- Resource fence: CPU/reference and source work only. No GPU, SSH, Docker,
  provider API, or `gpu_pool` call.

## Immediate experiment

Use `$researcher` with the deep profile and `$experiment-run`. Reconstruct the
stock sampler requirement, build the cheapest exact clustered index that can
be evaluated within 45 minutes, and run it on the same 32 real hidden rows.
Report logical per-query pruning and the physically relevant union of member
weight pages across all 32 rows, including centroid/radius metadata and
survivor-gather traffic.

The result must prove the stock-required candidate set remains inside every
survivor set, report index build/storage cost separately from per-request
traffic, and include an optimistic oracle-incumbent bound. Falsify this
decomposition if no admissible hierarchy exceeds 5% gross physical union
avoidance or if its optimistic net byte/time bound is non-positive. A positive
reference result promotes only a target-H200 exact-consumer component, not an
endpoint or production claim.

## Budgets

- Wall clock: 45 minutes.
- Provider spend: `$0`.
- Additional storage: 4 GiB; reuse existing immutable tensors by read-only
  view.

## Portfolio-changing result

A certified positive net traffic bound promotes one H200 component that
includes traversal, metadata, survivor gather, exact rescoring, and the stock
sampler consumer. A loose or physically scattered hierarchy closes only this
cluster-bound decomposition; learned or quality-recovered sublinear heads
remain distinct.
