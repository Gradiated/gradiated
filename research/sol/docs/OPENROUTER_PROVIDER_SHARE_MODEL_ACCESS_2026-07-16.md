# OpenRouter provider-share model: source, data, and validation contract

Date: 2026-07-16  
Decision owner: Inference Foundry  
Scope: GLM-5.2 standard endpoints on OpenRouter; prediction of provider and
routed-variant token share under price and service changes

## Decision

We do **not** currently have OpenRouter's production provider-routing backend
source or enough historical route-decision data to claim an accurate global
provider-share model.

We do have the official documented policy, public endpoint state, public
provider-token-share snapshots, and several short-window performance signals.
Those are sufficient to build a useful baseline and begin longitudinal
collection, but not to identify the global routing function. The missing
variables include the eligible request denominator, request-specific filters,
explicit user routing, tool-routing cohort, sticky-cache state, endpoint
capacity/rate limits, fallbacks, and some internal quality signals.

A 15-minute public collector is now running so this evidence gap stops growing.
It stores raw replayable snapshots under `.agents/runtime/`, not in git.

## Evidence contract

**Question.** Can a model forecast each GLM-5.2 provider variant's token share
after a price or reliability change accurately enough to make subsidy and
capacity decisions?

**Primary hypothesis.** A cohort-aware replay of the documented inverse-square
router, combined with observed endpoint state and an empirical residual model,
can forecast out-of-time daily shares within the acceptance bounds below.

**Falsifier.** The model fails if hidden request mix, capacity, user pinning, or
internal quality tiers cause persistent out-of-time error above the bounds. In
that case no amount of fitting to public aggregate shares makes it decision
grade; request-level or cohort-level OpenRouter telemetry is required.

**Decision consequence.** Subsidy curves must use prediction intervals and may
not be presented as expected provider traffic until the model passes a
chronological holdout. The current subsidy curve remains a scenario analysis.

**Evidence labels.** Public API values are measured OpenRouter aggregates.
Routing policy statements are vendor-documented. Candidate-set behavior not
specified in the docs is unknown. Any inferred traffic response is labeled
inferred until validated against held-out route data.

## Source-code audit

The OpenRouter GitHub organization was enumerated with `gh repo list
OpenRouterTeam --limit 100`, then its public code was searched for the routing
phrases `lowest-cost candidates`, `inverse square`, `Auto Exacto`, and related
endpoint-selection symbols. The current public organization contains docs,
SDKs, examples, skills, and the deprecated runner, but no identifiable
production routing service. Searches resolve the policy wording to the
documentation source, not a backend implementation. Shipped frontend bundles
expose the public statistics calls but not the server-side router; their source
maps are not publicly readable.

Conclusion: production routing code was not found in the current public
[OpenRouter GitHub organization](https://github.com/OpenRouterTeam). The policy
source is public in the [official docs repository](https://github.com/OpenRouterTeam/docs),
but that is not the production router. If OpenRouter has published the backend
under another owner or repository, its exact URL is required.

## What the official policy tells us

For ordinary default routing, OpenRouter says it prioritizes stable providers,
selects among the lowest-cost candidates with inverse-square price weighting,
and retains other providers as fallbacks. It does not publicly define the exact
lowest-cost candidate boundary or every price scalar used for a particular
request. Eligibility also depends on request parameters, context/output limits,
privacy, region, quantization, and user-supplied provider preferences.
[Official provider-routing documentation](https://openrouter.ai/docs/guides/routing/provider-selection)

Tool requests use Auto Exacto, whose tiers incorporate throughput, tool-call
success, and OpenRouter's internal benchmarks. New endpoint sample thresholds
and uptime thresholds also change routing status. Prompt caching can introduce
provider affinity using account/model/conversation or `session_id`, so requests
are not independent draws from a static price distribution.
[Official prompt-caching documentation](https://openrouter.ai/docs/guides/best-practices/prompt-caching)

This means source alone would improve deterministic replay but would still not
determine aggregate share without the request cohort and dynamic state inputs.

## Public historical data found

The model page calls public `/api/frontend/v1/stats/` endpoints for effective
pricing/provider token totals, endpoint state, activity, throughput, latency,
end-to-end latency, tool errors, structured-output errors, cache hit rate,
benchmark scores, and recent uptime.

Observed limits on 2026-07-16:

| Surface | Public history observed | Use |
|---|---:|---|
| effective pricing/provider totals | eight daily chart points; current mutable provider totals | share target, effective price |
| endpoint state | current state and 30-minute summary | price, capability, health, load proxy |
| performance/error/cache charts | 84 hourly points for `3d`; eight daily points for `1w` | dynamic endpoint features |
| model activity | 31 daily model-level points | market volume, not provider denominator |
| recent uptime | three days | availability feature |
| benchmark scores | current lookback aggregate | internal-quality proxy only |

The effective-pricing response does not state the aggregation window for its
provider token totals, does not provide a provider-share time series, and
ignores attempted arbitrary historical start/end parameters. Repeated calls can
return different current totals. Therefore the public interface cannot provide
a retrospective causal backtest today.

## Why a normal API key is not the missing key

OpenRouter's authenticated analytics query API supports dimensions including
provider, but the official skill and API contract describe analytics for the
authenticated account or workspace. It would be useful after we generate
representative traffic or become a provider, and it can preserve our own route
and fallback outcomes. It does not appear to expose global competitor route
decisions or global historical provider shares.
[Official analytics API](https://openrouter.ai/docs/api/api-reference/betaanalytics/query-analytics-data)

Therefore an ordinary management/API key is helpful but not sufficient. The
valuable access is one of:

1. OpenRouter provider-dashboard/partner telemetry for our endpoint and the
   market candidate set;
2. a global metrics export or internal analytics endpoint;
3. production router source plus historical route-state and request-cohort
   aggregates.

OpenRouter's provider documentation says accepted providers receive dashboard
access and operational visibility, so provider onboarding is the most plausible
route to additional first-party data.
[Official provider integration guide](https://openrouter.ai/docs/guides/community/for-providers)

## Exact data request to OpenRouter

Ask for 30–90 days at hourly resolution for GLM-5.2, with no prompts or user
identifiers. The minimum privacy-preserving aggregate is:

- request cohort: tool/non-tool, default router versus explicit `sort`/`order`/
  `only`, privacy/ZDR/region, quantization, context bucket, requested output
  bucket, cache/sticky-session cohort;
- eligible requests and tokens by cohort and endpoint, including candidate-set
  count or IDs;
- first endpoint selected, endpoint ultimately served, attempts, fallbacks, and
  terminal outcome;
- prompt, cached-prompt, and output token totals by endpoint and cohort;
- displayed and request-effective prices, discounts, and endpoint revisions;
- endpoint uptime/health tier, capacity/rate-limit state, latency, throughput,
  request count, and derankable errors;
- Auto Exacto tier and the historical values/timestamps of each routing signal;
- timestamps for policy, threshold, or experiment changes.

The critical field is the eligible-request denominator. Chosen-provider totals
alone cannot distinguish “the router disliked this provider” from “few requests
were eligible for it.” If only aggregated data is available, each row should be
`hour × model × request cohort × endpoint` and include both eligible and served
counts/tokens.

For code access, request the production router repository and the version or
commit deployed during the telemetry window. Secrets and private business logic
can be omitted if OpenRouter supplies a deterministic route-decision replay API
that returns candidate tiers, weights, and fallback order for a sanitized
request/state record.

## Model architecture once data exists

Keep the model interpretable and causal enough for counterfactual pricing:

1. **Cohort/eligibility layer.** Split default non-tool, Auto Exacto tool,
   explicit routing, and sticky-cache traffic. Reconstruct each endpoint's
   eligibility from request features and capabilities.
2. **Policy replay.** Apply the source-defined health/tier logic and
   inverse-square weighting to eligible low-cost candidates. Preserve the full
   fallback order.
3. **Dynamic state layer.** Estimate capacity, rate-limit, health, and fallback
   probabilities from lagged endpoint telemetry. Do not let future chart values
   leak into a prediction.
4. **Residual calibration.** Fit a regularized hierarchical model to the gap
   between replayed and observed shares. Provider effects must shrink toward
   zero; a black-box provider identity coefficient must not be allowed to hide a
   broken policy reconstruction.
5. **Aggregation.** Weight cohort predictions by forecast request and token mix,
   then report provider and routed-variant request share, token share, revenue,
   and uncertainty separately.

Required baselines are previous-share persistence, price-only inverse-square,
and a share-of-cheapest heuristic. A sophisticated model is useful only if it
beats all three on a future period.

## Validation gate

Use walk-forward chronological validation across at least four weeks and include
at least one price, endpoint-entry, or reliability regime change. Never use a
random row split over overlapping rolling-window snapshots.

Preregistered decision-grade targets:

- top-10 routed-variant daily token-share mean absolute error at most 1.5
  percentage points;
- daily total-variation distance across all variants at most 8 percentage
  points;
- weighted provider-rank Spearman correlation at least 0.90;
- 80% prediction intervals with 70–90% empirical coverage;
- counterfactual share error within 10% relative on held-out price or endpoint
  changes for providers with at least 2% realized share.

These are acceptance targets, not current results. If the counterfactual target
cannot be tested from natural changes, run a bounded live price experiment after
provider onboarding. Until that gate passes, use the model for scenario ranges,
not a single subsidy-to-MRR forecast.

## Implemented collection

The tested collector is at
`research/sol/evidence/openrouter_share_model/collector.py`. It runs every 15
minutes, uses no credential, preserves routed variants, stores checksummed raw
responses, and continues through failures of optional public charts. Its schema
and operations are documented in the adjacent evidence README.

