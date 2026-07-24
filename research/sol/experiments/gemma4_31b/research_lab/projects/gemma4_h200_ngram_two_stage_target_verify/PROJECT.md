# Exact two-stage NGRAM target verification

## Question

Can the pinned Gemma 4 NGRAM verifier preserve the complete depth-12 draft
tree and exact greedy semantics while evaluating rows 1–6 for every
high-load request and rows 7–12 only for requests that accept the entire
first stage?

## Why this matters

The retained sparse-penalty endpoint is exact and costs `$0.139616/M`, but
still accumulates `7.095` seconds of client drift with a
`+0.03503 seconds/request` late slope. Production telemetry measures average
accepted length near `5.1` once eight or more requests are running, while the
target model evaluates 12 rows for every request.

Directly truncating the fixed depth-12 tree to depth 6 is closed: the
repaired component executed 48 real CUDA rows but changed target predictions
and accepted/bonus tokens for all eight requests. Two-stage verification is
materially different because it retains the original tree, positions, and
depth-12 continuation. It skips the second half only when the first stage
already proves that continuation cannot be accepted.

## Frozen experiment

- Exact model, revision, image, checkpoint, request trace, sparse-penalty
  baseline, installed sources, and rejection terminal are bound in
  `DIRECTOR_BINDING.json`.
- Preserve the depth-12 `NgramCorpus` producer and original draft-tree order.
- At eight or more running requests, verify rows 1–6 for all requests.
- Run rows 7–12 only for requests that accept all six stage-one drafts and
  require the original continuation.
- Reconcile cache slots, request-token ownership, positions, tree masks,
  accepted drafts, and bonus tokens exactly with depth-12 verification.
- Do not sweep stage depth or load threshold.

## First decision-bearing measurement

Claim the retained H200 once and stack the bound direct sparse min-new-token
update. Run one candidate-only production prefix through request 870. Compare
every completed request index against the persisted sparse-penalty comparator
and persist stage-one rows, continuation survivors, stage-two rows, accepted
and bonus tokens, target-forward time, failures, and output-token usage.

Only exact output, finish-reason, usage, accepted-token, and bonus-token
semantics plus a credible reduction in target rows or target-forward time
admits one candidate-only fixed 1,036-request trajectory. Replay no stock,
sparse endpoint, or adaptive-truncation arm.

## Limits

- Authorized spend: `$8`.
- Release the H200 by `2026-07-25T00:50:00Z`.
- Verified cleanup watchdog deadline: `2026-07-25T01:00:00Z`.
- Preserve all terminals and source identities with SHA-256.

## Portfolio decision

An exact positive prefix admits the sole endpoint. Any output mismatch,
cache-ownership defect that survives one focused repair, or non-positive
target-work result closes this two-stage implementation.
