# DeepSeek V4 Flash 0731 OpenRouter latency targets

## Decision

Set the first provider target at:

- provider-visible TTFT p50 at or below 0.70 seconds;
- provider-visible TTFT p90 at or below 1.00 second;
- provider-visible TPOT at or below 8 ms per token at p50;
- provider-visible TPOT at or below 10 ms per token at p90;
- at least 99.5% successful requests after warmup;
- early `429` responses under overload instead of long queue waits.

The stretch target is 0.55 seconds TTFT p50 and 6 ms TPOT. These targets are
inferred from the current provider comparison. OpenRouter does not publish a
single fixed acceptance threshold.

## Scope and falsification

This decision applies to the DeepSeek V4 Flash 0731 endpoint offered through
OpenRouter. It does not claim that a short local prompt predicts long-context
performance.

Falsify the target if a representative external test shows either p50 or p90
outside the target for two consecutive 30-minute windows, or if queueing causes
the endpoint to miss the error or uptime target.

## Current market evidence

OpenRouter's provider documentation states that it tracks TTFT and throughput
for every provider. Its throughput metric includes fetch latency, TTFT, and
streaming time, so queueing on the provider is visible in the metric. OpenRouter
also recommends returning early `429` responses under load instead of keeping
requests in a long queue. Its routing metrics use rolling p50, p75, p90, and
p99 values.

The current OpenRouter model page lists DeepSeek V4 Flash 0731 at $0.03 per
million input tokens and $0.075 per million output tokens, with a 1M-token
context window. The current launcher in the Pod is configured for 262,144
tokens, so the advertised context must not exceed the tested service limit.

A current third-party provider snapshot reports these comparable values for
the same model revision:

| Provider route | TTFT | Output speed | Uptime | Evidence |
| --- | ---: | ---: | ---: | --- |
| DigitalOcean | 0.55 s | 19 tok/s | 99.92% | Current snapshot |
| CoreWeave | 0.58 s | 114 tok/s | 99.95% | Current snapshot |
| DeepInfra | 0.76 s | 33 tok/s | 98.71% | Current snapshot |
| Baidu Qianfan | 0.99 s | 89 tok/s | 100.00% | Current snapshot |
| Reka AI | 0.96 s | 164 tok/s | 99.97% | Current snapshot |
| Wafer Fast | 0.99 s | 194 tok/s | 99.97% | Current snapshot |

The snapshot reports 29 providers with complete price and speed data. It is a
market signal, not an OpenRouter acceptance guarantee.

## Our measured baseline

The two live RunPod Pods used vLLM 0.27.1, the same model checkpoint, and
streaming requests with a short prompt and a 128-token output limit. The
measurements were loopback-only and excluded the OpenRouter and Internet path.

| Deployment | TTFT median | TPOT median | Decode rate |
| --- | ---: | ---: | ---: |
| 1x B300 | 33.4 ms | 7.35 ms/token | 136 tok/s |
| 2x B300 tensor parallel | 40.5 ms | 7.21 ms/token | 139 tok/s |

These values pass the inferred TPOT target locally. They do not prove that the
provider-visible TTFT will pass after TLS, gateway, geographic routing, prompt
prefill, queueing, and OpenRouter measurement overhead.

A longer streamed test used about 2,020 input tokens and 500 output tokens,
after one warmup request. It measured 151 ms TTFT, 7.49 ms/token, and 133.5
tok/s on 1x B300. It measured 178 ms TTFT, 7.31 ms/token, and 136.8 tok/s on
2x B300 tensor parallel. These are still loopback measurements.

## Operating recommendation

Use two independent 1x B300 replicas behind one OpenAI-compatible endpoint for
the first provider submission. This gives each request a full GPU, avoids
tensor-parallel collectives, and provides two independent 16-sequence
schedulers. Use admission control to keep queueing below the target. Keep the
2x tensor-parallel deployment for comparison, not as the default throughput
topology.

Run the acceptance benchmark with streaming and these workload buckets:

1. 1k input tokens and 128 output tokens.
2. 8k input tokens and 256 output tokens.
3. 32k input tokens and 512 output tokens.
4. Tool calls and structured output.

Measure TTFT, TPOT, p50/p90/p99, queue time, errors, GPU utilisation, and
NVLink traffic at concurrency 1, 4, 8, 12, and 16 per replica. Repeat each
bucket after warmup and at the expected arrival rate.

## Source table

| URL | Retrieved | Evidence type |
| --- | --- | --- |
| https://openrouter.ai/docs/guides/community/for-providers | 2026-08-26 | OpenRouter official documentation |
| https://openrouter.ai/docs/guides/routing/provider-selection | 2026-08-26 | OpenRouter official documentation |
| https://openrouter.ai/deepseek/deepseek-v4-flash-0731/api | 2026-08-26 | OpenRouter model listing |
| https://providerbench.ai/models/deepseek/deepseek-v4-flash-0731/ | 2026-08-26 | Current third-party provider snapshot |
| `/workspace/logs/stream-metrics-1xb300.txt` | 2026-08-26 | Measured remote run |
| `/workspace/logs/stream-metrics-2xb300.txt` | 2026-08-26 | Measured remote run |
| `/workspace/logs/provider-comparable-1xb300.txt` | 2026-08-26 | Measured remote run |
| `/workspace/logs/provider-comparable-2xb300.txt` | 2026-08-26 | Measured remote run |

## Next action

Deploy two independent 1x B300 replicas, expose a controlled external test
endpoint, and collect the four workload buckets before submitting the provider
application. Do not advertise 1M context until the 1M path has passed a
separate memory and latency test.
