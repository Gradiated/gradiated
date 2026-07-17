# GLM-5.2 $10M ARR subsidy scenario — 2026-07-16

> **Superseded and numerically invalid for planning.** The analysis applied OpenRouter's endpoint discount twice even though `pricing.*` already contains the displayed discounted price, and it assigned a new endpoint an unsupported incumbent routing weight. Use the corrected [provider-data subsidy/MRR curve](GLM52_ROUTING_AND_SUBSIDY_CURVE_2026-07-16.md). The $28,717/month result must not be used.

## Decision

If serving COGS is uniformly 25% above the cheapest GLM-5.2 endpoint, the constrained minimum-subsidy solution under the 30-day routing calibration is **$28,717/month**. List at **1.20836 times the cheapest price**, approximately 3.33% below COGS but still 20.84% above the cheapest provider. The inverse-square formula then predicts 19.95% traffic share and $833,333/month of provider billings.

Use **$50k/month** as the initial direct-subsidy envelope and recompute from measured share. This optimum depends on the recent 30-day cheapest-provider share of 36.4%. Under the instantaneous 23.1% share snapshot, no displayed price reaches $10M ARR through price weighting alone: the mathematical maximum is $9.97M ARR and requires approximately **$1.33M/month** subsidy. Do not pursue that price-war branch; performance and Auto Exacto rank must provide the missing routing weight.

## Evidence contract

- Question: with COGS 25% above the cheapest provider, what monthly subsidy is required to generate $10M annualized gross provider billings on OpenRouter?
- Revenue definition: actual endpoint gross billings, not the undiscounted market value of served tokens and not net provider payout or profit.
- Scope: GLM-5.2 standard traffic, current OpenRouter prices and shares retrieved 2026-07-16T10:47:51Z, and the seven complete UTC traffic days 2026-07-09 through 2026-07-15.
- Assumption: “25% above cheapest” means all-in variable COGS for the observed uncached-input, cache-read, and output mix equals 1.25 times the cheapest endpoint's user price for the same mix.
- Non-scope: OpenRouter contractual payout adjustments, working capital, fixed fleet overcapacity, engineering, support, taxes, and other operating expense.
- Falsifier: materially different provider onboarding terms, routing behavior, traffic mix, or inability to enter normal/Auto Exacto top-tier routing.

## Current inputs

The current cheapest healthy endpoint was StreamLake after its displayed discount:

- uncached input: approximately $0.6521/M;
- output: approximately $2.0495/M;
- cache read: approximately $0.1211/M.

Applied to the measured weekly mix—521.535B uncached prompt tokens, 2.709T cached prompt tokens, and 63.136B output tokens—the full market is approximately **$797,546/week**, or **$3.456M/month** at that endpoint's price.

The revenue target is:

```text
$10,000,000 / 12 = $833,333/month
```

At cheapest-price parity, this requires 24.11% of total traffic. At a listed price 25% above cheapest, it requires 19.29% of traffic.

## Routing behavior

OpenRouter documents this default behavior for stable non-tool endpoints:

1. prioritize endpoints without significant recent outages;
2. select among the lowest-cost candidates with probability weighted by inverse price squared;
3. retain remaining providers as fallbacks.

Therefore a provider priced at 1.25 times the cheapest receives this relative price weight:

```text
1 / 1.25² = 0.64
```

Tool-calling requests are different. Auto Exacto reorders providers using throughput, tool-call success, and internal benchmark data, with good, insufficient-data, and deprioritized tiers. Price alone therefore cannot predict the full GLM-5.2 share.

## Constrained optimum

Let:

- `P` be the cheapest workload-weighted price;
- `r` be our displayed price divided by `P`;
- `M = $3.456032M/month`, the whole current market billed at `P`;
- `R = $0.833333M/month`, the $10M ARR target;
- `K` be the incumbent routing-weight pool when the cheapest provider's weight is normalized to one.

The 30-day cheapest-provider share was 36.4%, so `K = 1 / 0.364 = 2.747253`. After adding our endpoint:

```text
share(r)   = 1 / (K × r² + 1)
revenue(r) = M × r / (K × r² + 1)
subsidy(r) = R × (1.25 / r - 1), when revenue(r) = R
```

Solving `revenue(r) = R` gives two roots. The higher-price root minimizes subsidy:

```text
r*             = 1.20835984
traffic share  = 19.95468%
monthly revenue = $833,333
monthly COGS    = $862,050
monthly subsidy = $28,717
```

At current SKU prices, the optimized displayed prices are approximately $0.7880/M uncached input, $2.4766/M output, and $0.1463/M cache read. Corresponding COGS at 1.25 times cheapest is approximately $0.8152/M, $2.5619/M, and $0.1514/M.

The lower-price root also reaches the revenue target but captures much more traffic at a far larger loss, so it is dominated for a minimum-subsidy objective.

## Subsidy scenarios

### 1. Performance-assisted price parity — comparison point

List at the cheapest user price. If base COGS is 1.25 times that price, the required user discount from cost is 20% because `1.25 × (1 - 0.20) = 1.00`.

```text
monthly revenue       = $833,333
monthly serving COGS  = $833,333 × 1.25 = $1,041,667
monthly subsidy       = $208,333
```

This requires approximately 24.1% traffic share. It is not optimal under the 30-day calibration because the higher price of 1.20836 times cheapest reaches the revenue target with only $28,717/month subsidy.

### 2. Remain 25% above cheapest

There is no per-token subsidy if listed price equals COGS. However, inverse-square weighting gives only 64% of the cheapest provider's price weight. Calibrating the candidate pool to the cheapest provider's instantaneous 23.1% share gives approximately 12.9% share after adding the new endpoint, or only **$6.68M annualized gross billings**.

Reaching $10M ARR at that price requires 19.3% share, so a sufficiently strong Auto Exacto/performance ranking could close the gap without a price subsidy. This is possible but not guaranteed.

### 3. Price-only acquisition — reject

Normalize the current cheapest provider's routing weight to one. Its observed 23.12% share implies approximately 4.325 total incumbent weight units. For a new endpoint at price ratio `r`:

```text
new share = 1 / (4.325 × r² + 1)
monthly revenue = $3.456M × r × new share
```

Revenue is maximized near `r = 0.481`, roughly 52% below the cheapest provider. The model then gives 50% traffic share and approximately $831k/month revenue, or $9.97M ARR—within snapshot noise of the target.

At that volume:

```text
monthly serving COGS = $3.456M × 50% × 1.25 = $2.160M
monthly revenue      ≈ $0.831M
monthly subsidy      ≈ $1.329M
```

This result is not a forecast. It is a price-only bound showing that inverse-square routing can make aggressive subsidy self-defeating: lowering price increases share but also lowers revenue per token. The recent 30-day leading share was materially higher than the instantaneous share and would imply a much smaller subsidy. This instability is another reason to acquire share through performance rather than a price war.

## Recommendation and kill rule

- Start at approximately **1.208 times the cheapest workload-weighted price** with a **$50k/month direct subsidy envelope**.
- Maintain at least 95% uptime; target materially higher for a credible commercial endpoint.
- Optimize throughput, streaming behavior, tool-call correctness, and benchmark parity to enter Auto Exacto's good tier.
- Re-estimate `K` from the endpoint's measured eligible-request share and re-solve the quadratic weekly; do not assume the 30-day calibration persists.
- Ramp capacity only as measured traffic share grows.
- If a healthy, feature-complete, top-quality endpoint cannot sustain approximately 20% share near the optimized price, stop the subsidy ramp and improve the service. Do not cross into the approximately $1.3M/month price-only regime.

## Sources

| Source | Retrieval | Evidence type |
|---|---|---|
| [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) | 2026-07-16 | Official current documentation: inverse-square default price weighting, outage priority, explicit sorting |
| [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers) | 2026-07-16 | Official current documentation: discounts, capacity, uptime thresholds, performance metrics, Auto Exacto tiers |
| [OpenRouter provider application](https://openrouter.ai/providers/apply) | 2026-07-16 | Official current description: provider payments and performance-based routing |
| [GLM-5.2 endpoint prices](https://openrouter.ai/api/v1/models/z-ai/glm-5.2-20260616/endpoints) | 2026-07-16 | Official live API |
| [GLM-5.2 activity](https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | Official live traffic API |
| [GLM-5.2 effective pricing and shares](https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | Official live API; provider share window is mutable |

## Limitations

- OpenRouter does not publish the exact size of the “lowest-cost candidates” set or a complete formula combining standard routing with Auto Exacto.
- Request-specific context, output allowance, features, quantization filters, region, data policy, capacity, and failures change the eligible provider pool.
- GLM-5.2 is heavily agentic; the public weekly trace records 41.3M tool calls, but not a directly usable count of requests subjected to Auto Exacto.
- The live provider-share snapshot and 30-day display differ materially. The exact subsidy cannot be known before an onboarded endpoint accumulates real routing data.
