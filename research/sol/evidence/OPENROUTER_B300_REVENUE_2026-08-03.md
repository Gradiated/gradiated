# OpenRouter B300 gross-revenue screen — 2026-08-03

Decision question: how much gross provider revenue can one B300 generate when a
self-hosted open-weight frontier model is listed on OpenRouter at exactly the
cheapest active provider price?

## Result

At 75% useful fleet utilization, the best screened opportunity is Kimi K3 at
approximately **$27–$41 of gross billings per available B300-hour**, or
**$219–$329/hour for the minimum 8-B300 deployment**. GLM-5.2 is the strongest
measured-throughput case at approximately **$15.23/B300-hour**. DeepSeek V4 Pro
is only approximately **$6.04/B300-hour** at its unusually low official-provider
price.

These are capacity-revenue estimates, not realized OpenRouter payouts or profit.
They assume enough routed demand, the observed OpenRouter cache mix, correct and
persistent prefix caching, and no quality/SLO deranking.

| Model | Cheapest active price, uncached/cache/output ($/M) | Observed uncached/cache tokens per output token | B300 processed tok/s/GPU | Gross $/B300-h at 100% | Gross $/B300-h at 75% | Confidence |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Kimi K3 | 3.00 / 0.30 / 15.00 | 11.81 / 48.72 | 2,000–3,000 | 36.56–54.84 | **27.42–41.13** | Low-medium: final-weight B300 verification is still pending; range brackets SGLang's approximately 3K tok/s/GPU large-scale observation |
| GLM-5.2 | 0.72 / 0.12 / 1.80 | 7.58 / 43.74 | 3,870 | 20.31 | **15.23** | Medium-high: public SGLang 8xB300 NVFP4 high-throughput measurement, 8K-in/1K-out |
| DeepSeek V4 Pro | 0.435 / 0.003625 / 0.87 | 6.56 / 33.70 | 4,400 | 8.06 | **6.04** | Medium-high: public SGLang 8xB300 FP4 high-throughput measurement, 8K-in/1K-out |
| DeepSeek V4 Flash 0731 | 0.09 / 0.018 / 0.18 | 6.66 / 52.98 | 9,432 | 7.68 | **5.76** | Medium-high: public SGLang B300 FP4 high-throughput measurement; included as an efficient but lower-value control |

OpenRouter's complete 2026-08-02 activity at those floor prices implies total
market billings of roughly $7,727/hour for Kimi K3, $2,292/hour for GLM-5.2,
$1,036/hour for DeepSeek V4 Pro, and $842/hour for DeepSeek V4 Flash. One 8-B300
Kimi node at the 75%-utilization estimate therefore needs only approximately
2.8–4.3% of current model billings to stay economically full. One GLM-5.2 node
needs approximately 5.3%.

## Method

For each model, OpenRouter's last complete public activity day supplies uncached
input `U`, cached input `C`, and output `O`. Public serving measurements supply
processed throughput per GPU `T`; cached tokens are billed but are not counted as
fresh model-forward tokens. The estimate is:

```text
output_tokens_per_second = T / (1 + U/O)
gross_revenue_per_gpu_hour = utilization * 3600 * output_tokens_per_second
  * (P_output + (U/O)*P_uncached + (C/O)*P_cache) / 1,000,000
```

SGLang defines its displayed throughput per GPU as input plus output tokens over
elapsed time per GPU. The measured GLM and DeepSeek benchmarks use 8,192 input
and 1,024 output tokens with cache flushing. Applying the current uncached/output
ratio is therefore a workload conversion, not a claim that cached input consumes
zero memory, lookup, transfer, or retention capacity.

## Buy-versus-rent boundary

The lab's current medium-term B300 rental planning rate is $5.80/GPU-hour
(`research/factory/data/gpu_prices.json`). Public 8-B300 server indications are
approximately $430K–$550K; use $485K as a midpoint only after obtaining a quote.
With three-year depreciation, residual value, power, colo, support/spares, and
cost of capital, an indicative owned all-in range is roughly $3–$4.50/GPU-hour.

At 75% utilization:

- Kimi K3 has very large modeled headroom over either rental or ownership.
- GLM-5.2 supports approximately 62% gross margin at the $5.80 rental planning
  rate before non-GPU serving costs, or roughly 70–80% against the indicative
  owned range.
- DeepSeek V4 Pro is approximately break-even on committed rental before
  non-GPU costs and only moderately attractive on owned hardware.
- DeepSeek V4 Flash does not support the current committed-rental rate before
  non-GPU costs.

The apparent Kimi cash payback is only a few months, which is a warning that the
uncertainty is commercial and operational rather than arithmetic. Do not buy a
fleet from this screen alone. First reproduce K3 throughput on final weights,
replay the actual OpenRouter token/cache distribution, confirm the provider
settlement contract, and demonstrate enough routing share at 99%+ uptime with
competitive tool-call quality.

## Evidence and exclusions

- Current provider prices and endpoint status: OpenRouter public endpoint APIs
  for `moonshotai/kimi-k3`, `z-ai/glm-5.2`, and
  `deepseek/deepseek-v4-pro`.
- Current workload mix and market volume: OpenRouter public model-activity APIs,
  complete UTC day 2026-08-02.
- Throughput and topology: SGLang Kimi K3, GLM-5.2, and DeepSeek V4 cookbooks.
- Kimi K3 weights and architecture: Moonshot's official Hugging Face model card.
- Qwen3.7 Max/Plus are excluded because current weights are not available for an
  independent provider deployment. Closed frontier APIs are excluded for the
  same reason.
- OpenRouter says default stable-provider routing prioritizes price using
  inverse-square price weighting, while uptime, throughput, parameter support,
  and Auto Exacto tool quality can still change realized share. Matching floor
  price is therefore necessary but not sufficient.

Evidence labels: OpenRouter prices/activity and SGLang throughput are measured or
vendor/framework-reported public observations. Workload conversion, Kimi range,
utilization, ownership cost, margin, and required-share calculations are derived.
