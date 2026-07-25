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

## Resources

Spend `$0`, use local CPU analysis only, write at most 1 GiB, and finish by
`2026-07-25T03:15:00Z`. Record the causal result and exact proposed arm in
project-local artifacts; provider mutation is forbidden.
