# OpenRouter capacity opportunity scan

- Date: 2026-08-26
- Status: evidence snapshot
- Decision: continue the DeepSeek V4 Flash 0731 qualification on one B300.
- Next candidate: test MiMo V2.5 only when a multi-GPU deployment is available.

## Question

Can public OpenRouter API data show which models need more provider capacity?

## Answer

OpenRouter does not publish rejected demand, model queue depth, aggregate 429
rates, or provider capacity declarations. The API cannot directly show which
models reach their capacity limits most often.

The API does publish daily public token use and current endpoint health. These
fields support a supply-gap proxy. The proxy compares seven-day public token
use with the number of active provider endpoints. It also checks endpoint
uptime, latency, throughput, and ZDR support.

This proxy is inferred evidence. It is not a capacity measurement. One large
provider can supply more capacity than many small providers.

## Snapshot

The scan used data available at `2026-08-26T10:07:08.190Z`. The demand window
was 2026-08-19 through 2026-08-25. It contained 357 daily ranking rows and 61
distinct models. The endpoint scan covered the top 40 weekly models.

| Model | Seven-day public tokens | Active endpoints | Tokens per active endpoint | Degraded endpoints | ZDR endpoints |
|---|---:|---:|---:|---:|---:|
| MiMo V2.5 | 9.915T | 4 | 2.478T | 1 | 3 |
| Hy3 | 7.157T | 7 | 1.022T | 0 | 4 |
| DeepSeek V4 Flash 0731 | 11.624T | 25 | 0.465T | 8 | 21 |
| DeepSeek V4 Flash 0423 | 5.577T | 16 | 0.349T | 2 | not reviewed |
| Step 3.7 Flash | 0.445T | 3 | 0.148T | 0 | 2 |

An endpoint was marked degraded when it had a nonzero status or less than 95%
uptime during the prior day. This is a conservative local rule.

## Interpretation

MiMo V2.5 has the strongest inferred supply gap. It has high use, four active
endpoints, and three ZDR endpoints. Its five listed endpoints had a median
one-day uptime of 97.01%, a median time to first token of 2.746 seconds, and a
median throughput of 35 tokens per second.

Hy3 has the next strongest concentration. Its seven endpoints were active.
Their health was better than the MiMo group. This result shows concentrated
supply, but it does not show an active shortage.

DeepSeek V4 Flash 0731 has the highest relevant public use. It also has 29
listed endpoints and 21 ZDR endpoints. A new DeepSeek provider does not fill a
clear model-availability gap. It can still fill a performance, reliability,
price, location, or privacy gap. Eight listed endpoints met the conservative
degraded rule during this snapshot.

Daily demand was stable during this seven-day window. DeepSeek V4 Flash 0731
used 1.390T to 1.849T tokens per day. MiMo V2.5 used 1.180T to 1.728T tokens per
day. Hy3 used 0.707T to 1.255T tokens per day.

## One-B300 fit

NVIDIA specifies 288 GB of HBM3e for one B300 GPU.

MiMo V2.5 has 310B total parameters and 15B active parameters. FP8 weights need
about 310 GB before runtime and KV-cache memory. Its published SGLang example
uses tensor parallelism across eight GPUs and data parallelism across two
replicas. It is not a direct one-B300 production candidate.

Hy3 has 295B total parameters and 21B active parameters. Its official model
card lists BF16 support. It does not fit on one B300 in that precision.

Step 3.7 Flash has 198B total parameters and 11B active parameters. Its
quantized GGUF form can fit in one B300. Its published production vLLM and
SGLang examples use four GPUs for NVFP4 or eight GPUs for FP8 and BF16. A
one-GPU deployment needs a separate performance qualification.

DeepSeek V4 Flash 0731 remains the best first qualification target because the
current one-B300 deployment is already in progress. The provider application
must show a measured advantage. Target ZDR, stable US capacity, at least 99.9%
uptime, competitive price, and strong time-to-first-token and throughput.

## Application implication

OpenRouter states that it has a large provider backlog. It prioritizes
proprietary models and providers that fill network gaps. It routes traffic by
latency, throughput, uptime, and price. Model demand alone does not ensure
acceptance.

Use the following position for the first application:

1. Offer a stable US ZDR DeepSeek V4 Flash 0731 endpoint.
2. Include measured B300 latency, throughput, concurrency, error rate, and
   24-hour soak results.
3. Set an accurate capacity declaration in the provider model document.
4. State the tested context limit. Do not claim the model maximum without a
   matching load test.
5. Add MiMo V2.5 as a planned second model only after a suitable multi-GPU test.

## Reproduction

Use an OpenRouter API key through an environment variable. Do not put the key
in a command, document, or repository file.

The read-only inputs were:

- `GET https://openrouter.ai/api/v1/datasets/rankings-daily`
- `GET https://openrouter.ai/api/v1/models?sort=top-weekly`
- `GET https://openrouter.ai/api/v1/models/:author/:slug/endpoints`
- `GET https://openrouter.ai/api/v1/endpoints/zdr`

Group daily ranking rows by `model_permaslug`. Sum `total_tokens` over the
seven-day window. Count endpoint rows with `status == 0` as active. Compare this
count with the token total. Review uptime, latency, throughput, price, and ZDR
support before making a decision.

## Sources

- [OpenRouter Data API](https://openrouter.ai/docs/cookbook/administration/data-api)
- [OpenRouter endpoint API](https://openrouter.ai/docs/api/api-reference/endpoints/list-endpoints)
- [OpenRouter provider application](https://openrouter.ai/providers/apply)
- [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers)
- [MiMo V2.5 model card](https://huggingface.co/XiaomiMiMo/MiMo-V2.5)
- [Hy3 model card](https://huggingface.co/tencent/Hy3)
- [Step 3.7 Flash model card](https://huggingface.co/stepfun-ai/Step-3.7-Flash)
- [NVIDIA B300 hardware reference](https://docs.nvidia.com/enterprise-reference-architectures/whitepaper/hgx-servers-and-spectrum-x.pdf)
