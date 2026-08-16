# Gemma 4 agent persistent-KV replay

## Question

How much exact prefill work could a provider avoid on realistic multi-turn tool
traffic by retaining content-addressed KV state and routing repeated prefixes to
the owning replica?

## Why this matters

InferCept, CachedAttention and CacheWise report large gains on tool,
multi-turn, and coding-agent workloads. Those results do not transfer to this
campaign and do not improve a fresh-prompt Artificial Analysis benchmark. The
lab's synthetic exact mix currently records only 12.6958% cached prompt tokens.
A trace replay can cheaply determine whether product traffic contains enough
additional exact-prefix reuse to justify a persistent-KV service.

Use `$experiment-run`. The first phase is a zero-GPU replay; the paid
continuation below is admitted only because that replay passed its preregistered
plausibility gate.

## Scope and immediate experiment

- Use the local TauBench request/tool assets and any already-captured
  campaign-safe multi-turn traces. Do not ingest credentials, private prompts,
  or customer data.
- Construct cumulative turn requests exactly as an OpenAI-compatible provider
  receives them: each later request contains the full prior conversation and
  tool results.
- Tokenize with the exact Gemma 4 tokenizer revision from `CAMPAIGN.md`.
- Compare:
  1. no inter-request persistence;
  2. current in-process radix/prefix behavior under arbitrary routing;
  3. content-addressed exact-prefix affinity plus reuse-aware eviction;
  4. an ideal unlimited exact-KV upper bound.
- Report fresh, reusable, resident-hit, evicted and reloaded tokens by session
  and turn; estimate prefill compute, KV capacity, host/storage traffic, and
  committed-price cost under explicit assumptions.
- Separate same-tenant/session reuse from cross-tenant reuse. The production
  candidate must default to tenant-isolated fingerprints.
- If scope-matched avoidable prefill work is at least 25% of total endpoint
  compute or the derived cost reduction is at least 20%, produce one small
  implementation experiment for the next paid cycle. Otherwise close the
  workload route without building a distributed cache.

Do not claim end-to-end savings from token ratios alone. Calibrate the replay
with the lab's measured prefill/decode split and report the transfer range.

## Contract

- Causal hypothesis: agent/tool turns repeatedly resend long exact prefixes
  that are currently recomputed or evicted because routing and cache lifetime
  ignore session locality.
- Competing explanation: OpenRouter request diversity and load balancing leave
  too little exact reusable prefix for a 20% endpoint result.
- Maximum spend: `$0`.
- Compute: local CPU only, at most eight wall hours and four CPU-hours.
- Deadline: `2026-07-24T09:00:00Z`.
- Storage: at most 2 GiB.
- Artifacts: input/source manifest, replay script, per-turn token ledger,
  capacity/eviction sensitivity, calibrated cost range, and one decision
  terminal.

## Paid endpoint continuation — 2026-07-24

The exact-token replay measured `481,820 / 600,735` repeated-prefix tokens
(`80.2051%`). At 16 GiB, session affinity retained all of them without reloads;
the calibrated endpoint opportunity is 25.26–48.12%. This passes the original
gate and changes the next question from plausibility to measured realization.

Consume `DIRECTOR_GPU_BINDING.json` and claim only retained bench
`h200-sync-linear-e00vhh6h29fj68x91g`. Use its exact checkpoint and pinned
SGLang image. Run one matched pair over the same 165 sessions and 905 cumulative
requests in the same interleaved turn-round order:

1. Control: explicitly disable or reset cross-turn persistent reuse while
   preserving ordinary within-request semantics.
2. Candidate: tenant-isolated content-addressed exact-prefix persistence,
   session affinity, LRU admission, and a fixed 16-GiB KV budget.

Persist raw cache hit, miss, eviction, reload, admitted-token and byte counters;
non-overlapping prefill, decode, and complete-request timing; HBM residency;
request ownership; output token IDs; and tool-call payloads. Require identical
deterministic outputs and tool-call behavior. Attribute savings to avoided
prefill work rather than token ratios, and report the matched endpoint cost
delta. The safe synthetic tool-result limitation remains explicit.

Repair one ordinary runtime/API/cache-control integration defect in place on
the retained bench. Do not introduce a distributed cache, cross-tenant reuse,
new tokenizer/workload, cache-size sweep, routing sweep, broad quality suite,
or another provider allocation. A complete exact pair decides the route.

Continuation maximum spend: `$12`; one H200 claim; at most four provider hours;
science deadline `2026-07-24T09:45:00Z`; use the existing `10:30Z` lab watchdog.
