# Vera Rubin NVL72 inference rack economics

Date: 2026-07-28
Decision: estimate the economic asset value of one Vera Rubin NVL72 rack under
Artificial Analysis' general-agentic token-price mix. For OpenRouter-specific
economics, this initial scenario is superseded by the measured-traffic analysis
in `OPENROUTER_KIMI_K3_RACK_REVENUE_2026-07-28.md`.

## Question and claim boundary

Question: what annual revenue capacity and three-year economic value could one
Vera Rubin NVL72 rack have when serving Kimi K3-like traffic?

This is a scenario model, not a measured Kimi K3 Rubin benchmark, demand
forecast, provider margin, financing quote, or company valuation. The result is
falsified by a scope-matched aggregate Kimi K3 Rubin measurement materially
outside the modeled 35,000-60,000 output-token/s interval, or by realized
utilization and blended price outside the selected scenario.

## Evidence

| Evidence | Value | Class |
|---|---:|---|
| Artificial Analysis general-agentic blend | 7 cache-hit input : 2 ordinary input : 1 output | Methodology |
| Kimi K3 prices | $0.30/M cache hit, $3/M input, $15/M output | Provider-reported, AA-observed |
| Kimi K3 AA blended price | $2.31/M total billed tokens | Derived by AA |
| Kimi K3 provider count | 9 | AA-observed, current snapshot |
| Kimi K3 provider speed | 31.5-168.2 output tokens/s/user | AA-measured endpoint performance; not aggregate capacity |
| Kimi K2.6 cheapest AA blended price | $0.59/M | AA-observed mature-market cross-check |
| NVIDIA Rubin efficiency point | about 700,000 Kimi-K2 tokens/s/MW | Vendor-reported |
| Assumed NVL72 rack power | 220 kW | Analyst-reported |
| Derived Kimi-K2 rack output capacity | about 154,000 output tokens/s | Derived: 700,000 x 0.22 |
| Kimi K2/K3 active parameters | 32B / 104B | Model-reported |
| Kimi K3 Rubin center estimate | 47,000 output tokens/s | Inferred: 154,000 x 32/104 |

The active-parameter scaling is deliberately simple. Kimi K3's native MXFP4,
Kimi Delta Attention, MoE communication, context geometry, speculative
decoding, batching, and Rubin software maturity can move the result materially.
The modeled interval is therefore 35,000-60,000 output tokens/s.

Artificial Analysis describes 7:2:1 as a comparison assumption. It is not an
observed traffic distribution. For economic normalization, output capacity is
divided by the 10% output share to produce "AA-equivalent billed token
capacity." Cached-token residency, cache writes, storage, request geometry, and
long-context decode may reduce physical capacity and are represented only by
the throughput range.

OpenRouter's actual Kimi K3 traffic is much more cache-heavy: the latest seven
complete days were 91.77% cached input, 7.05% uncached input, and 1.18% output.
That measured mix produces a $0.664/M blend at stated prices and an annualized
current OpenRouter billing pool of about $43.44M. See the companion report for
the provider-share and rack-utilization analysis. The AA-normalized figures
below remain a synthetic comparison scenario, not an OpenRouter revenue
forecast.

## Formula

```text
AA blended price = (7 * cache price + 2 * input price + output price) / 10
                 = (7 * 0.30 + 2 * 3.00 + 15.00) / 10
                 = $2.31/M

annual revenue =
  output_token_s / 0.10
  * 31,536,000 seconds/year
  * realized blended price / 1,000,000
  * commercial utilization
```

## Revenue capacity

At K3's current $2.31/M launch price:

| Aggregate output | Full-utilization revenue | Revenue at 70% utilization |
|---:|---:|---:|
| 35,000 tokens/s | $25.5M/year | $17.8M/year |
| 47,000 tokens/s | $34.2M/year | $24.0M/year |
| 60,000 tokens/s | $43.7M/year | $30.6M/year |

Cross-check: applying the Kimi-K2-derived 154,000 output tokens/s to the current
Kimi K2.6 market-floor price of $0.59/M gives $28.7M/year at full utilization
and $20.1M/year at 70%. This supports the order of magnitude but does not
validate K3 throughput.

## Three-year economic asset value

The DCF uses a 15% discount rate and excludes corporate SG&A, taxes, financing,
customer acquisition, model-license payments, and shared platform R&D.
Rack-level cash operating cost includes power, facility, maintenance, and
ordinary operations. Terminal values are residual hardware values.

| Case | Output t/s | Utilization | Year-1 realized blend | Annual price erosion | Cash opex | Three-year PV |
|---|---:|---:|---:|---:|---:|---:|
| Bear | 35,000 | 50% | $1.00/M | 40% | $1.50M | $5.8M |
| Base | 47,000 | 70% | $1.50/M | 30% | $1.75M | $23.8M |
| Bull | 60,000 | 85% | $2.31/M | 20% | $2.00M | $67.2M |

Against an estimated $7.8M-$9.1M purchase price, the bear case destroys capital,
the base case supports roughly $15M of NPV above a $9M purchase, and the bull
case is exceptionally valuable. The base economic asset value is therefore
about **$20M-$30M per rack**, conditional on demand and a realized first-year
price near $1.50/M. An uncontracted rack should be valued closer to hardware
replacement/resale value, not this capacity DCF.

## Binding commercial caveat

The Kimi K3 license permits commercial use, but a licensee operating
Model-as-a-Service whose aggregate revenue exceeds $20M in any consecutive
12-month period must enter a separate agreement with Moonshot AI before using
the model commercially. Certified inference partners are exempt. The model
license economics are undisclosed and excluded here. One well-utilized rack can
cross this threshold in the base or bull case, so the license agreement is a
binding diligence item rather than a footnote.

## Decision

Do not value a rack at launch-price revenue. Use:

- approximately $8M-$10M as uncontracted hardware/replacement value;
- approximately $20M-$30M as a base three-year economic asset value with
  credible demand, 70% utilization, and price compression;
- more than $50M only with contracted utilization, demonstrated K3 Rubin
  throughput, and resolved model-license economics.

The next decisive evidence is a measured aggregate Kimi K3 throughput curve on
Rubin at several interactivity points, followed by a real traffic/cache trace
and a commercial Moonshot license quote.

For an OpenRouter deployment, the throughput curve should replay the measured
average request geometry of approximately 76k cached input, 5.9k uncached
input, and 985 output tokens. A short-context output-throughput benchmark does
not validate capacity for that workload.

## Sources

Retrieved 2026-07-28.

1. Artificial Analysis, "Language Model Benchmarking Methodology":
   https://artificialanalysis.ai/methodology
   (current methodology; primary methodology source)
2. Artificial Analysis, "Kimi K3 API Provider Benchmarking & Analysis":
   https://artificialanalysis.ai/models/kimi-k3/providers
   (current measured provider and pricing snapshot)
3. Artificial Analysis, "Kimi K2.6 API Provider Benchmarking & Analysis":
   https://artificialanalysis.ai/models/kimi-k2-6/providers
   (current measured mature-market cross-check)
4. NVIDIA Technical Blog, "Scaling Token Factory Revenue and AI Efficiency by
   Maximizing Performance per Watt":
   https://developer.nvidia.com/blog/?p=114827
   (vendor-reported Rubin performance)
5. Moonshot AI, "Kimi K3" model repository:
   https://github.com/MoonshotAI/Kimi-K3
   (primary architecture source)
6. Moonshot AI, "Kimi K3 License":
   https://raw.githubusercontent.com/MoonshotAI/Kimi-K3/main/LICENSE
   (primary license source)
7. NVIDIA, "Vera Rubin NVL72":
   https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/
   (primary system specification)
8. Tom's Hardware reporting Morgan Stanley rack estimate:
   https://www.tomshardware.com/tech-industry/artificial-intelligence/nvidias-memory-costs-soar-485-percent-latest-ai-systems-now-cost-usd7-8-million-to-build-memory-now-comprises-25-percent-of-the-total-cost-rubin-gpus-a-mere-usd50-000-apiece
   (analyst estimate reported by secondary source)
9. Investing.com reporting Bernstein rack and power estimate:
   https://m.investing.com/news/technology-news/what-it-costs-to-deploy-1gw-of-nvidia-vera-rubin-infrastructure-4740730
   (analyst estimate reported by secondary source)
