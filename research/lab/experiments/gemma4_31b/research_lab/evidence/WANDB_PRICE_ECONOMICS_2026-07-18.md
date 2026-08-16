# W&B Gemma 4 31B price economics — 2026-07-18

## Question and decision

How can W&B plausibly retail `google/gemma-4-31b-it` at `$0.12/M` fresh input, `$0.09/M` cache read, and `$0.35/M` output while advertising a BF16 endpoint?

Decision use: determine whether the lab's remaining cost gap requires weight quantization or can plausibly be closed through infrastructure economics, throughput, utilization, and strategic pricing. The explanation is falsified by W&B disclosing its exact hardware, runtime, tensor precisions, utilization, provider payout, or unit economics.

## Confirmed facts

- W&B publishes the same Gemma prices on its own Serverless Inference pricing page as OpenRouter exposes. The price is therefore not merely an OpenRouter-specific display discount.
- W&B documentation says its managed services run on CoreWeave infrastructure. CoreWeave completed its acquisition of W&B on 2025-05-05.
- CoreWeave documentation says Serverless Inference is delivered through W&B Inference and that CoreWeave automatically handles scaling, routing, and resource allocation on its own GPU infrastructure.
- W&B classifies Gemma 4 31B as generally available. Its documentation also imposes default spend caps and says included inference credits are available for a limited time.
- OpenRouter reports the W&B endpoint as `wandb/bf16`; this does not disclose KV-cache dtype or internal kernel operand and accumulator formats.

## Scope-matched arithmetic

The campaign request has 3,679 fresh input tokens, 535 cache-read tokens, and 358 output tokens. At W&B retail prices it earns:

`3,679 × $0.12/M + 535 × $0.09/M + 358 × $0.35/M = $0.00061493/request`.

The current retained local H200 endpoint takes `0.919457394125 s/request`. At that throughput, W&B retail corresponds to `$2.4077` of gross revenue per saturated GPU-hour. Our `$3.25/H200-hour` planning rate produces `$0.000830066/request`, 35.0% above W&B retail before production overhead.

At zero overhead, full utilization, and no margin, matching W&B at `$3.25/H200-hour` requires `0.681153 s/request`: 25.9% less service time or 35.0% more throughput than the current retained endpoint.

| Throughput versus current endpoint | Maximum GPU cost at 100% useful utilization, zero overhead/margin | Illustrative maximum GPU cost at 80% useful utilization with 20% of revenue left for non-GPU cost and margin |
|---:|---:|---:|
| 1.00× | $2.41/h | $1.54/h |
| 1.25× | $3.01/h | $1.93/h |
| 1.35× | $3.25/h | $2.08/h |
| 1.50× | $3.61/h | $2.31/h |
| 2.00× | $4.82/h | $3.08/h |

The second column is a mathematical ceiling, not an estimate of W&B cost. The third column is an explicit scenario, not reported W&B economics.

## Best explanation

The price is plausible through a stack of moderate advantages rather than one exceptional precision trick:

1. **Vertically integrated capacity:** W&B is part of CoreWeave and its inference product runs on CoreWeave's fleet. Its economic denominator can be internal fleet cost or the opportunity cost of reserved/otherwise-unused capacity, not the external `$3.25/h` committed cloud rate used by this campaign.
2. **Higher throughput:** A roughly 35% throughput gain alone closes the raw zero-margin gap at `$3.25/h`. Hopper/Blackwell-specific kernels, a B200 placement, stronger batching, or a combination could plausibly supply that order of improvement, but the endpoint hardware and runtime are not disclosed.
3. **Fleet utilization and autoscaling:** CoreWeave controls routing, scaling, and allocation across a managed model catalog. This can improve realized utilization and amortize platform operations, although weights for different models cannot simply share one active replica.
4. **Strategic pricing:** W&B can rationally accept a thin margin, temporary subsidy, or loss leader to increase adoption of the wider W&B/CoreWeave platform. Limited-time included credits and account spend caps limit exposure, but do not prove below-cost pricing.
5. **Mixed internal precision remains possible:** BF16 can identify weights or the public endpoint class while KV cache and selected kernels use FP8. No public source confirms W&B's KV dtype.

The evidence does not support claiming that W&B uses FP8 weights, MXFP4 weights, one specific GPU, a custom kernel, or profitable unit economics.

## Sources

| Source | Retrieved | Evidence type | Use |
|---|---:|---|---|
| `https://wandb.ai/site/pricing/inference` | 2026-07-18 | W&B-reported current pricing | Direct Gemma input/output/cache prices |
| `https://docs.wandb.ai/index.md` | 2026-07-18 | W&B documentation | Managed services run on CoreWeave infrastructure |
| `https://docs.wandb.ai/inference/models.md` | 2026-07-18 | W&B documentation | Gemma model identity and generally available status |
| `https://docs.wandb.ai/inference/usage-limits.md` | 2026-07-18 | W&B documentation | Spend caps, pay-as-you-go terms, and limited-time credits |
| `https://www.coreweave.com/blog/coreweave-completes-acquisition-of-weights-biases` | 2026-07-18; published 2025-05-05 | CoreWeave announcement | Completed ownership integration |
| `https://docs.coreweave.com/products/inference.md` | 2026-07-18 | CoreWeave documentation | CoreWeave GPU infrastructure and inference options |
| `https://docs.coreweave.com/products/inference/serverless.md` | 2026-07-18 | CoreWeave documentation | W&B delivery of CoreWeave Serverless Inference and managed scaling/routing/allocation |
| `https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints` | 2026-07-18T20:13:02Z | OpenRouter-reported live API | W&B endpoint tag, status, and price |
| `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json` | local | Measured | Current retained endpoint service time |

## Next action

Treat W&B's price as an attainable economic target, not proof of an unknown quantization scheme. Measure whether the current stack can reach the 1.35× throughput line on H200/B200 or whether a production-rate H200 below roughly `$2.1/h` is available under the illustrative utilization/margin scenario. Public information cannot distinguish these mechanisms; a controlled endpoint throughput/quality probe or provider disclosure would materially reduce uncertainty.
