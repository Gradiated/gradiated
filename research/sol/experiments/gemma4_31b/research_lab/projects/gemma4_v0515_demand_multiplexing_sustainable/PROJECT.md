# v0.5.15 sustainable demand multiplexing

## Question

Can one production-valid multiplexing geometry overlap independent copies or
disjoint views of the exact Gemma 4 workload strongly enough to remove the
single-stream arrival-cost floor while preserving every request byte,
per-request semantics, queue limits, and the official v0.5.15 native-NGRAM
execution path?

## Why this matters

The B200 source/fit lane closed without GPU use because its `$5.15/hour`
planning rate requires at most `0.4026911068 s/request` at 90% sustainable
utilization, while the bound single-stream arrival span alone imposes
`0.6937319716 s/request`. No accelerator speed can repair that denominator.
The same terminal proves that at least `1.7227397374x` aggregate demand density
or a committed B200 rate at most `$2.9894242806/hour` is required.

The campaign explicitly asks for background concurrency, batching, saturation
economics, and active reconsideration of latency-for-cost tradeoffs. This
project asks whether independent production demand can be pooled without
changing the canonical single-stream endpoint or fabricating a throughput
claim.

## Bound evidence

Mechanically verify `DIRECTOR_BINDING.json` before analysis. Treat:

- the B200 arrival-floor terminal as derived exact-workload economics;
- the v0.5.15 source and launch identities as content-addressed;
- H100/H200 results as non-transferable until their active measurements close;
- any multiplexed throughput before a GPU run as analytical only.

## Scope and immediate result

1. Reconstruct the exact request arrivals, token denominator, current endpoint
   gates, and raw/90%-sustainable cost ceilings for H200, H100, and B200.
2. Distinguish invalid global arrival compression from valid aggregation of
   independent tenant streams. Preserve each stream's request bytes,
   within-stream order, semantic reference, and release times relative to that
   stream's origin. Do not mutate the active H200 or H100 contracts.
3. Trace official v0.5.15 admission, max-running-request, CUDA-graph batch,
   queue, and global NGRAM-corpus behavior. Explicitly address whether repeated
   prompts or cross-stream corpus writes would create an unrepresentative
   acceptance advantage.
4. Nominate at most one deterministic, content-addressed multiplexing packet:
   stream count, phase offsets, request selection, exact aggregate denominator,
   queue/release gates, and the smallest later GPU falsifier. The packet must
   reach at least `1.7227397374x` demand density for the B200 hypothesis while
   remaining meaningful on H100/H200.
5. Return the packet or typed `none`. Do not claim a GPU, create a provider
   resource, run either active endpoint, or transfer measured throughput across
   hardware.

## Decision gate

Nominate only if the geometry is a plausible production demand pool rather
than a faster synthetic clock; preserves exact per-request semantics and
within-stream releases; avoids or explicitly falsifies duplicate-prompt corpus
bias; has a queue-peak gate of at most 30 and final queue zero; and yields one
cheap executable comparison against a scope-matched single-stream control.

Otherwise return typed `none` and identify which workload, semantics, queue,
or representativeness invariant blocks multiplexing.

## Director reopening — official stock v0.5.15 path

The original typed-none result closed multiplexing only on the semantically
rejected native-NGRAM endpoint. The independently verified request-217 causal
terminal now proves that decode-attention mode did not change the active
Triton target-verification path and returns no further exact NGRAM repair.

Reopen this same scientific question for one materially distinct execution:
disable NGRAM and every speculative mode, retain the official v0.5.15 image,
runtime commit, exact checkpoint, request bytes, semantic rows, and validated
two-stream geometry, and compare the bound 139-request stock single-stream
control with the disjoint two-stream candidate. This is demand pooling, not a
semantic repair or NGRAM replay.

The candidate must preserve normalized semantics, request bytes, within-stream
order, release timing, zero failures, peak queue at most 30, and final queue
zero while producing a service-time improvement larger than measured timing
noise. Only then may the owner run the existing 759-request two-stream
endpoint. Accept only at no more than `$0.14` per million total tokens. The
complete execution contract is `DIRECTOR_STOCK_MULTIPLEX_BINDING.json`.

Reuse retained H200
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; release it by `08:25Z`. Never replay
the consumed 791-request NGRAM endpoint or request-217 discriminator.

## Budget and artifacts

- Provider/GPU spend: `$0`; no GPU claim.
- Wall clock: 60 minutes.
- Local compute: at most 2 CPU-hours.
- Storage: at most 2 GiB project-local.
- Required artifacts: verified binding, exact arrival/economic derivation,
  scheduler/corpus causal map, one execution packet or typed `none`,
  `RESEARCH_LOG.md`, and updated `STATUS.json`.

The reopening adds at most 30 H200 minutes, 45 wall minutes, `$4.00` cumulative
project authority, and 3 GiB of additional project-local artifacts.
