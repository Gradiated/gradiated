# Small frontier model review for OpenRouter

- Date: 2026-08-26
- Status: candidate shortlist
- Decision: qualify DeepSeek V4 Flash 0731 first; keep Step 3.7 Flash as the
  multimodal alternative.

## Question

Which recently released open-weight models have strong OpenRouter demand and
can run on a practical multi-GPU deployment for a provider application?

## Scope and limits

This review covers models with public weights, recent OpenRouter traffic, and a
deployment footprint below the largest 8-GPU frontier systems. It does not
measure Gradiated throughput, latency, or quality. GPU counts below are derived
from published parameter counts and weight precision. They include no large
long-context KV-cache allowance unless stated.

OpenRouter's official rankings measure tokens and task-spend share. They do not
publish an authoritative per-model dollar total. The dollar figures below are
directional estimates from OpenRouter token totals and current list prices.

## Demand snapshot

The estimated seven-day spend ranking for relevant open-weight models is:

| Model | Estimated spend | Tokens | OpenRouter model price | Model date |
|---|---:|---:|---:|---|
| MiMo V2.5 | $3.56M | 8.18T | $0.14 / $0.28 per 1M tokens | 2026-04-22 |
| MiniMax M3 | $2.62M | 1.76T | $0.14 / $1.21 per 1M tokens | model list date not exposed |
| DeepSeek V4 Flash 0731 | $2.02M | 16.85T | $0.06 / $0.12 per 1M tokens | 2026-07-31 |
| Step 3.7 Flash | $0.583M | 665.97B | $0.20 / $1.15 per 1M tokens | 2026-05-28 |
| MiMo V2.5 Pro | $0.534M | 547.25B | $0.435 / $0.87 per 1M tokens | 2026-04-22 |

OpenRouter's current task-spend feed also shows strong demand for GLM 5.2,
DeepSeek V4 Pro, and Kimi K3 in coding and agent tasks. Those models are much
larger or have less practical first-deployment fit.

## GPU fit

The active parameter count controls compute. The full parameter count controls
weight memory for a normal MoE deployment. Keep at least 10–20% headroom for
runtime state, routing, CUDA workspaces, and a useful KV cache.

| Model | Published size | Derived weight footprint | Practical first deployment |
|---|---|---:|---|
| DeepSeek V4 Flash 0731 | 284B total / 13B active; FP4 + FP8 mixed | roughly 150–285 GB, depending on mixed layers | 2x H200 or 2x B200 for short-to-medium context; 4x H100 is possible. Use 4x H200 for high concurrency or long context. |
| Step 3.7 Flash | 198B total / 11B active; FP8 or NVFP4 checkpoints | roughly 100–200 GB | 2x H200 or 2x B200. NVFP4 can fit on 2x 96GB RTX PRO 6000 with reduced context and concurrency. |
| MiMo V2.5 | about 310B total / 15B active | roughly 155–310 GB at 4–8 bit | 2x H200 with a suitable quantization; 3–4x H200 is safer for production context. |
| MiniMax M3 | about 428B total / 23B active | about 214 GB at FP4; 428 GB at FP8 | 2x H200 only with an efficient quantization; 4x H200 is the safer production target. |
| Nemotron 3 Ultra | 550B total / 55B active; official NVFP4 | vendor states 4x B200/B300 or 8x H100 minimum | 4x B300/B200 or 8x H100. This is not a small first deployment. |
| GLM 5.2 | 744B total / about 40B active | roughly 372 GB at 4-bit before overhead | 4x H200 or 2x B300-class GPUs only with a validated low-bit runtime. Treat as a later option. |

GPU memory references used here: H200 141 GB, B200 180 GB, B300 288 GB, and
RTX PRO 6000 Blackwell 96 GB. These are capacity estimates, not performance
claims.

## Recommendation

Choose **DeepSeek V4 Flash 0731** for the first qualification attempt.

Reasons:

1. It is the newest model in the practical shortlist.
2. It has the highest observed token demand and the third-highest estimated
   spend among the shortlist.
3. Its 284B/13B MoE design gives a credible 2x H200 or 2x B200 starting point.
4. DeepSeek reports strong agentic and coding results for the official release.
5. The official model card documents vLLM and SGLang serving paths.

The main risk is competition. OpenRouter already has many DeepSeek providers.
The application must show a measured latency, throughput, uptime, price, and
geographic capacity advantage.

Choose **Step 3.7 Flash** instead if Gradiated can offer a differentiated
multimodal service. Its native image and video input, 256K context, and 198B
total parameter footprint create a clearer product gap than another text-only
DeepSeek endpoint.

OpenRouter states that provider applications must support an OpenAI-compatible
streaming API, usage accounting, a complete `/models` response, monthly
invoicing, and clear privacy terms. It also states that applications are
prioritized for proprietary models and that routing depends on latency,
throughput, uptime, and price. A model choice alone does not guarantee
approval.

## Qualification gate

Before submitting the application, run a fixed test set against the selected
model and record:

- non-streaming and streaming correctness;
- time to first token and output tokens per second at 1, 4, 8, and 16 requests;
- 95th percentile latency and error rate;
- tool calling and structured output behavior, if advertised;
- 24-hour soak uptime and restart recovery;
- exact model metadata, pricing, context, location, and privacy fields.

Reject the candidate if it cannot sustain at least 95% uptime, if streaming
usage totals are wrong, or if the measured economics do not beat an existing
OpenRouter provider at comparable quality.

## Nebius H200 cost estimate

Nebius currently lists H200 at $4.50 per GPU-hour on demand and $2.45 per
GPU-hour preemptible. Its H200 GPU-cluster preset is eight GPUs. A two- or
four-GPU model therefore still requires an eight-GPU host when deployed as an
InfiniBand-connected cluster; unused GPUs remain billable.

| Nebius allocation | On demand | Preemptible | 72-hour test | 7 days | 730-hour month |
|---|---:|---:|---:|---:|---:|
| 1 H200 VM | $4.50/h | $2.45/h | $324 | $756 | $3,285 |
| 8 H200 host | $36/h | $19.60/h | $2,592 | $3,292.80 | $26,280 |

The eight-GPU host is the realistic production cost for DeepSeek V4 Flash on
Nebius. A first qualification run should use 72 hours on preemptible capacity
if interruption recovery is part of the test, or 72 hours on demand if the
goal is a clean OpenRouter reliability measurement. These figures exclude
storage, egress, taxes, and any commitment discount.

## Why four GPUs for long context

DeepSeek V4 Flash has 284B total parameters and 13B active parameters. Active
parameters reduce compute per token, but the full MoE weight set still needs to
be resident. Two H200s provide 282 GB of HBM and can be enough for a short-
context, low-concurrency quantized deployment. Four H200s provide 564 GB.

The extra memory holds the model weights plus the KV cache, runtime workspace,
CUDA/NCCL buffers, and several concurrent requests. A 1M-token context can
consume more memory than the weights, depending on the attention and KV-cache
implementation. Four GPUs are therefore a safer long-context starting point,
not a hard minimum. The initial provider contract should advertise a measured
128K or 256K context limit until a 1M-context test passes.

## Sources

| Source | Evidence type |
|---|---|
| https://openrouter.ai/api/frontend/v1/rankings/task-spend | Measured OpenRouter task-spend share, retrieved 2026-08-26 |
| https://tokenscost.com/spend-leaderboard | Derived seven-day dollar estimates from OpenRouter data, retrieved 2026-08-26 |
| https://openrouter.ai/api/v1/models | Measured current model IDs, prices, context, and creation timestamps, retrieved 2026-08-26 |
| https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731 | Vendor model card and benchmark claims |
| https://github.com/stepfun-ai/Step-3.7-Flash | Vendor model card and deployment claims |
| https://huggingface.co/MiniMaxAI/MiniMax-M3 | Vendor model card and deployment claims |
| https://huggingface.co/XiaomiMiMo/MiMo-V2.5-Pro | Vendor model card and parameter claims |
| https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 | Vendor model card and minimum GPU claim |
| https://huggingface.co/docs/transformers/main/model_doc/glm_moe_dsa | Framework documentation and parameter claim |
| https://www.nvidia.com/en-gb/data-center/h200/ | Vendor GPU memory specification |
| https://docs.nvidia.com/enterprise-reference-architectures/whitepaper/hgx-servers-and-spectrum-x.pdf | Vendor platform GPU memory specification |
| https://www.nvidia.com/en-us/products/workstations/professional-desktop-gpus/rtx-pro-6000/ | Vendor GPU memory specification |
| https://openrouter.ai/providers/apply | Vendor application requirements and routing policy |
| https://nebius.com/prices | Vendor current GPU pricing |
| https://docs.nebius.com/compute/virtual-machines/types | Vendor VM presets and GPU-cluster constraints |

## One-H200 replica option

If each replica must use one H200 VM, **Step 3.7 Flash** is the strongest
revenue-backed candidate found. A current spend estimate places it at about
$583K of OpenRouter traffic over seven days. The vendor publishes an NVFP4
checkpoint and a GGUF build with about 111.5 GB of language-model weights plus
the projector and runtime overhead. That can fit in one 141 GB H200 for a
short-context, low-concurrency service.

The limitation is important: the vendor's production vLLM/SGLang examples use
tensor parallelism across four or eight GPUs. A one-H200 replica is therefore
an experimental low-concurrency deployment, not the vendor's recommended
production configuration. Start with an 8K context cap, measure quality and
throughput, and do not advertise the full 256K context until it passes.

Other one-H200 candidates:

- **OpenAI gpt-oss-120b:** OpenAI states that it fits on one 80 GB GPU and is a
  strong reasoning model. It does not appear in the current 17-model public
  spend leaderboard, so there is no evidence yet of meaningful OpenRouter
  revenue.
- **Mistral Small 4:** 119B total and 6.5B active, Apache 2.0, multimodal, and
  designed for efficient serving. It is a good technical fit for one H200, but
  it also has no visible top-tier OpenRouter spend evidence.
- **Qwen3.5-35B-A3B:** fits comfortably on one H200 and supports text, image,
  and video. Its current OpenRouter spend is not visible in the public top-
  model spend table.

At Nebius' current on-demand rate, independent replicas cost approximately:

| Replicas | Hourly | 730-hour month |
|---:|---:|---:|
| 1 | $4.50 | $3,285 |
| 2 | $9.00 | $6,570 |
| 4 | $18.00 | $13,140 |
| 8 | $36.00 | $26,280 |

This avoids the eight-GPU cluster requirement because each replica is a
standalone one-GPU VM. It also avoids cross-host tensor parallelism, at the
cost of lower per-replica context and throughput.
