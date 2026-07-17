# GLM-4.7-Flash provider economics denominator

Date: 2026-07-16

## Question and decision

Question: if public providers charge `$0.40/M` output tokens for GLM-4.7-Flash, why does the campaign's best full-47 L40S point still report `$0.477-$0.485/M` output tokens of raw GPU cost?

Decision: do not interpret that comparison as proof that providers have lower serving COGS. The campaign rate is total GPU wall cost for a request mix containing 8,192 uncached input tokens and 1,024 output tokens, divided only by output tokens. Providers bill both sides of that same request. At current DeepInfra standard pricing, the corresponding revenue is `$0.88` per million output-equivalent requests, not `$0.40`. The campaign needs separate input, cached-input, and output activity costs plus a matched aggregate load test before concluding that a technical or procurement gap remains.

## Scope, hypothesis, and falsification

Scope: exact campaign 8K-input/1K-output cache-off profiles on one L40S, current public GLM-4.7-Flash prices, and publicly described provider infrastructure. This is not evidence of any provider's actual hardware, aggregate throughput, utilization, COGS, margin, or subsidy.

Hypothesis: most of the apparent price gap is caused by a denominator mismatch, with any residual gap likely explained by shared-fleet utilization, owned/committed hardware, larger-memory accelerators, and fleet-level scheduling rather than one unknown model kernel.

Falsification: the hypothesis weakens if a matched provider-equivalent cost model that allocates prefill, cached prefill, and decode separately still exceeds public revenue after realistic lifecycle overhead, or if direct provider aggregate-throughput/hardware evidence shows materially lower COGS from a model-specific mechanism.

## Measured and derived result

The campaign runner starts its wall timer before submitting every request and computes `total_output_tokens / elapsed`; each row verifies exactly 8,192 prompt and 1,024 completion tokens. Prefill, queueing, and decode therefore all contribute to the reported `$ / M output` denominator.

At `$1.10/L40S-hour`:

| Candidate | Measured aggregate output tok/s | Raw GPU cost per M output | DeepInfra standard revenue at 8:1 | Raw GPU headroom | DeepInfra Flex revenue at 8:1 | Raw GPU headroom |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stock full-47 | 609.606 | $0.501 | $0.880 | 43.0% | $0.704 | 28.8% |
| Selective-W4 full-47 | 630.195 | $0.485 | $0.880 | 44.9% | $0.704 | 31.1% |
| Top-3/shared full-47 | 641.127 | $0.477 | $0.880 | 45.8% | $0.704 | 32.3% |

Revenue formulas:

- DeepInfra standard: `8 * $0.06 input + 1 * $0.40 output = $0.88` per million output-equivalent requests.
- DeepInfra Flex: `8 * $0.048 input + 1 * $0.32 output = $0.704`.
- Amazon/Novita list price: `8 * $0.07 input + 1 * $0.40 output = $0.96`.

These margins are before CPU, RAM, storage, network, orchestration, idle capacity, failures, support, and company gross margin. They nevertheless reverse the prior conclusion that raw L40S compute is already above provider revenue on the measured workload.

Artificial Analysis's default `7:2:1` cache/input/output blend is a pricing normalization, not evidence that the campaign's cache-disabled profile matches provider traffic. DeepInfra charges `$0.01/M` cached input and supports a best-effort Flex tier at a 20% discount; a matched competitive claim therefore requires a legitimate cache-hit workload and cache activity cost rather than disabling caching and comparing only against the output tariff.

## Competing explanations and provider priors

1. **Fleet utilization and queueing — strongly supported as a general mechanism.** DeepInfra Flex requests can wait up to ten minutes for spare capacity and may be rejected; this directly trades latency/availability for utilization. AWS describes Project Mantle as using automatic capacity management and unified pools. Novita describes batching, load balancing, elastic scaling, and warm model pools.
2. **Cheaper capital — supported generally, not model-specifically.** DeepInfra says it owns and operates infrastructure across eight US data centers. Its public cluster offer prices all-in B300 capacity at `$2.99/GPU-hour` for three years and `$1.98` for five years. Novita says it partners with data centers and publicly advertises H100 rental around `$1.85/hour`. None identifies the hardware serving this GLM endpoint.
3. **Newer/larger accelerators — plausible, unverified for GLM-4.7-Flash.** DeepInfra publicly offers B200/B300 infrastructure with much greater HBM capacity and bandwidth than L40S. Larger memory can support BF16 weights, larger batches, or multiple replicas. DeepInfra labels its public GLM-4.7-Flash endpoint `bfloat16`, but that label does not prove its kernel precision or physical placement.
4. **Serving software — supported generally.** Novita publicly cites vLLM, SGLang, PagedAttention, RadixAttention, quantization, and batching. DeepInfra cites NVIDIA Dynamo collaboration and full-stack co-design; AWS uses Project Mantle. This argues that vLLM itself is not necessarily the main gap, while fleet-level scheduling and exact-model optimization remain important.
5. **Pricing strategy or subsidy — possible but not established.** Three providers list the same `$0.40/M` output tariff despite output speeds ranging from roughly 65 to 175 tokens/s per streamed request. That suggests a market-anchored list price rather than transparent cost-plus pricing. DeepInfra's `$0.32/M` Flex tariff shows that standard pricing is not a hard marginal-cost disclosure, but public evidence cannot distinguish spare-capacity monetization, lower COGS, cross-subsidy, or temporary pricing.

## Missing controls and next action

1. Replace the single output-denominated campaign gate with activity-based `$/M fresh input`, `$/M cached input`, and `$/M output`, plus revenue and gross-margin calculations for named workload mixes.
2. Run one long-lived, production-shaped aggregate test with the exact Artificial Analysis 10K-input geometry and a realistic output distribution; report per-request streamed speed and total fleet/GPU throughput separately.
3. Run a legitimate repeated-prefix cache arm because DeepInfra's cheapest blended price depends materially on its `$0.01/M` cached-input tariff.
4. Measure the same checkpoint on a high-memory Blackwell or a cheaper owned/committed candidate before assuming L40S is the production optimum.
5. Treat provider single-stream output speed as an SLO observation, not an aggregate capacity number.

## Sources

| Source | Retrieved | Evidence type | Use |
| --- | --- | --- | --- |
| https://artificialanalysis.ai/models/glm-4-7-flash/providers | 2026-07-16 | Independent benchmark | Current provider prices, 7:2:1 blend, per-request output speed |
| https://deepinfra.com/zai-org/GLM-4.7-Flash | 2026-07-16 | Vendor-reported | `$0.06/$0.40/$0.01` standard and `$0.048/$0.32/$0.008` Flex prices; BF16 label |
| https://docs.deepinfra.com/chat/overview | 2026-07-16 | Vendor documentation | Flex waits up to ten minutes, may reject, and costs 20% less |
| https://deepinfra.com/series-b | 2026-07-16 | Vendor-reported | Owned infrastructure, eight US data centers, NVIDIA/Dynamo collaboration |
| https://deepinfra.com/deepcluster | 2026-07-16 | Vendor-reported | B300 term economics and infrastructure scope |
| https://aws.amazon.com/bedrock/pricing/ | 2026-07-16 | Vendor pricing | Amazon `$0.07/M` input and `$0.40/M` output |
| https://aws.amazon.com/about-aws/whats-new/2026/02/amazon-bedrock-expands-aws-privatelink-support-openai-api-endpoints/ | 2026-07-16 | Vendor-reported | Project Mantle unified pools and automatic capacity management |
| https://blogs.novita.ai/behind-the-scenes-how-we-host-models-on-novita-ai/ | 2026-07-16 | Vendor-reported | Batching, load balancing, quantization, warm pools, and data-center partnerships |
| `campaign_100/nebius/vllm_batched_runner.py` | 2026-07-16 | Measured-method contract | Wall timer and output-only denominator |
| `projects/full47_selective_w4_proven_path_direct/STATUS.json` | 2026-07-16 | Measured | Selective-W4 throughput, planning cost, geometry, and scope limits |
| `projects/top3_shared_c36_direct/STATUS.json` | 2026-07-16 | Measured | Reproduced top-3/shared c32 throughput and scope limits |

