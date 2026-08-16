# NGRAM cross-request state aging discriminator

## Question

Does the pinned NGRAM worker's process-global corpus lifetime cause the sharp
service-time transition after roughly 700 requests, and can one bounded
corpus-lifetime policy preserve exact target-verified outputs and stable
service at the campaign's fixed `1.439656551 request/s` arrival rate?

## Why this is the next bottleneck

The exact NGRAM endpoint is already quality-qualified: fresh AR and NGRAM
captures both scored GPQA-Diamond `55/198` and TauBench `10/165`, while NGRAM
used 18 fewer completion tokens. Its canonical c32 latency is
`0.625149101968745 s/request`.

The 720-second production stream is a valid negative for the original capacity
estimate, not a general NGRAM reject. All `1036/1036` requests completed, but
requests 0-699 held about `2.31 s` mean latency before a sharp phase change:
later 100-request bins reached about `22-24 s` mean latency and the client
backlog ended at `8.148 s`. The server queue gauge remained zero. Over the
same run, SWA eviction reached `4,820,278` tokens and HBM grew by about
`5.1 GiB`.

The pinned source supplies a concrete causal candidate. `NGRAMWorker` owns one
process-global `NgramCorpus`, calls `batch_put` after every verification
forward, and resets it only through `clear_cache_pool`; finished requests erase
their match state but not learned corpus contents. The stock capacity is
`10,000,000`. This can increase scheduler-side lookup/update cost even when
the GPU-side request queue remains empty. Prefix/SWA churn is the competing
explanation and must be measured, not conflated with corpus lifetime.

## Experiment

Consume and hash-check `DIRECTOR_BINDING.json`. First use the persisted
`1036` request rows, metrics, pinned Python source, and the image's exact
`cpp_ngram` and SWA-cache source to explain the phase transition. Bind counters
for corpus size/capacity, `synchronize`, `batch_get`, and `batch_put` time;
match-state count; NGRAM accept length; scheduler/target-forward time; SWA
evictions and hit tokens; KV occupancy; HBM; power; completed rate; server
queue; and client queue. Do not treat elapsed time alone as localization.

Freeze exactly one source-justified bounded-lifetime intervention before the
paid launch. It may roll over or compact only the learned cross-request NGRAM
corpus at a deterministic bound derived from the persisted transition and
source contract. It must not clear or resize the prefix/SWA/KV cache at the
same boundary; that separation is the discriminator. Keep ordinary source,
API, instrumentation, launch, and retrieval repairs inside this project.

Claim warm bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` once. Reuse its
resident checkpoint, pinned image, runtime/JIT caches, and the existing
detached-owner path. Run one instrumented candidate trajectory over the frozen
arrival schedule and request bytes, using the persisted stock trajectory as
the control; do not run a second stock stream. Preserve the exact FP8 model,
FP8-E5M2 page-1 KV, TP1, context 5000, max-running 32, dynamic chunking,
NGRAM draft settings, and `1.439656551 request/s` rate.

The candidate must reach beyond the stock transition, persist per-100-request
windows, and compare every response's target token IDs or normalized served
semantics, finish reason, and usage against the persisted control. A short
source/counter discriminator may terminate the arm early if it falsifies
corpus aging. Do not replay GPQA, TauBench, the four-row verifier, the ten-row
suite, c32, attention tiles, variable compaction, or the separate 10K view.
Run no arrival-rate, corpus-capacity, draft-depth, backend, or concurrency
sweep.

## Decision

Retain a bounded corpus lifetime only if the measured corpus operation time
explains the stock phase change, the intervention causes an immediate and
durable recovery without a simultaneous prefix-cache reset, all served
semantics remain exact, all arrivals complete, and final client queue is
non-positive in trend and no greater than one arrival spacing
(`0.6946101133 s`). Report sustainable total-token economics at the campaign's
`$3.25/H200-hour` planning rate.

If corpus time does not grow with the transition, or the intervention does not
restore stable service, close this corpus-lifetime hypothesis. Preserve the
counter evidence so the next director can decide whether the measured
alternative is SWA/KV cache churn, allocator/runtime growth, or a lower
sustainable arrival placement. Do not silently switch mechanisms or open a
support project.

## Resources

- Priority: `7100`
- Researcher profile: `deep`
- Authorized cumulative spend: `$8`
- Bench: retained `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`
- Compute: at most 125 claimed H200-minutes
- Wall clock: finish and release by `2026-07-24T16:45:00Z`
- Storage: at most 12 GiB of new project-local artifacts
- Provider mutation: forbidden
