# Prefix-affinity batching economics

## Question

Can one deterministic cache-affinity admission and replica-routing policy
increase reusable prompt work on the exact c32 Gemma workload enough to reduce
whole-request cost, while preserving every request, token, model operation,
and a usable background-agent completion bound?

## Why it matters

The locked qualified result is `0.625149101968745 s/request` and the target is
`0.500119281574996 s/request`. The exact workload contains `117,728` fresh and
`17,120` cached prompt tokens per 32-request window. GPU-local metadata fusion
has only a `0.038202%` conservative bound, so this independent lane changes the
workload/runtime scheduling boundary and exploits the campaign's explicit
permission to trade latency for sustainable cost. It must first prove that
the exact requests contain reusable prefix identity; assumed cache hits are
not evidence.

## Authoritative inputs

- Exact workload:
  `../gemma4_causal_parallel_offset_head/inputs/qualified_c32_workload.json`,
  SHA-256
  `7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d`.
- Exact model: `google/gemma-4-31B-it`, revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Locked denominator and target: `CAMPAIGN.md`.
- The direct scheduler component is independent and must not be claimed or
  treated as a cache-affinity result.

## Scope

Within 90 wall-clock minutes:

1. Reconstruct exact byte/token prefix identities and the maximum reusable
   prefix work available under reordering alone. If the workload has no
   additional repeated prefixes, return that typed negative immediately.
2. Select one policy only: deterministic prefix-affinity admission plus
   replica routing under a bounded waiting window. Preserve request contents,
   output length, concurrency accounting, target semantics, and all compulsory
   fresh-prefill/decode work.
3. Implement a reproducible trace or discrete-event consumer using the exact
   workload and the closest measured prompt/decode service accounting. Compare
   with FIFO at identical offered work and report cache-hit tokens, batch
   occupancy, service-time/cost bound, p50/p95 completion time, queue memory,
   and the break-even arrival/reuse rate.
4. Derive both an oracle upper bound and a realizable conservative bound
   against `0.625149101968745 s/request`. Do not credit cache reuse that the
   exact identity graph cannot produce.
5. Persist `PREFIX_AFFINITY_BATCHING_OFFLINE_TERMINAL.json` with direct hashes,
   the policy source, assumptions labeled measured/derived/inferred, a complete
   falsifier, and one exact-runtime consumer command or typed `none`.

Use no GPU, SSH, provider endpoint, checkpoint shard, image pull, model
generation, quality proxy, generic scheduler sweep, or synthetic extra
prefixes. This project may inspect the exact workload read-only.

## Result that changes the portfolio

A positive result must show scope-matched reusable prefix identity and a
conservative cost reduction after queueing and memory overhead, with a bounded
completion-time tradeoff. That earns a later runtime discriminator. A missing
identity opportunity or non-positive complete bound closes this policy and
redirects the independent lane away from cache-affinity scheduling.
