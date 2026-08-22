# OpenRouter Kimi K3 traffic and revenue per Rubin rack

Date: 2026-07-28
Decision: replace the generic Artificial Analysis token blend with measured
OpenRouter Kimi K3 traffic when estimating OpenRouter revenue per rack.

## Bottom line

OpenRouter's public model-activity telemetry exposes prompt, cached-prompt, and
completion tokens. Across the latest seven complete UTC days, 2026-07-21
through 2026-07-27, Kimi K3 traffic was:

| Token category | Seven-day tokens | Share of billed tokens |
|---|---:|---:|
| Cached input | 1,151,094,988,541 | 91.77% |
| Uncached input | 88,441,216,256 | 7.05% |
| Output | 14,832,127,489 | 1.18% |
| Total | 1,254,368,332,286 | 100.00% |

This is approximately **77.61 cached input : 5.96 uncached input : 1 output**,
not Artificial Analysis' generic 7:2:1 comparison blend. Average request
geometry was about 76,435 cached input, 5,873 uncached input, and 985 output
tokens.

At K3's stated $0.30/M cached-input, $3/M uncached-input, and $15/M output
prices, the measured blend is **$0.664/M total billed tokens**. The latest seven
complete days imply:

- 179.2B total billed tokens/day;
- 2.12B output tokens/day, or 24,524 average output tokens/s;
- $119,019/day and **$43.44M/year** of annualized customer billings across the
  entire current OpenRouter K3 market.

OpenRouter's current effective-pricing snapshot reports a $0.609/M weighted
input price and $15.864/M weighted output price. Applying that current snapshot
to the trailing-seven-day traffic geometry gives $0.789/M total tokens,
$141,436/day, or **$51.62M/year**. This second figure is a current-price
scenario, not measured historical revenue, because provider mix and prices
changed during the seven-day window.

## What one rack could earn from OpenRouter

The current whole OpenRouter market averages only 24,524 output tokens/s.
Therefore, market share is presently a stronger revenue constraint than the
preliminary 35,000-60,000 output-token/s Rubin capacity estimate.

At K3's stated prices:

| Share of current OpenRouter K3 traffic | Gross annual billings | Output load | Utilization of a 47k output-t/s rack |
|---:|---:|---:|---:|
| 10% | $4.34M | 2,452 t/s | 5.2% |
| 25% | $10.86M | 6,131 t/s | 13.0% |
| 50% | $21.72M | 12,262 t/s | 26.1% |
| 75% | $32.58M | 18,393 t/s | 39.1% |
| 100% | $43.44M | 24,524 t/s | 52.2% |

These are customer billings, not provider net revenue. They exclude
OpenRouter's commercial terms, model-license payments, downtime, routing-share
dynamics, and price competition. A provider winning 25% share would generate
about $10.9M/year of gross billings but leave most of a 47k-output-t/s rack
idle unless the remaining capacity serves direct customers or other models.

The corresponding current-effective-price scenario is $5.16M, $12.91M,
$25.81M, $38.72M, and $51.62M at 10%, 25%, 50%, 75%, and 100% share.

## Theoretical capacity is not yet a physical benchmark

If a rack truly sustained 35k, 47k, or 60k aggregate output tokens/s at this
exact traffic geometry, full-utilization customer billings at stated prices
would be approximately $62.0M, $83.3M, or $106.3M per year. Those values are
economic extrapolations, not validated rack capacity:

```text
revenue per output token =
  77.608 cached inputs * $0.30/M
  + 5.963 uncached inputs * $3/M
  + 1 output * $15/M
  = $56.17 per million output-equivalent tokens
```

The transfer is especially uncertain because an average K3 request contains
about 82k prompt tokens and only 985 output tokens. Prefill, cache lookup,
cache transfer, KV residency, Kimi Delta Attention, concurrency, and memory
capacity can make a rack's output-token capacity on this workload materially
different from a short-context decode benchmark.

The next decisive measurement is therefore a K3 Rubin throughput curve that
replays the observed request geometry and separately reports:

- cached-prefix hit and transfer behavior;
- uncached prefill throughput;
- decode throughput and interactivity;
- KV/cache memory occupancy and eviction;
- aggregate accepted requests and output tokens/s.

## Infinite-demand sustainable capacity

For an infinite queued workload, use **70% sustained commercial utilization**
as the base planning assumption rather than 100% of benchmark peak. This is a
synthetic operational allowance, not a measured Rubin result:

| Allowance | Retained capacity |
|---|---:|
| Maintenance and equivalent availability | 95% |
| Scheduler, batching, and request-shape fragmentation | 90% |
| SLO and burst headroom | 85% |
| Combined | 72.7% |
| Underwriting assumption | 70% |

Applying 70% to the preliminary 47,000 output-token/s K3 rack estimate gives:

- **32,900 output tokens/s**;
- 2.55M cached-input tokens/s;
- 196k uncached-input tokens/s;
- **2.78M total billed tokens/s**, or 240.4B/day;
- about **33.4 requests/s**, or 2.89M requests/day, at the observed request
  geometry;
- $58.28M/year gross billings at stated prices, or $69.26M/year using the
  current OpenRouter effective-price snapshot.

The underlying 35k-60k peak-capacity uncertainty remains larger than the
operational allowance. At the same 70% sustained utilization, the resulting
range is:

| Preliminary peak | Sustained output | Total billed tokens/s | Requests/day | Stated-price billings |
|---:|---:|---:|---:|---:|
| 35k output t/s | 24.5k t/s | 2.07M | 2.15M | $43.40M/year |
| 47k output t/s | 32.9k t/s | 2.78M | 2.89M | $58.28M/year |
| 60k output t/s | 42.0k t/s | 3.55M | 3.68M | $74.40M/year |

This utilization haircut covers ordinary serving overhead, but it does not
validate the active-parameter throughput transfer. Exact K3 long-context
behavior could move the peak before the 70% factor is applied.

## Evidence and reproducibility

Evidence classes:

- **Measured:** OpenRouter daily request and token counters.
- **Provider-reported:** OpenRouter model prices and rolling effective prices.
- **Derived:** category shares, request geometry, annualized billings, and
  provider-share scenarios.
- **Inferred:** preliminary Rubin capacity and resulting utilization.

The public activity endpoint returns daily counters. `total_prompt_tokens`
includes cached prompt tokens, so uncached input is:

```text
uncached_input = total_prompt_tokens - total_native_tokens_cached
```

The analysis excludes 2026-07-28 because it was an incomplete UTC day at
retrieval. It includes the seven complete rows dated 2026-07-21 through
2026-07-27.

Reproduction URLs:

1. OpenRouter model activity:
   `https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=moonshotai%2Fkimi-k3-20260715&variant=standard`
2. OpenRouter effective pricing:
   `https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=moonshotai%2Fkimi-k3-20260715&variant=standard`
3. OpenRouter Kimi K3 page:
   `https://openrouter.ai/moonshotai/kimi-k3-20260715`
4. OpenRouter public model catalog:
   `https://openrouter.ai/api/v1/models`

Retrieved 2026-07-28. These undocumented frontend endpoints are public but may
change. OpenRouter describes effective pricing as a rolling average after
prompt caching; its public model catalog reports $0.30/M cache read, $3/M
input, and $15/M output pricing.

## Decision

For OpenRouter-specific rack economics:

- use the measured 91.77% cache / 7.05% uncached input / 1.18% output blend;
- under infinite demand, use **32.9k output tokens/s, 2.78M total billed
  tokens/s, and $58.3M/year** as the base sustainable-capacity scenario;
- retain a wide $43.4M-$74.4M/year stated-price range until exact-geometry K3
  Rubin throughput is measured;
- do not underwrite the 75%-80% operational-utilization case until sustained
  production traces establish its SLO and failure behavior.

Moonshot's commercial license threshold remains binding: Model-as-a-Service
aggregate revenue above $20M in a consecutive 12-month period requires a
separate agreement unless the provider qualifies for the stated exemption.
