# GLM-5.2 OpenRouter revenue opportunity — 2026-07-16

> **Partially superseded:** the traffic totals remain valid, but the promotional low-price range applied OpenRouter's endpoint discount twice. Use the corrected pricing, market size, provider rank, and subsidy economics in [GLM52_ROUTING_AND_SUBSIDY_CURVE_2026-07-16.md](GLM52_ROUTING_AND_SUBSIDY_CURVE_2026-07-16.md).

## Decision

GLM-5.2 is the primary commercial target. Gemma 4 31B remains a useful medium-sized bridge only if another lower-cost campaign is needed to prove that the retained-allocation research loop can operate smoothly. Do not spend a long campaign optimizing the bridge once that operational proof exists.

## Evidence contract

- Question: how large is the current GLM-5.2 provider opportunity, and how does it compare with Gemma 4 31B?
- Scope: OpenRouter standard-variant traffic for the seven complete UTC days 2026-07-09 through 2026-07-15, with pricing/provider snapshots retrieved 2026-07-16.
- Non-scope: direct API and enterprise demand, provider payout terms, platform fees, infrastructure COGS, overhead, tax, and profit.
- Falsifier: a refreshed seven-day trace showing materially lower billings, or a stable leading provider share that makes the assumed 37–40% first-place target insufficient.
- Evidence labels: traffic is measured by OpenRouter; billings and capacity are derived; future routing share and deployment cost are inferred until measured.

## Current market

| Metric | Seven-day result |
|---|---:|
| Prompt tokens | 3.230T |
| Completion tokens | 63.136B |
| Total tokens | 3.293T |
| Requests | 69.991M |
| Cached prompt tokens | 2.709T |
| Prompt cache-hit fraction | 83.85% |
| Current weighted input price | $0.3653/M prompt tokens |
| Current weighted output price | $3.7500/M completion tokens |
| Derived current weighted billings | **$1.417M/week** |

The cheapest promotional endpoint observed during the snapshot was approximately $0.686/M uncached input, $2.156/M output, and $0.1274/M cache reads. Repricing all observed traffic at those rates gives **$838,970/week**. A more stable low-price envelope near $0.93/M uncached input, $3.00/M output, and $0.18/M cache reads gives **$1.162M/week**. The current addressable OpenRouter gross-billings range is therefore approximately **$0.84M–$1.42M/week**.

## What “top provider” could bill

The instantaneous provider snapshot was fragmented: NovitaAI had 23.20%, StreamLake 23.12%, Alibaba 19.73%, and Z.ai 13.04% of sampled tokens. The OpenRouter 30-day page had recently shown StreamLake at 36.4% and NovitaAI at 33.9%. Because the measurement windows disagree and routing can move quickly, plan for **37–40%** share to be robustly first rather than assuming that 24–25% will remain sufficient.

| Endpoint price basis | 37% share | 40% share |
|---|---:|---:|
| Promotional low price | $310,419/week | $335,588/week |
| Stable low-price envelope | $429,934/week | $464,793/week |
| Current market-weighted price | $524,230/week | $566,735/week |

The defensible planning headline is therefore **$310k–$465k/week of gross endpoint billings** for a competitively priced first-place provider. That annualizes to approximately **$16.1M–$24.2M**, before all deductions and assuming traffic/share persist. Provider payout and net revenue remain unknown.

This is roughly 25–40 times the $10k–$13k/week first-place opportunity estimated for Gemma 4 31B.

## Research and deployment burden

- The official model repository reports 753B total parameters. The vLLM recipe characterizes the model as approximately 39B active per token.
- The practical official FP8 geometry is one 8xH200/H20 node; full 1M context is documented on 8xB200 with FP8 KV cache. The selective NVFP4 checkpoint is approximately 465 GB and Blackwell-only.
- Existing committed-price planning rates imply approximately $499/day for 8xMI355X, $624/day for 8xH200, or $989/day for 8xB200. This is around 19–37 times the hourly cost of the current single L40S geometry.
- At 37% share, the observed demand averages about 1.98M prompt tokens/s, 38.6k output tokens/s, and 42.8 requests/s. This requires a fleet and strong prefix-cache economics, not merely a fast single-node result.
- A prior Wafer-reported 2,626 output tok/s result on 8xMI355X implies a lower bound of roughly 15 such nodes for the output stream alone at 37% share. Prefill, cache movement, long-context admission, redundancy, and SLO headroom can increase the requirement materially.

The high cache-hit fraction means the decisive economic questions are not only MoE GEMMs. Prefix/KV cache placement, cache-read bandwidth, long-context admission, CPU scheduling, interconnect/topology, expert locality, MTP acceptance, and fleet utilization directly determine whether the revenue can become margin.

## Recommended sequencing

1. Finish only the minimum GLM-4.7 Flash graduation evidence needed to trust repeated retained-allocation experiments.
2. If the lab still needs a moderate stress test, run a bounded Gemma 4 31B admission campaign, not an open-ended optimization campaign.
3. Move the scientific and commercial optimization target to GLM-5.2 on a cached 8-GPU allocation.
4. First compare official FP8 on 8xH200/MI355X with NVFP4 on 8xB200 using the actual cache-heavy agent workload. Measure all-in input, cache-read, and output COGS separately.
5. Optimize the bottleneck observed in those traces; prioritize cache/topology/MTP/runtime interactions before model surgery unless telemetry points elsewhere.

## Reproduction and sources

Seven-day totals are the sums of `total_prompt_tokens`, `total_completion_tokens`, `total_native_tokens_cached`, and `count` for 2026-07-09 through 2026-07-15 from:

- OpenRouter activity: <https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard>
- OpenRouter effective prices/provider shares: <https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard>
- OpenRouter endpoint pricing: <https://openrouter.ai/api/v1/models/z-ai/glm-5.2-20260616/endpoints>
- OpenRouter model page and rolling-window definitions: <https://openrouter.ai/z-ai/glm-5.2>
- Official model card and architecture changes: <https://huggingface.co/zai-org/GLM-5.2>
- vLLM deployment recipe: <https://recipes.vllm.ai/zai-org/GLM-5.2>
- Shared committed-price inventory: [`../../factory/data/gpu_prices.json`](../../factory/data/gpu_prices.json)
- Prior Wafer evidence: [`WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md`](WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md)

Core formulas:

```text
weighted market = prompt_tokens × weighted_input_price + output_tokens × weighted_output_price
endpoint billings = share × (uncached_prompt × input_price + cached_prompt × cache_read_price + output × output_price)
```
