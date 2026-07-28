# Load-adaptive exact NGRAM bypass

## Question

Can the pinned Gemma 4 server preserve exact greedy outputs while using
ordinary one-token target decoding whenever eight or more requests are
running, and use the retained depth-12 NGRAM path only below that load?

## Why this matters

The exact sparse-penalty endpoint costs `$0.139616/M` but accumulates
`7.095` seconds of final client drift with a `+0.03503 seconds/request` late
slope. At eight or more running requests its NGRAM acceptance averages about
`5.1`, while every speculative step evaluates 12 target rows.

The closed two-stage verifier proved that this is real avoidable work: it
removed `22,542/56,808` target rows. However, its extra forward and
recombination improved planning cost by only `$0.000243/M` and changed 80 of
871 output sequences. A high-load bypass is materially different: it does
not truncate or split a speculative tree. It routes the whole batch through
the runtime's ordinary greedy target-decode path and therefore has a direct
route to exact semantics.

## Frozen experiment

- Bind the exact model, revision, image, checkpoint, request trace, sparse
  baseline, installed sources, and two-stage terminal in
  `DIRECTOR_BINDING.json`.
- Stack the exact direct sparse min-new-token update.
- Below eight running requests, preserve the depth-12 NGRAM path unchanged.
- At eight or more running requests, bypass speculative draft and verify
  work for the whole scheduling step and execute ordinary greedy target
  decode.
- On every threshold transition, make NGRAM match-state ownership explicit:
  clear or rebuild it from authoritative request tokens before re-entry.
- Preserve request cache ownership, positions, generated-token histories,
  finish reasons, and usage. Do not mix speculative cache slots into the
  ordinary decode step.
- Freeze threshold eight. Sweep no threshold, depth, or batching parameter.

## First decision-bearing measurement

Claim retained H200 `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` once. Run one
candidate-only fixed production prefix through request 870 against the
persisted sparse-penalty comparator. Persist exact index-aligned output
tokens, finish reason, usage, failures, threshold transitions, NGRAM and
bypass step counts, target rows, target-forward time, queue slope, and
experiment economics.

Only an exact, failure-free prefix with a credible throughput, drift, or
cost improvement admits one candidate-only fixed 1,036-request trajectory.
Replay no stock, sparse endpoint, adaptive truncation, or two-stage arm.

## Limits

- Authorized spend: `$8`.
- Accelerator: one retained NVIDIA H200 at `$2.46/hour`.
- Release by `2026-07-25T00:50:00Z`.
- Verified cleanup watchdog deadline: `2026-07-25T01:00:00Z`.
- Storage: at most 4 GiB of new project artifacts.
- Preserve every terminal and bound identity with SHA-256.

## Portfolio decision

An exact positive prefix admits the sole full trajectory. A semantic
divergence after one source-local transition repair, or a non-positive
prefix, closes this bypass implementation.
