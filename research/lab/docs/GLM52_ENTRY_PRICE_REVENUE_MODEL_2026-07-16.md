# GLM-5.2 OpenRouter entry-price revenue model — 2026-07-16

> **Accuracy amendment:** the original tables below treated all traffic as
> inverse-square price weighted. OpenRouter's provider documentation establishes
> that requests containing tools are reordered by Auto Exacto using quality and
> performance signals instead. GLM-5.2 records 0.5905 tool-call events per
> request, so that assumption materially overstates subsidy elasticity. Do not
> use the original curve for a subsidy commitment. The corrected cohort-aware
> model and trust-ramp decision are in
> [`GLM52_PROVIDER_TRUST_RAMP_AND_MODEL_ACCURACY_2026-07-16.md`](GLM52_PROVIDER_TRUST_RAMP_AND_MODEL_ACCURACY_2026-07-16.md).

## Decision

We can model a useful steady-state revenue range now, but 99% uptime alone does
not make provider share predictable to a narrow interval. OpenRouter's
documented normal-routing threshold is 95%; going from 95% to 99% avoids
fallback exposure but does not determine tool quality, benchmark tier, cache
affinity, capability eligibility, capacity, provider pinning, or the unpublished
lowest-cost candidate boundary.

For planning, use the P25 case as conservative, P50 as base, P75 as strong
execution, and P90 only after telemetry demonstrates top-decile provider
fitness. Do not use P90 merely because expected uptime is 99%.

At the previously assumed production COGS of `1.25 ×` the cheapest listed
schedule, listing at COGS produces the following steady-state scenarios:

| Stable-provider fitness | Token share | Gross endpoint billings/month | Requests/month | Required average output tok/s |
|---|---:|---:|---:|---:|
| P25 conservative | 0.15% | $9k | 0.45M | 153 |
| P50 base | 0.44% | **$27k** | 1.33M | 457 |
| P75 strong | 2.58% | **$159k** | 7.86M | 2,696 |
| P90 top-decile | 10.88% | $670k | 33.11M | 11,357 |

These are gross customer-facing billings, not net provider receipts. OpenRouter
provider payout/fee terms are not present in the public data. At a displayed
price equal to assumed inference COGS, gross margin before platform terms is
zero by construction.

## Price curve

The current cheapest listed proportional schedule is approximately `$0.94/M`
uncached input, `$0.17/M` cache read, and `$2.90/M` output. The common GLM-5.2
workload blend is `$0.344/M` total tokens because 83.85% of prompt tokens are
cached and output is a small fraction of total tokens.

| Price ratio | Common blend | Rank after entry | P25 share / MRR | P50 share / MRR | P75 share / MRR | P90 share / MRR |
|---:|---:|---:|---:|---:|---:|---:|
| 0.75× | $0.258/M | #1 | 0.41% / $15k | 1.21% / $45k | 6.86% / $254k | 25.32% / $936k |
| 1.00× | $0.344/M | #1 | 0.23% / $11k | 0.68% / $34k | 3.98% / $196k | 16.02% / $790k |
| **1.25×** | **$0.430/M** | **#10** | **0.15% / $9k** | **0.44% / $27k** | **2.58% / $159k** | **10.88% / $670k** |
| 1.50× | $0.516/M | #15 | 0.10% / $8k | 0.30% / $23k | 1.81% / $134k | 7.81% / $578k |
| 2.00× | $0.689/M | #24 | 0.06% / $6k | 0.17% / $17k | 1.03% / $101k | 4.55% / $449k |

The price-only model can show lower gross billings at a higher price because the
documented inverse-square traffic response removes share faster than price rises.
That response applies only after eligibility and quality tiering. The table is
not evidence that an unqualified new endpoint can buy P75/P90 traffic by
undercutting.

## Evidence contract

- Question: what steady-state provider share and gross monthly endpoint billings
  correspond to a proportional GLM-5.2 displayed price schedule if the endpoint
  maintains at least 99% uptime?
- Data: seven complete UTC days, 2026-07-09 through 2026-07-15; 304.3M modeled
  monthly requests; 14.32T total monthly tokens; 24 currently stable incumbent
  endpoints with aligned price and provider-share data.
- Stock controls: prior-share persistence, equal-fitness inverse-square price
  weighting, and the earlier all-endpoint residual model.
- Hypothesis: the empirical latent-fitness distribution of currently stable
  endpoints provides a useful entrant planning prior after threshold ramp.
- Falsifier: our endpoint's measured stable eligible-request share lies outside
  the selected scenario, or its own bounded price response is materially
  inconsistent with inverse-square weighting.
- Non-scope: initial endpoint ramp, capacity caps, semantic/quality failure,
  explicit provider routing, demand growth, provider payout terms, and net profit.

## Method

For each stable incumbent `i`, infer residual routing fitness under each of four
plausible request-price proxies:

```text
fitness_i = observed_token_share_i × (provider_price_i / cheapest_price)²
```

For an entrant with scenario fitness `a` and proportional price ratio `r`:

```text
entrant_share = a / (r² + a)
gross billings = entrant_share × monthly workload billings at price r
```

Fitness absorbs everything not explained by displayed price. P10/P25/P50/P75/
P90 are medians of the respective fitness quantiles across cache-aware blend,
uncached blend, input-only, and output-only price proxies. Only endpoints marked
normal/stable in the live endpoint API are included. Twelve mutable public share
summaries were sampled and provider medians used.

The exact reproduction is
[`../evidence/openrouter_share_model/entry_revenue_model.py`](../evidence/openrouter_share_model/entry_revenue_model.py),
and the captured result is
[`../evidence/openrouter_share_model/GLM52_ENTRY_REVENUE_MODEL_2026-07-16.json`](../evidence/openrouter_share_model/GLM52_ENTRY_REVENUE_MODEL_2026-07-16.json).

## Interpretation and next calibration

The defensible pre-launch financial case at `1.25×` is:

- conservative underwriting: about **$9k gross MRR**;
- base case: about **$27k gross MRR**;
- strong qualified service: about **$159k gross MRR**;
- upside, not underwriting: about **$670k gross MRR**.

This wide range is not primarily an uptime uncertainty. It is eligibility and
provider-fitness uncertainty. After onboarding, the shortest route to a narrow
forecast is to measure eligible requests separately for tool/non-tool traffic,
clear the benchmark and tool-success tiers, let cache affinity warm, prove the
capacity required by the target share, and run two or three bounded price steps.
Those observations replace the cross-sectional fitness prior with our own
elasticity and route-opportunity measurements.

## Sources

| Source | Retrieved | Evidence type | Use |
|---|---|---|---|
| [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) | 2026-07-16 | vendor-documented | inverse-square weighting, request filters, fallback behavior |
| [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers) | 2026-07-16 | vendor-documented | stability and sampling thresholds, Auto Exacto factors |
| [GLM-5.2 endpoint state](https://openrouter.ai/api/frontend/v1/stats/endpoint?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | measured public aggregate | prices, endpoint status, capabilities |
| [GLM-5.2 provider totals](https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | measured mutable public aggregate | provider token-share target |
| [GLM-5.2 activity](https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | measured public aggregate | market volume and workload mix |
| [OpenRouter prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching) | 2026-07-16 | vendor-documented | provider affinity and cache caveat |
