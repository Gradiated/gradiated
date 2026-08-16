# Gemma 4 sustained-load NGRAM acceptance causal study

## Question

What exact source and hardware mechanism causes native depth-12 NGRAM
acceptance and service time to collapse under sustained c32 load, and is
there one materially distinct load-aware policy worth an endpoint test?

## Evidence

On the consumed streamed-tail trajectory, `spec_accept_length` began near
`11.87` with acceptance rate `0.988`, then repeatedly settled near length
`5.0` and rate `0.364` while full-wave server spans grew from `17.095` to
more than `78` seconds and peak queue reached 41. The prior threshold-8
bypass is closed: it reduced target rows but made throughput and planning
cost worse. Tail scheduling, broadcast reuse, sparse min-token writes, and
that threshold policy must not be replayed.

## Scope

- Inspect the pinned SGLang v0.5.13 NGRAM/speculative scheduling source, the
  exact Gemma 4 geometry, and only the bound c32 telemetry needed to explain
  the acceptance/service-time transition.
- Distinguish real draft acceptance loss from metric aggregation, request
  reuse, batch-shape, queue ownership, cache-state, launch, or target-step
  effects.
- Produce one source-bound candidate materially different from threshold-8
  bypass, with exact symbols, causal chain, predicted queue/acceptance and
  accelerator-counter changes, semantic risk, and the smallest candidate-only
  endpoint arm that would falsify it.
- Do not claim performance from source reasoning and do not run, claim,
  reload, or mutate a GPU or provider resource.

## Decision

Promote only a candidate whose predicted saved work lies on the measured
critical path, preserves target semantics, does not repeat a settled policy,
and can be implemented and measured on the retained native-NGRAM endpoint in
one bounded arm. Otherwise close this causal lead and nominate a materially
different mechanism.

## Endpoint phase

The source probe promoted `request_local_verified_trunk`. Implement only that
hash-bound overlay:

- Retain a bounded per-request trie seeded and updated only from that
  request's target-verified tokens.
- Reserve its longest verified continuation as the draft trunk, then fill
  unused rows from the unchanged global BFS recency tree.
- Erase request-local state through the existing finished-request cleanup and
  fall back to the current global tree until local verified state exists.
- Preserve native depth 12, 12 target-verified rows per request, the pinned
  model/image/checkpoint/runtime, and the full individual-arrival workload.
- Run exactly one candidate-only 1,036-request endpoint. Replay no control,
  threshold-8 bypass, frequency mode, global breadth-one, scheduler, or other
  settled arm.
- Persist normalized semantics, failures, per-request acceptance around the
  first rare branch, target verify forwards/rows, KV allocation/free
  telemetry, release drift, queueing, elapsed time, and economics.

Retain only if all normalized rows are exact, failures are zero, target verify
rounds fall, unaffected requests retain long accepted trunks after rare
branches, peak queue is at most 30, final queue is zero, release drift does
not grow, and planning cost is at most `$0.14/M`.

## Resources

Reserve at most `$3` and use only retained bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. Apply the source overlay and reload
the resident server in place; do not create or destroy provider resources.
Write at most 6 GiB and release by `2026-07-25T04:20:00Z` under the verified
`2026-07-25T04:30:00Z` watchdog.

## Semantic and activation localization

The first complete endpoint is an invalid candidate-path result, not a
mechanism rejection or retention result. It passed cost, queue, release, and
reliability gates at `732.4464497909994` seconds and `$0.1396017174972092/M`,
but only 1,035/1,036 normalized rows matched. Request 790 first diverged at
output token 26. The terminal also recorded no overlay state or trace rows
because the harness read the remote packet output while sitecustomize wrote to
the container's default `/work/out`.

Consume `DIRECTOR_REPAIR.json`. First bind the retained container activation
artifacts, then localize request 790 at the first target-verification state:
draft tokens, tree ancestry mask, accepted indices, request ownership, corpus
updates, and cleanup. Admit only the smallest defect repair within the
request-local verified-trunk mechanism. Run the smallest candidate-only
sustained-load discriminator needed to reach request 790. A repaired full
endpoint is allowed only after activation is positively proved and the
discriminator is exact. Preserve every original identity, target-verification
invariant, workload byte, fallback, comparator, and decision gate; replay no
control or settled arm.
