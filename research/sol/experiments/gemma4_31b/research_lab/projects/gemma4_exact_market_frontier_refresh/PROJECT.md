# Gemma 4 exact-model market frontier refresh

## Question

Does the current public serving frontier for the exact Gemma 4 31B
instruction model materially change the campaign's locked economic target or
identify a production placement/runtime lead that should outrank the current
unmeasured H100, B200, and MI355X candidates?

This is a zero-provider-spend market/economics discriminator. It is
independent of the active conditional-depth physical mechanism.

## Bound scope

- Campaign model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Campaign workload: text-only, default non-reasoning traffic around 4,214
  prompt and 358 output tokens per request at c32, including the durable
  535-token shared-prefix accounting.
- Qualified service evidence: `0.625149101968745 s/request`.
- Locked service target at the current planning mapping:
  `0.500119281574996 s/request`.
- The shared accelerator-price inventory is authoritative for hardware
  planning and passed its seven-day freshness check on this director turn:
  `research/factory/data/gpu_prices.json`, refreshed
  `2026-07-22T21:42:00Z`. Do not duplicate its H100, H200, B200, MI355X, or
  L40S price searches.

An exact-model claim must distinguish Gemma 4 31B from Gemma 3, Gemma 2,
larger/smaller Gemma variants, aliases without checkpoint evidence, and
quantized or modified representations. Record uncertainty rather than
silently treating them as equivalent.

## Immediate evidence path

Use source-backed, reproducible web research. Start with the current
Artificial Analysis provider-comparison page for the exact model when one
exists, then verify decision-bearing provider prices and model identities
against first-party provider documentation.

For every usable provider observation, preserve:

- page URL, retrieval time, observation/benchmark recency, model name and
  exactness evidence;
- cache-hit, input, and output prices separately;
- the published blended mix, especially Artificial Analysis's 7:2:1
  cache-input-output convention when used;
- output tokens/second, time to first token, total latency, test workload,
  endpoint features, and any rate or batching qualification;
- whether the price is public retail, promotional, committed, or inferred.

Normalize each sufficiently scoped observation to both:

1. the publisher's stated blend, reproduced exactly; and
2. the campaign's 4,214-input/358-output request with 535 cached-prefix
   tokens, showing the arithmetic and dollars per million total tokens.

Compare the result with the campaign target without transferring throughput
across unmatched hardware, runtime, precision, workload, or model identities.
If a public endpoint is cheaper, treat it as a competitive target or provider
lead—not evidence that a self-hosted accelerator will match its throughput.
If public data are absent or incomparable, preserve that uncertainty.

## Terminal

Write `EXACT_MODEL_MARKET_FRONTIER_REFRESH.json` as exactly one of:

- `market_target_revision_candidate`: current exact-model evidence supports a
  different normalized competitive target or a concrete production
  placement/runtime lead, with identities, source dates, citations, and
  arithmetic sufficient for director review; or
- `typed_none`: no current exact-model observation is sufficiently scoped to
  revise the locked target or placement ranking, with the strongest available
  evidence and mismatch reasons preserved.

A search-result list, generic GPU-price survey, unmatched Gemma benchmark, or
uncited price table is not a terminal. Do not edit `CAMPAIGN.md`; the director
owns any target revision after reviewing the artifact.

## Budgets

- Wall clock: 90 minutes.
- Compute: at most 4 local CPU-hours; zero accelerator compute.
- Storage: at most 1 GiB of new durable artifacts.
- Provider spend: `$0.00`.
- Provider login, contact, mutation, purchasing, and GPU claims are
  forbidden.
