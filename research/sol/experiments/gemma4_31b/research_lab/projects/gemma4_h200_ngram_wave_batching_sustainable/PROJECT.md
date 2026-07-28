# Sustainable NGRAM wave admission

## Question

Can background-agent arrivals be buffered into deterministic 32-request waves
so the qualified NGRAM c32 geometry remains stable and meets the fixed
`1.439656551 request/s` economic load without an unbounded queue?

## Evidence

The exact NGRAM endpoint is quality-qualified: AR and NGRAM both scored
GPQA-Diamond `55/198` and TauBench `10/165`; NGRAM used 18 fewer completion
tokens. Its matched c32 arm completed 32 requests in `20.004771263 s`, or
`1.599618390 request/s`.

Two independent 1,036-request rolling-admission streams instead underwent the
same late phase change. They were stable for roughly 700 requests, then
per-request latency approached `22-24 s` and client backlog ended at
`6.43-8.15 s`. Resetting the process-global NGRAM corpus at request 650 did
not move the transition: reset cost `14.7 ms`, the online trie held only
hundreds of nodes, and all corpus lookup/update time was negligible. Corpus
lifetime is closed.

The remaining measured interaction is admission geometry. Continuous
replacement mixes fresh 4,214-token prefill with an already full decode set.
For background traffic, the same fixed arrival rate can instead accumulate 32
arrivals over `22.227523626 s`, then dispatch one c32 wave. The qualified c32
service time leaves about `2.22 s` headroom per wave. This trades bounded
waiting latency for the already measured efficient batch shape without
changing model, NGRAM, request, or output semantics.

## Experiment

Consume and hash-check `DIRECTOR_BINDING.json`. On retained bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`, stop only the retained instrumented
state-aging container and launch a clean stock server from the hash-bound
image and `ngram-launch.json`. Use the proven detached remote-owner path and
keep ordinary launch, consumer, and retrieval repairs in this project and
claim.

Freeze one client policy before the paid call:

- preserve all 1,036 original arrival timestamps and request bodies;
- buffer arrivals outside the server;
- dispatch each consecutive group of 32 simultaneously when its 32nd member
  arrives;
- do not dispatch the next wave until both its release time has arrived and
  the preceding wave has completed;
- dispatch the final 12-request tail once the fixed arrival trace ends.

Run this single wave-admission arm once. It is not a c32 replay: it must sustain
32 full waves plus the tail across the complete workload and report each
wave's release drift, server time, completion span, upstream queue depth and
age, GPU utilization/power, cache realization, failures, output IDs or
normalized served semantics, finish reason, usage, and total-token economics.
Compare against the persisted rolling stream and the qualified c32 terminal;
run no contemporaneous stock arm.

Preserve exact FP8 weights, FP8-E5M2 page-1 KV, TP1, context 5000,
max-running 32, dynamic chunking 2048, NGRAM settings, unique suffixes, and
the fixed `1.439656551 request/s` offered load. Do not replay quality, the
four/ten-row verifier, c32, the separate 10K view, corpus reset, attention
tiles, or variable compaction. Run no wave-size, arrival-rate, concurrency,
backend, chunk, or draft sweep.

## Decision

Retain wave admission if all 1,036 requests complete with exact served
semantics and usage, no wave misses the next `22.227523626 s` release by more
than one arrival spacing, final upstream backlog is zero, failures/reloads are
zero, and planning cost at `$3.25/H200-hour` is no more than `$0.14/M` total
tokens. Report mean/p95/max completion time including buffer wait; latency is
secondary, but it must remain bounded and operationally usable.

A growing cross-wave release drift, nonzero final backlog, semantic mismatch,
or cost above target closes this fixed wave policy. Preserve the result so the
next director can decide between a lower sustainable placement rate and a
source-level prefill/decode scheduling intervention.

## Resources

- Priority: `7200`
- Researcher profile: `execution`
- Authorized cumulative spend: `$6`
- Bench: retained `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`
- Compute: at most 90 claimed H200-minutes
- Wall clock: complete and release by `2026-07-24T16:45:00Z`
- Storage: at most 10 GiB of new project-local artifacts
- Provider mutation: forbidden

