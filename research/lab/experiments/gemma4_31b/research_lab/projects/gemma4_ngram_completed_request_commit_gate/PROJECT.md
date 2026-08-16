# Completed-request NGRAM commit gate

## Question

Can native depth-12 NGRAM prevent a live rare request from contaminating
concurrent peers by buffering its target-verified suffix writes and committing
them to the unchanged global corpus only after that request completes?

## Why this matters

The bound causal probe attributes the acceptance collapse to every live request
continuously inserting its last 18 target-verified tokens into one global
online corpus. The repaired request-local read path was activated and measured,
but failed semantics, queue, and cost gates. The active support-two candidate
instead requires corroboration from two distinct request IDs before writing.

This hypothesis is independent of both:

- it changes write visibility in time, not support count;
- one completed request may commit without a second request;
- reads remain stock global BFS with native breadth, depth 12, and target
  verification;
- no request-local draft tree, ancestry remap, accepted-token map, frequency
  ranking, scheduler change, or breadth reduction is introduced.

## Bound evidence and identities

Use `DIRECTOR_BINDING.json`. Its identities were mechanically extracted from
the active support-two project's materialized bound inputs:

- pinned `NGRAMWorker` source SHA-256
  `27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554`;
- causal result SHA-256
  `44e631b769d53127ca98907e0205132afa0fd3530595d6dd9962a999d3c3b396`;
- requests SHA-256
  `10e7edacaa194fd0f43b3a3c38f7d91cec0ceba22df8e08e3b5897b174346135`;
- exact semantic rows SHA-256
  `630d05bd860d1dd22c3e35ba2d8f792afc5051f0c68e0a74a9deda8140a02b36`;
- launch SHA-256
  `8349853a7eac9e73211f5d3081c834c05f78e0fd292ddbe5acb921b1824a523d`;
- model
  `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`;
- runtime image
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.

Materialize these inputs inside this project and reject any mismatch before a
GPU claim.

## Scope

First inspect the pinned worker and exact runtime request lifecycle to prove an
unambiguous stable request ID and completion/abort hook. Reproduce the bound
source-probe scenarios, then implement only a bounded per-request buffer of
already target-verified suffix writes. A request's buffered writes become
visible through the unchanged global `batch_put` path only at proven
completion. Abort, ID reuse, and exceptional cleanup must discard the buffer
deterministically.

The offline discriminator must establish:

- no in-flight request can alter another request's readable corpus;
- common historical trunks remain available at native depth;
- request 32 and request 790 cannot contaminate concurrent peers before
  completion;
- completion, abort, and request-ID reuse cannot leak or double-commit state;
- memory is explicitly bounded.

If the pinned runtime exposes no exact completion/abort boundary, close the
candidate offline. Do not approximate lifecycle ownership.

Only after the offline proof passes and priority-8550 releases a compatible
director-registered H200 may one candidate-only 791-request discriminator run.
Require positive activation identity, exact normalized semantics, zero
failures, and no post-rare-branch accepted-depth collapse. Only if it passes
may one 1,036-request full-arrival endpoint run. Retain only with exact
semantics, zero failures, peak queue at most 30, final queue zero, stable
release timing, fewer target-verify rounds, and at most `$0.14/M`.

Replay no control, threshold-8 bypass, frequency mode, breadth-one,
request-local verified-trunk, support-two write gate, scheduler arm, or other
settled arm.

## Resources

- Total authorized spend: `$3`.
- Local compute: at most 2 CPU-hours.
- Provider compute: at most 45 H200 minutes, including setup and failures.
- Wall clock: 90 minutes from researcher start.
- Storage: at most 6 GiB project-local.
- Provider mutation is forbidden. Claim only a director-registered compatible
  bench after priority-8550 releases it and only when its watchdog covers the
  full declared owner deadline plus cleanup.

## Decision

Promote only if exact source ownership proves the temporal-isolation mechanism
and the valid discriminator preserves semantics while preventing live rare
branches from contaminating peers. Close if lifecycle ownership is ambiguous,
common trunks disappear, state leaks across abort/ID reuse, or the first valid
measurement misses semantic, reliability, queue, or economic gates.
