# Distinct-request NGRAM promotion gate

## Question

Can native depth-12 NGRAM retain its long accepted trunks under sustained load
by admitting a verified suffix to the existing global corpus only after the
same suffix is observed from at least two distinct request IDs?

## Why this matters

The bound source probe shows that every request writes its last 18
target-verified tokens into one global online corpus, while `buildRecency`
gives recent branches fixed breadth. A rare branch therefore collapses
accepted length from about 12 to 5 and expands a 358-token completion from
about 29.83 to 71.60 target rounds. The invalid request-local endpoint reached
the economic target, but its custom per-request tree merge has not produced a
valid semantic sample and repeated reloads are now the limiting cost.

This candidate is materially distinct:

- It changes write admission, not frequency-mode or BFS read ranking.
- It preserves global breadth, depth 12, target verification, and the stock
  tree topology.
- It creates no request-local draft tree, ancestry mask, accepted-token map,
  or cleanup path.
- It requires support from distinct request IDs, so repetition within one rare
  request cannot promote its branch globally.

## Bound evidence and identities

- Pinned `NGRAMWorker` source:
  `../gemma4_ngram_sustained_acceptance_causal/inputs/bound/ngram_worker.source.py`,
  SHA-256 `27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554`.
- Causal result:
  `../gemma4_ngram_sustained_acceptance_causal/artifacts/causal-source-probe/RESULT.json`,
  SHA-256 `44e631b769d53127ca98907e0205132afa0fd3530595d6dd9962a999d3c3b396`.
- Requests SHA-256:
  `10e7edacaa194fd0f43b3a3c38f7d91cec0ceba22df8e08e3b5897b174346135`.
- Exact semantic rows SHA-256:
  `630d05bd860d1dd22c3e35ba2d8f792afc5051f0c68e0a74a9deda8140a02b36`.
- Launch SHA-256:
  `8349853a7eac9e73211f5d3081c834c05f78e0fd292ddbe5acb921b1824a523d`.
- Model:
  `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime image:
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.

Materialize and hash the referenced immutable inputs inside this project before
any claim. Reject any identity mismatch.

## Scope

First reproduce the three bound source-probe scenarios. Implement one bounded
probation table keyed by the exact suffix bytes and tracking distinct request
IDs. Promote a suffix to the unchanged global `batch_put` path only at support
two. Bound memory and erase probation entries deterministically; do not change
the read path, tree mask, retrieval indexes, target verifier, breadth, depth,
match mode, scheduler, workload, or server representation.

The offline probe must predict:

- common suffixes promote quickly and preserve accepted depth near 12;
- the request-32 and request-790 rare branches remain probationary;
- no suffix can self-promote through repeated steps from one request;
- bounded memory and cleanup do not depend on request completion order.

Only after that probe passes and the director returns a compatible warm H200
to available may one candidate-only 791-request discriminator run. Require
positive activation identity, exact normalized rows, zero failures, and
unaffected-request accepted depth that does not collapse after the rare branch.
Only if it passes may one 1,036-request full-arrival endpoint run. Retain only
with exact semantics, zero failures, peak queue at most 30, final queue zero,
stable release timing, fewer target-verify rounds, and at most `$0.14/M`.

Replay no control, threshold-8 bypass, frequency mode, global breadth-one,
request-local verified-trunk endpoint, scheduler arm, or other settled arm.

## Resources

- Total authorized spend: `$3`.
- Provider compute: at most 50 H200 minutes, including setup and failures.
- Wall clock: 90 minutes from researcher start.
- Local compute: at most 2 CPU-hours.
- Storage: at most 6 GiB project-local.
- Provider mutation is forbidden to the researcher. Claim only a
  director-registered compatible bench whose lifecycle covers the declared
  owner deadline.

## Decision

Promote only if the exact-source probe and discriminator support the predicted
rare-branch quarantine without a new semantic or server-stability defect.
Close this candidate if common paths fail to promote, distinct-request support
does not prevent the measured collapse, or the first valid endpoint misses the
semantic, reliability, queue, or economic gate.
