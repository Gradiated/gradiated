# OpenRouter provider token-share model: validation and operating design

Date: 2026-07-16

## Decision

Do not use price and trailing uptime alone as a precise pre-launch revenue
forecast. They are a useful prior, but they miss provider eligibility, request
constraints, tool-routing tier, capacity, commercial allocation, and average
tokens per routed request. On the current public panel, that model is not close
to the preregistered accuracy gate.

Use a two-stage model instead:

1. **Pre-launch prior:** public candidate set, documented inverse-square price
   routing, current health gating, request-cohort eligibility, and deliberately
   broad provider-fitness scenarios.
2. **Post-launch nowcast:** anchor on the endpoint's observed eligible/routed
   request counts, success rate, and tokens per request. Apply price
   counterfactuals around that anchor only after a controlled price step has
   estimated elasticity for the endpoint's actual cohorts.

The post-launch nowcast passes its gate. It is materially more accurate, but it
is not yet a validated causal model of a future price change.

## Evidence

The reproducible panel contains 30 high-volume, standard, multi-provider models,
314 aligned endpoint rows, and 65 providers. GLM-5.2 was excluded from fitting
and retained as the primary model holdout. Features are all public: displayed
price, recent uptime, endpoint health errors and rate limits, tool-error signal,
cache rate, throughput, capabilities, endpoint age, and the endpoint's current
request-count window. Shares are public provider token shares.

Leave-one-model-out results:

| Model | Mean total-variation error | Mean endpoint-share MAE | Mean rank correlation |
|---|---:|---:|---:|
| Equal share | 56.5% | 10.80 pp | 0.000 |
| Documented inverse-square price | 52.4% | 10.01 pp | 0.329 |
| Uptime-gated inverse-square | 48.5% | 9.28 pp | 0.434 |
| Learned price + uptime | 50.7% | 9.68 pp | 0.497 |
| Full public pre-launch features | 44.8% | 8.56 pp | 0.556 |
| Full pre-launch + Auto Exacto benchmarks | **44.5%** | **8.50 pp** | 0.552 |
| Provider-history model | 42.9% | 8.19 pp | 0.629 |
| Post-launch request nowcast | **12.5%** | **2.40 pp** | **0.897** |

On the strict unseen-provider test across 20 providers and 204 provider-model
observations, uptime-gated inverse-square has 7.75 pp provider-share MAE, the
full pre-launch model has 7.37 pp, and the post-launch nowcast has 2.37 pp. This
test does not allow a learned reputation effect for the held-out provider.

GLM-5.2 holdout total-variation error is 61.3% for uptime-gated inverse-square,
55.8% for the full pre-launch model, 17.4% for raw current request share, and
18.3% for the learned request nowcast. The post-launch model therefore passes
its <=20% GLM holdout gate and improves mean panel error by 74% versus the
uptime-gated baseline. It does not correctly identify GLM's largest provider in
this single snapshot, so launch revenue must still be reported as a range.

## Correct model structure

OpenRouter documents the non-tool default as: remove providers suffering a
significant outage in the last 30 seconds, select among the lowest-cost stable
candidates with probability proportional to inverse price squared, and retain
the rest as fallbacks. Tool requests additionally pass through Auto Exacto,
which reorders providers by throughput, tool success, and benchmark signals;
within a tier, the original price order remains.

The operational model should therefore be cohort-compositional rather than one
global regression:

```text
eligible[p,c,t] = capability constraints × policy constraints × live health
route_weight[p,c,t] = eligible × exacto_tier_weight × price[p,c,t]^-2
request_share[p,t] = sum_c demand[c,t] × normalized(route_weight[p,c,t])
token_share[p,t] = request_share × endpoint_tokens_per_request / market_tokens
```

Trailing uptime is not a smooth demand coefficient. A provider at 98.5% and one
at 99.5% can route similarly while both are currently healthy; a fresh outage
can remove one immediately. Model uptime with live eligibility/circuit-breaker
state plus an incident process, then multiply by success and fallback rates.

The panel's observational price coefficients are approximately -1.2 for the
non-tool mixture and -0.69 for the tool mixture. They are attenuated by hidden
eligibility and tier assignment and must not replace the documented -2 rule in
a causal counterfactual. Estimate endpoint-specific effective elasticity from
price steps after onboarding.

The GLM-5.2 page now exposes provider-level GPQA-Diamond and Tau-Bench Verified
Airline scores. These are direct Auto Exacto tier inputs and explain a material
piece of the previously hidden tool-cohort fitness. They must be added as
time-varying provider features rather than treated as one model-wide quality
score. The verification targets and current peer distribution are recorded in
`GLM52_AUTO_EXACTO_VERIFICATION_2026-07-16.md`.

Measured incremental validation is modest: benchmark features improve mean
leave-one-model-out TV by 0.72%, unseen-provider TV by 3.64%, and GLM-5.2 TV by
4.27% (55.81% to 53.43%). They improve GLM provider ordering but do not make
absolute pre-launch share accurate. Once current request counts are included,
benchmark features slightly worsen mean panel TV, so the production nowcast
retains the simpler request-telemetry specification.

## Data collection and calibration

- The GLM-5.2 collector records public shares, endpoint request counts, prices,
  health, uptime, performance, and raw source responses every 15 minutes.
- The multi-model collector records a 30-model panel every six hours. This
  creates event history for price changes, outages, endpoint additions, and
  recoveries instead of repeatedly fitting one cross-section.
- `route_probe.py` can measure realized provider selection for matched non-tool
  and tool requests. It requires `OPENROUTER_API_KEY`, explicit `--execute`, and
  a spend cap; prompts and responses are not stored. No key is currently
  available, so no paid probes were run.
- After onboarding, ingest the provider's own attempted, eligible, accepted,
  failed, fallback, prompt-token, completion-token, cache-token, and tool-cohort
  counters at one-minute resolution. This is the highest-value missing data.

For causal price calibration, keep serving software and capacity fixed and run
small, reversible price steps around the launch price. Each step must span the
same demand mix and include pre/post recovery periods. Estimate changes in
routed-request odds separately for non-tool and tool cohorts, rejecting windows
with health incidents, capacity saturation, endpoint-set changes, or Exacto
tier changes. A synthetic route-probe panel is a diagnostic control, not a
substitute for production demand.

## Revenue-model contract

Before launch, report p10/p25/p50/p75/p90 revenue scenarios; do not publish a
single precise MRR. During launch, replace the prior with observed request-share
and token-length anchors after 30 minutes, then refresh at two hours and daily.
Only use a price-response curve after at least two clean price transitions have
the expected sign and a held-out transition predicts token share within the
chosen error gate.

Artifacts:

- `research/sol/evidence/openrouter_share_model/OPENROUTER_PROVIDER_PANEL_2026-07-16.json`
- `research/sol/evidence/openrouter_share_model/OPENROUTER_PROVIDER_PANEL_VALIDATION_2026-07-16.json`
- `research/sol/evidence/openrouter_share_model/panel_model.py`
- `research/sol/evidence/openrouter_share_model/collector.py`
- `research/sol/evidence/openrouter_share_model/panel_collector.py`
- `research/sol/evidence/openrouter_share_model/route_probe.py`

Authoritative routing references: [provider selection](https://openrouter.ai/docs/guides/routing/provider-selection),
[provider integration and Auto Exacto](https://openrouter.ai/docs/guides/community/for-providers), and
[generation metadata](https://openrouter.ai/docs/api/api-reference/generations/get-generation).
