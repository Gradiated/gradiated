# Lossless output-head low-rank residual index: disjoint-query transfer

## Question

Does the frozen rank-32 residual index from
`gemma4_lossless_output_head_lowrank_residual_index` preserve the exact stock
candidate set and reduce net physical output-head traffic on 32 hidden rows
that were not used to learn or evaluate that index?

## Why it matters

The predecessor reported a large exact-reference result—103 of 262,144
physical survivor rows and 90.0035% net bytes avoided—but learned its basis on
the same 32 queries used for evaluation. The exact capture contains 1,536
unique hidden rows, so a disjoint-query test is the cheapest discriminator
between a reusable lossless output-head mechanism and in-sample overfitting.
The output head accounts for about `0.0351006 s/request`; a transferable
physical reduction would justify an exact-consumer GPU component, while a
failure closes this frozen low-rank representation without affecting the QKV
endpoint lane.

## Exact scope

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Read
  `../gemma4_lossless_output_head_lowrank_residual_index/LOSSLESS_LOWRANK_RESIDUAL_TERMINAL.json`
  once and reuse its persisted rank-32 index, exact tied BF16 weights, runner,
  and exact capture read-only.
- Freeze every learned index byte. Select 32 deterministic hidden rows from
  the remaining exact capture only after proving they are disjoint from every
  row used to fit or evaluate the predecessor. Fail closed if row provenance
  cannot establish that separation.
- Preserve the recovered stock consumer: temperature-zero greedy argmax,
  monotone softcap, and min-token stop masking. Certify the complete possible
  stock candidate set, not only top-1 agreement.
- Charge the 32-row physical union of exact weights plus projection, index,
  metadata, score buffers, survivors, and exact verification traffic. Report
  logical pruning separately and do not amortize query-specific index
  construction into a reusable serving claim.

## Immediate experiment

Use `$researcher` with deep profile and `$experiment-run`. Run one deterministic
CPU/reference held-out discriminator against the frozen persisted index. Publish
`LOSSLESS_LOWRANK_RESIDUAL_DISJOINT_TERMINAL.json` with row-provenance hashes,
exact stock-set containment, survivor union, gross and net physical bytes, and
a typed pass/fail classification. Do not tune the basis, rank, thresholds, or
held-out row selection after seeing the result.

## Limits

- Wall clock: 45 minutes.
- GPU/provider spend: `$0`; do not call `gpu_pool`, SSH, Docker, CUDA, or any
  provider API.
- Additional storage: 2 GiB.
- Do not mutate the predecessor or the QKV endpoint project.

## Portfolio-changing result

Promote to one exact-consumer H200 component only if the frozen index preserves
the exact stock candidate set and still avoids positive net physical traffic
under the fully charged held-out union. Otherwise close frozen low-rank
residual transfer and redirect output-head work to a materially different
representation.
