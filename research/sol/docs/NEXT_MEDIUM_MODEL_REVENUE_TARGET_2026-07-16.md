# Next medium-model revenue target — 2026-07-16

## Decision

Target **Gemma 4 31B** after the GLM-4.7 Flash research loop is working smoothly. It is the best current combination of medium model size, paid traffic, addressable provider billings, and a realistically contestable number-one provider position on OpenRouter.

Use **Gemma 4 26B A4B** as the technical runner-up if sparse-MoE transferability is valued more than the probability of becoming the top provider.

### Expanded live-ranking refresh — 2026-07-16T21:49:00Z

The recommendation still holds after broadening the scan beyond the original three models.

- With a strict `20B–80B total parameters` definition, **Gemma 4 31B is the most popular attractive paid target**. Gemma 4 26B A4B has nearly identical token traffic but a smaller revenue pool.
- With a `single-accelerator deployment footprint` definition, **gpt-oss-120b is the most popular candidate**: `528.50B` standard-route tokens in the last seven complete UTC days. Its native MXFP4 checkpoint is `60.8 GiB` and fits one 80 GB GPU despite `116.83B` total parameters and `5.13B` active parameters.
- gpt-oss-120b is not the preferred campaign because its competitive endpoint floor is only about `$0.03/M` input and `$0.15/M` output. Repricing its measured traffic at that floor produces a `$26.13k/week` market, versus `$43.69k/week` for Gemma 4 31B at `$0.12/$0.35`. At a plausible first-place share, Gemma 4 31B therefore offers roughly `$13.1k/week` of gross endpoint billings versus `$7.3k/week` for gpt-oss-120b.

Current standard-route comparison for the seven complete UTC days `2026-07-09` through `2026-07-15`:

| Candidate | OpenRouter weekly rank | Architecture / deployment class | 7-day tokens | Current weighted market billings | Current leader share | Competitive-price whole market | Illustrative first-place endpoint billings |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| **Gemma 4 31B** | 27 | 30.7B dense; quantized single 48/80 GB GPU | **316.55B** | **$59.24k/week** | DeepInfra 26.67% | **$43.69k/week** at `$0.12/$0.35` | **$13.11k/week** at 30% |
| Gemma 4 26B A4B | 29 | 25.2B total / 3.8B active MoE | 308.07B | $36.02k/week | DeepInfra 30.75% | $24.50k/week at `$0.06/$0.33` | $8.58k/week at 35% |
| gpt-oss-120b | 19 | 116.83B total / 5.13B active; one 80 GB GPU | **528.50B** | **$87.42k/week** | Amazon 23.97% | $26.13k/week at `$0.03/$0.15` | $7.32k/week at 28% |
| Mistral Nemo | 32 | 12B dense; below strict medium band | 273.77B | $6.40k/week | DeepInfra 79.72% | $5.41k/week at `$0.019/$0.03` | unattractive: incumbent already near 80% |
| gpt-oss-20b | 39 | 20.91B total / 3.61B active; 12.8 GiB MXFP4 | 183.50B | $10.34k/week | W&B 29.92% | $9.08k/week at `$0.029/$0.14` | $3.18k/week at 35% |
| Qwen3.6 35B A3B | 55 | 35B total / 3B active MoE | 79.37B | $15.86k/week | AkashML 46.60% | $15.64k/week at `$0.13/$1.00` | $7.82k/week at 50% |
| Qwen3.6 27B | 57 | 27B dense | 74.57B | $38.65k/week | Alibaba 73.57% | $26.90k/week at `$0.282/$2.376` | high nominal value, but first-party concentration makes displacement difficult |

`7-day tokens` are measured public OpenRouter standard-route activity. Weighted market billings, competitive-price markets, and first-place endpoint billings are derived and are gross customer-facing amounts before OpenRouter fees, provider payout terms, infrastructure COGS, overhead, and tax. Weekly rank is the live ordering returned by OpenRouter's `sort=top-weekly` Models API. Free variants are excluded because free-token popularity is not evidence of paid demand.

Gemma 4 31B is also the better research target. It is new, has a fragmented 14-provider market, and exposes hybrid local/global attention, unified global-layer K/V, a 262K vocabulary, MTP, multimodal admission, precision, and long-context scheduling as model-specific optimization surfaces. The main launch caveat is that some measured traffic is multimodal; a text-only endpoint cannot assume eligibility for all of the reported demand.

## Evidence contract

- Decision: select the next medium-sized model campaign; do not start or stop a campaign from this brief alone.
- Original narrow snapshot: OpenRouter activity for the seven complete UTC days 2026-07-09 through 2026-07-15; provider mix and effective pricing retrieved 2026-07-16T10:30:30Z. The expanded refresh above supersedes its live pricing and provider-share fields.
- Revenue definition: gross end-user billings attributable to an endpoint, before OpenRouter/platform fees, provider payout terms, infrastructure COGS, overhead, and tax. This is not net revenue or profit.
- Scope: OpenRouter only. Direct API, enterprise, and other aggregator demand are excluded.

## Original narrow comparison — 2026-07-16T10:30:30Z

| Candidate | Architecture | 7-day tokens | Live weighted model billings | Current leading token share | Share assumed to rank first | Gross weekly billings at competitive price |
|---|---:|---:|---:|---:|---:|---:|
| **Gemma 4 31B** | 30.7B dense | 316.55B | **$66.79k** | 21.24% | 25–30% | **$10.13k–$12.16k** at $0.11/$0.34 per M input/output |
| Gemma 4 26B A4B | 25.2B total, 3.8B active | 308.07B | $34.44k | 42.58% | 45% | $10.73k at $0.06/$0.30 |
| Qwen3.6 35B A3B | 35B total, 3B active | 79.37B | $16.00k | 50.96% | 55% | $8.60k at $0.13/$1.00 |

The Gemma 4 31B market also has a conservative competitive-price value of **$40.53k/week** if all current traffic were repriced at $0.11/M input and $0.34/M output. The live provider-weighted estimate is $66.79k/week. Thus a reasonable current OpenRouter market range is about **$40k–$67k/week**, while a first-place endpoint at 25–30% share could bill about **$10k–$12k/week**. At $0.12/$0.35, that endpoint range is approximately $10.9k–$13.1k/week.

## Why Gemma 4 31B

1. **Demand:** its measured 316.55B weekly tokens are 5.26 times GLM-4.7 Flash's 60.16B-token snapshot.
2. **Contestability:** the largest provider currently carries only 21.24% of tokens. Gemma 4 26B A4B and Qwen3.6 are led by providers with about 43% and 51%, respectively, so becoming number one requires much more displacement.
3. **Revenue:** a plausible first-place share produces roughly $0.53M–$0.63M annualized gross endpoint billings at the competitive price used above, before churn and all deductions.
4. **Research surface:** the model combines hybrid local/global attention, unified K/V on global layers, a large 262K vocabulary/output head, and a dedicated multi-token-prediction draft model. These expose concrete co-design opportunities in speculative decoding, attention/KV movement, output-head execution, quantization, batching, and kernel/runtime specialization.
5. **Manageable step up:** 30.7B dense parameters are substantially below GLM-5.2 scale. Derived storage is about 61.4 GB in BF16, 30.7 GB at 8-bit, or 15.4 GB at 4-bit before runtime and KV-cache allocations. A quantized deployment on a 48 GB-class GPU is plausible at controlled context, but must be measured.

## Caveats and falsifiers

- OpenRouter token traffic is measured; billings are derived from public token counts and public effective/list pricing. OpenRouter does not expose the endpoint's provider payout or margin here.
- Live provider shares are a short-window routing snapshot and can move quickly. Recheck immediately before campaign selection.
- Multimodal image token accounting may not be fully represented by the simple prompt/completion calculation.
- A cheap endpoint does not automatically receive 25–30% of traffic. Availability, latency, throughput, context support, quantization labels, routing preferences, and reliability also affect share.
- Dense 31B inference may have worse COGS than the sparse candidates. Before committing the campaign, run a one-day admission screen measuring quantized memory fit, throughput, quality-deferred stability, and cost per million tokens on the available accelerator inventory.

## Reproducible public sources

- OpenRouter Gemma 4 31B activity: <https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=google%2Fgemma-4-31b-it-20260402&variant=standard>
- OpenRouter Gemma 4 31B effective pricing and provider shares: <https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=google%2Fgemma-4-31b-it-20260402&variant=standard>
- OpenRouter Gemma 4 31B provider page: <https://openrouter.ai/google/gemma-4-31b-it/providers>
- Official Gemma 4 31B model card: <https://huggingface.co/google/gemma-4-31B-it>
- Official Gemma architecture overview: <https://ai.google.dev/gemma/docs/core>
- OpenRouter Gemma 4 26B activity: <https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=google%2Fgemma-4-26b-a4b-it-20260403&variant=standard>
- OpenRouter Gemma 4 26B effective pricing: <https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=google%2Fgemma-4-26b-a4b-it-20260403&variant=standard>
- OpenRouter Qwen3.6 activity: <https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=qwen%2Fqwen3.6-35b-a3b-20260415&variant=standard>
- OpenRouter Qwen3.6 effective pricing: <https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=qwen%2Fqwen3.6-35b-a3b-20260415&variant=standard>
- OpenRouter live weekly-ranked Models API: <https://openrouter.ai/api/v1/models?sort=top-weekly>
- OpenRouter Models API documentation: <https://openrouter.ai/docs/guides/overview/models>
- OpenRouter gpt-oss-120b activity: <https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=openai%2Fgpt-oss-120b&variant=standard>
- OpenRouter gpt-oss-120b effective pricing: <https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=openai%2Fgpt-oss-120b&variant=standard>
- OpenRouter gpt-oss-120b endpoints: <https://openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints>
- Official gpt-oss model card: <https://deploymentsafety.openai.com/gpt-oss/preparedness-framework>
- Official Qwen3.6 model card: <https://huggingface.co/Qwen/Qwen3.6-35B-A3B/blob/main/README.md>
