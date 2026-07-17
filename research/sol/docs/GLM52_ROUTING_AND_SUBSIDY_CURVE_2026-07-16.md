# GLM-5.2 OpenRouter provider-data subsidy/MRR curve — 2026-07-16

## Decision

The earlier high-traffic estimate at 25% above the cheapest provider was not defensible. Correctly interpreted public pricing puts a service whose COGS is `1.25 × cheapest` at approximately the **10th-cheapest of 29 endpoints**, not third-cheapest. It would not be among the most expensive, but price rank alone does not imply material traffic.

The best public-data curve is a scenario band conditioned on provider fitness:

- At the median incumbent-equivalent fitness, zero-subsidy MRR is only **$18k** and no price reaches $833k MRR.
- At the 75th percentile, zero-subsidy MRR is **$212k** and the price-only revenue maximum is about **$582k MRR**.
- At the 90th percentile, zero-subsidy MRR is **$650k**. Reaching $833k MRR requires approximately **$350k/month** subsidy in the central model; sensitivity to the unpublished routing-price scalar is approximately **$282k–$381k/month**.
- A StreamLake- or Alibaba-equivalent endpoint can exceed $833k MRR without subsidy, but a new provider cannot be assumed to inherit that eligibility, quality, cache locality, capacity, or customer affinity.

Do not precommit a subsidy. Launch at COGS, clear onboarding and Auto Exacto evaluation, measure eligible-request share, and price-test only after the endpoint is in a known-good tier. The commercial prerequisite for $10M ARR is roughly top-decile provider fitness, not merely a lower list price.

## Critical pricing correction

OpenRouter's endpoint `pricing.prompt`, `pricing.completion`, and `pricing.input_cache_read` fields are already the discounted prices displayed to customers. The endpoint object also contains a `discount` field and undiscounted values in `pricing_json`. Applying `discount` to `pricing.*` a second time understated StreamLake and NovitaAI prices by another 31–32%.

That double-discount error caused the superseded third-cheapest conclusion and the $3.456M cheapest-price market estimate. Correct values are:

| Metric | Correct result |
|---|---:|
| Cheapest common-workload endpoint | Inceptron |
| Cheapest common-workload price | $0.3443/M total tokens |
| Assumed COGS, `1.25 × cheapest` | $0.4303/M |
| Hypothetical price rank at COGS | **#10 of 29** |
| Whole current market at cheapest prices | **$4.930M/month** |

The rendered provider table was the decisive cross-check: for example, NovitaAI displays approximately $0.955/M input after its discount, not the approximately $0.651/M produced by applying the discount twice.

## Evidence contract

- Question: what monthly gross endpoint billings follow from each subsidy level if COGS is 25% above the cheapest GLM-5.2 endpoint, after checking the routing assumption against all useful public OpenRouter provider data?
- Traffic scope: seven complete UTC days, 2026-07-09 through 2026-07-15.
- Provider scope: all 28 public standard endpoints returned on 2026-07-16; hypothetical entrant is the 29th.
- Revenue definition: customer-facing endpoint billings before provider payout terms, OpenRouter fees, fixed fleet cost, taxes, and overhead.
- COGS assumption: the entrant's input, cache-read, and output COGS schedule is proportional to the cheapest endpoint schedule and is 1.25 times it.
- Quality assumption: each scenario holds non-price provider fitness constant while displayed prices change proportionally.
- Falsifier: measured entrant share after reaching normal uptime and a known-good Auto Exacto tier falls outside the selected scenario or fails to respond approximately inverse-square to bounded price changes.

## Current traffic and workload economics

| Seven-day measurement | Value |
|---|---:|
| Requests | 69.991M |
| Prompt tokens | 3.230T |
| Cached prompt tokens | 2.709T |
| Completion tokens | 63.136B |
| Total tokens | 3.293T |
| Cached fraction of prompt | 83.85% |
| Tool calls | 41.332M |
| Tool calls per request | 0.591 |

At Inceptron's displayed schedule—$0.94/M uncached input, $0.17/M cache read, and $2.90/M output—the observed workload costs $1.134M/week, or **$4.930M/month**. The 25%-higher COGS schedule is $1.175/M input, $0.2125/M cache read, and $3.625/M output.

The workload is unusually sensitive to tool quality and cache placement. The five largest public apps are Hermes Agent, Claude Code, pi, OpenClaw, and Kilo Code; the weekly activity trace has 41.3M tool calls. Auto Exacto and sticky routing are therefore central, not edge cases.

## Provider-data cross-check

The table uses current already-discounted endpoint prices, the common seven-day cache/input/output mix, a repeated-sample median of the mutable public token-share summary, and one-week public performance/quality data. Shares varied during retrieval; values are representative rather than contractual.

| Provider | Common $/M | Token share | Throughput | Tool error | Cache hit | GPQA | Tau-bench |
|---|---:|---:|---:|---:|---:|---:|---:|
| StreamLake | $0.354 | 29.9% | 32.6 tps | 1.19% | 89.3% | 89.7% | 73.7% |
| Alibaba Cloud Int. | $0.474 | 27.7% | 34.9 tps | 0.66% | 86.3% | 89.9% | 71.0% |
| Z.ai | $0.520 | 10.6% | 33.1 tps | 0.29% | 90.6% | 88.6% | 74.9% |
| NovitaAI | $0.355 | 9.1% | 23.8 tps | 0.48% | 88.1% | 89.4% | 74.2% |
| SiliconFlow | $0.498 | 8.1% | 33.8 tps | 0.16% | 68.9% | 86.5% | 72.8% |
| Fireworks | $0.421 | 3.4% | 51.1 tps | 1.31% | 78.0% | 88.0% | 68.9% |
| AtlasCloud | $0.468 | 2.9% | 29.3 tps | 0.43% | 66.7% | 89.9% | 73.9% |
| Weights & Biases | $0.518 | 2.2% | 88.0 tps | 1.61% | 58.5% | 88.2% | 72.6% |
| Inceptron | **$0.344** | **0.43%** | 15.3 tps | 2.22% | 63.9% | 85.5% | 72.0% |
| DeepInfra | $0.353 | ~0.003% | ~13 tps | high | ~0% | 77.4% | 59.8% |

Three checks reject a price-only absolute-share forecast:

1. StreamLake and NovitaAI have almost identical prices but recently differed by roughly 3–9× in token share, depending on the public snapshot.
2. Alibaba is about 34% more expensive than StreamLake on the common mix yet has comparable traffic.
3. The cheapest endpoint, Inceptron, has only about 0.4% share; the second-cheapest, DeepInfra, has almost none.

Across all 28 endpoints in the aligned sample, Spearman correlations with token share were approximately:

| Public signal | Spearman correlation with share |
|---|---:|
| Common-workload price | -0.33 |
| Throughput | -0.01 |
| Tool-call error rate | **-0.61** |
| Cache-hit rate | **+0.58** |
| GPQA provider benchmark | **+0.72** |

These are observational and window-mismatched, not causal coefficients. They nevertheless agree with OpenRouter's documented two-stage behavior: request eligibility and quality/performance tiering determine who receives the opportunity; inverse-square price weighting acts within the surviving candidate set. Cross-sectional throughput alone is weak because current throughput, workload assignment, capacity, and tier are endogenous.

## Empirical fitness model

OpenRouter documents inverse-square price weighting but does not publish the request-specific price scalar or the size of the lowest-cost candidate set. Instead of assigning the entrant the current leader's share, infer each incumbent's residual provider fitness.

For incumbent `i`:

```text
a_i = observed_share_i × (price_i / cheapest_price)²
```

For an entrant with fitness `a` at displayed price ratio `r` relative to the cheapest schedule:

```text
entrant_share(a, r) = (a / r²) / (1 + a / r²)
                    = a / (r² + a)

MRR(a, r)           = $4.930003M × r × entrant_share(a, r)
subsidy(a, r)       = $4.930003M × (1.25 - r) × entrant_share(a, r)
```

The residual absorbs everything price does not explain: Auto Exacto tier, tool correctness, benchmark quality, feature/context eligibility, capacity, cache locality, customer/provider pinning, uptime, geography, and unobserved commercial effects.

Because OpenRouter does not expose its exact request-price scalar, residual percentiles were calculated four ways—cache-aware common blend, uncached input/output blend, input-only, and output-only—and the median percentile used. The inferred scenario fitness values are:

| Scenario | Fitness `a` | Interpretation |
|---|---:|---|
| P25 | 0.00173 | weak/poorly eligible incumbent equivalent |
| P50 | 0.00450 | median public endpoint equivalent |
| P75 | 0.05570 | strong incumbent equivalent |
| P90 | 0.18417 | top-tier incumbent equivalent |

The P75 and P90 estimates moved by roughly 10% or less across the four price proxies. That is much smaller than the provider-to-provider and snapshot share variation.

## Full optimized subsidy/MRR curve

For each monthly subsidy cap, the model selects the highest revenue price at or below the cap. MRR values are gross billings. Once a scenario reaches its mathematical revenue maximum, additional subsidy is economically destructive and is not spent.

| Monthly subsidy cap | P25 MRR | P50 MRR | P75 MRR | P90 MRR |
|---:|---:|---:|---:|---:|
| $0 | $7k | $18k | $212k | **$650k** |
| $25k | $17k | $32k | $233k | $669k |
| $50k | $22k | $40k | $251k | $686k |
| $100k | $29k | $51k | $280k | $718k |
| $250k | $44k | $74k | $343k | $793k |
| $500k | $59k | $98k | $413k | **$883k** |
| $750k | $70k | $115k | $463k | $945k |
| $1.0M | $78k | $128k | $499k | $989k |
| $1.5M | $90k | $146k | $548k | $1.041M |
| $2.0M | $97k | $158k | $574k | $1.058M |

### Detailed P90 curve

| Subsidy cap | Price / cheapest | Modeled share | MRR |
|---:|---:|---:|---:|
| $0 | 1.250 | 10.54% | $650k |
| $100k | 1.097 | 13.27% | $718k |
| $250k | 0.951 | 16.93% | $793k |
| $500k | 0.798 | 22.44% | $883k |
| $750k | 0.697 | 27.50% | $945k |
| $1.0M | 0.622 | 32.28% | $989k |
| $1.5M | 0.512 | 41.24% | $1.041M |
| $2.0M | 0.432 | 49.62% | $1.058M |

The P90 revenue maximum is approximately **$1.058M MRR** near 50% modeled share and `r ≈ 0.429`, requiring about $2.02M/month subsidy. That is a mathematical ceiling, not a sensible acquisition strategy.

## $10M ARR target

The target is $833,333 MRR.

| Fitness scenario | Can price alone reach target? | Minimum modeled subsidy |
|---|---|---:|
| P25 | No; maximum ~$102k MRR | — |
| P50 | No; maximum ~$165k MRR | — |
| P75 | No; maximum ~$582k MRR | — |
| P90 | Yes | **~$350k/month** |
| StreamLake-equivalent | Already above target at COGS | $0 |
| Alibaba-equivalent | Already above target at COGS | $0 |

For P90, the central solution lists near `0.880 × cheapest`, captures about 19.2% modeled traffic, bills $833k/month, and subsidizes approximately $350k/month. Recomputing with each of the four public price proxies gives approximately:

- displayed price: `0.858–0.934 × cheapest`;
- traffic share: `18.1–19.7%`;
- subsidy: **$282k–$381k/month**.

This does not mean $350k buys the target. It means that **after** independently earning top-decile provider fitness, a price subsidy of that order could close the remaining modeled gap. At P75 or below, aggressive discounting cannot create $10M ARR because lower revenue per token overwhelms additional share.

## Launch implication

1. List initially at COGS: $1.175/M input, $0.2125/M cache read, and $3.625/M output. This is around rank #10, not an extreme price.
2. Clear OpenRouter's published minimum-data gates: at least 100 general requests in 30 minutes and 200 tool-call requests in two hours; maintain at least 95% uptime.
3. Target top-decile public quality/eligibility signals before paying for traffic: benchmark parity, low tool errors, full parameter/context support, strong cache locality, enough capacity, and clean streaming behavior.
4. Measure eligible-request share separately for tool and non-tool traffic. Aggregate token share is not the routing probability.
5. Run small price steps only after reaching a known-good tier. Fit the endpoint's own elasticity and replace this cross-sectional scenario model.
6. Do not proceed to a six-figure monthly subsidy if the endpoint remains below P90-equivalent fitness. Spend on service quality, cache locality, capacity, and cost reduction first.

## Public-data inventory used

| Dataset | Use |
|---|---|
| [Rendered GLM-5.2 model page](https://openrouter.ai/z-ai/glm-5.2) | Display-price validation, provider table, effective-price description, performance, benchmarks, apps, activity |
| [Endpoint detail API](https://openrouter.ai/api/frontend/v1/stats/endpoint?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | Already-discounted prices, endpoint IDs, capabilities, context, quantization, current stats, status counters |
| [Public endpoints API](https://openrouter.ai/api/v1/models/z-ai/glm-5.2-20260616/endpoints) | Independent price, capability, uptime, and context cross-check |
| [Effective pricing and token shares](https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | Mutable provider shares, cache rates, effective input/output prices, price history |
| [Activity](https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | Requests, token mix, cache volume, tool calls, market size |
| [Throughput](https://openrouter.ai/api/frontend/v1/stats/throughput-comparison?permaslug=z-ai%2Fglm-5.2-20260616&timeRange=1w) | One-week provider throughput |
| [Latency](https://openrouter.ai/api/frontend/v1/stats/latency-comparison?permaslug=z-ai%2Fglm-5.2-20260616&timeRange=1w) and [E2E latency](https://openrouter.ai/api/frontend/v1/stats/latency-e2e-comparison?permaslug=z-ai%2Fglm-5.2-20260616&timeRange=1w) | One-week latency checks |
| [Tool errors](https://openrouter.ai/api/frontend/v1/stats/tool-call-error-rate?permaslug=z-ai%2Fglm-5.2-20260616&timeRange=1w) and [structured-output errors](https://openrouter.ai/api/frontend/v1/stats/structured-output-error-rate?permaslug=z-ai%2Fglm-5.2-20260616&timeRange=1w) | Auto Exacto/service-quality checks |
| [Cache hit rate](https://openrouter.ai/api/frontend/v1/stats/cache-hit-rate-comparison?permaslug=z-ai%2Fglm-5.2-20260616&timeRange=1w) | Sticky-routing and workload-affinity check |
| [Provider benchmarks](https://openrouter.ai/api/frontend/v1/stats/benchmark-scores?permaslug=z-ai%2Fglm-5.2-20260616) | GPQA and tau-bench provider quality |
| [Recent uptime](https://openrouter.ai/api/frontend/v1/stats/uptime-recent?permaslug=z-ai%2Fglm-5.2-20260616) | Three-day endpoint uptime history |
| [Top apps](https://openrouter.ai/api/frontend/v1/stats/top-apps-for-model?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) and [locations](https://openrouter.ai/api/frontend/v1/stats/top-colos-for-model?permaslug=z-ai%2Fglm-5.2-20260616) | Workload and geographic character |
| [Provider routing docs](https://openrouter.ai/docs/guides/routing/provider-selection) | Stable-candidate filtering and inverse-square weighting |
| [Provider integration docs](https://openrouter.ai/docs/guides/community/for-providers) | Uptime, evaluation thresholds, Auto Exacto tiers and signals |
| [Prompt caching docs](https://openrouter.ai/docs/guides/best-practices/prompt-caching) | Provider sticky-routing behavior |

Reproduction: [`../evidence/glm52_openrouter_subsidy_curve.py`](../evidence/glm52_openrouter_subsidy_curve.py).

## Source-code boundary and limitations

- OpenRouter's public GitHub organization currently exposes the docs source, SDKs, examples, and a deprecated inference runner. I did not find the production provider-routing backend among its public repositories. The open docs source confirms the documented algorithm but does not reveal candidate-set construction or the request-specific price scalar. If a separate production repository exists, it should be added to this evidence set.
- The effective-pricing summary is visibly mutable and its provider-token window is not specified in the JSON. Repeated direct calls and the rendered page produced materially different shares on the same day. Sampling reduces point noise but does not create a longitudinal causal dataset.
- Price, share, cache hit, quality, and performance windows differ. The residual model is a sensitivity model, not a causal forecast.
- Provider token share differs from request share and from eligible-request probability. Providers may receive different prompt/output lengths and cache patterns.
- The model assumes proportional price changes across all three SKUs and constant traffic volume. Real users can pin providers, request explicit sorting, filter by features/privacy/quantization/context, or change demand in response to price.
- Provider payout terms and OpenRouter fees are not public in these datasets, so MRR is gross customer billing, not net revenue or gross profit.
