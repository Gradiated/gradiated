# Gemma 4 31B inference co-optimization

## Objective

Minimize sustainable end-to-end serving cost for the exact instruction checkpoint `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, initially in its default non-reasoning text mode. The commercial goal is to win paid OpenRouter traffic while remaining a credible Gemma 4 31B endpoint. Latency is secondary for background-agent traffic; trade it for lower cost when completion time and reliability remain usable.

This is a fresh campaign. Do not inherit GLM-4.7 model identity, target prices, workload assumptions, admission gates, project backlog, or conclusions. Reuse generic provider, profiling, measurement, and cleanup mechanics when they save time.

Research progress means measured or tightly bounded movement in cost, throughput, capacity, or a causal bottleneck. Prefer a useful experiment over more process. One bounded compatibility check is enough before changing approach. Broad quality evaluation is deferred until a performance candidate deserves it, but no candidate becomes production-eligible without quality and feature validation.

## Market scorecard

Use current external data and refresh it before any market claim. The launch-mode references at campaign start on 2026-07-16 are:

- Artificial Analysis: exact [Gemma 4 31B (Non-reasoning)](https://artificialanalysis.ai/models/gemma-4-31b-non-reasoning/providers) page. Its current cheapest displayed blend is about `$0.14/M`; its standard performance view uses about 10K input tokens and single-stream generation. Keep this methodology-matched view separate from aggregate throughput.
- OpenRouter model ID: `google/gemma-4-31b-it`, whose default reasoning mode is disabled. The current credible low-price frontier is approximately `$0.12/M` fresh input, `$0.09/M` cache read, and `$0.35/M` output. Compare components, not only a blended headline.
- Recent OpenRouter traffic is prompt-heavy: approximately 4,214 prompt and 358 output tokens per request, an 11.76:1 prompt/output ratio, with cache reads around 12.7% of prompt tokens. Treat these as a starting distribution, not an immutable synthetic benchmark.

Report at least fresh-input, cache-read, and output economics separately; then report retail and sustainable self-hosted cost for the measured workload mix. Use actual provider rates for experiment spend and the shared committed-production rates in `research/factory/data/gpu_prices.json` for production comparisons. Include utilization, queueing, replicas/headroom, failures/reloads, storage, orchestration, and other material costs.

## First research cycle

Start both lanes immediately and let evidence change the portfolio:

1. **Measured baseline:** get the exact pinned model serving on one suitable GPU placement and measure complete requests, prompt/decode throughput, TTFT, memory, power, utilization, queueing, failures, and experiment cost. Choose the fastest credible route to evidence: BF16 on enough memory or a well-supported quantized representation. A 30.7B dense checkpoint is roughly 61.4 GB in BF16 before runtime state, so a 48 GB placement requires a lower-precision representation; do not repeatedly rediscover that constraint. Use a bounded initial run and always clean up provider resources.
2. **Opportunity derivation:** inspect the exact architecture, tensor shapes, runtime support, and target-chip hierarchy while the baseline runs. Rank interventions by expected all-in cost reduction and cheapest falsifier. Gemma's hybrid five-local/one-global attention, 1,024-token local window, unified global K/V, very large vocabulary/output head, precision choices, batching/cache geometry, and possible MTP path are starting hypotheses—not a required checklist.

The primary workload is a reproducible distribution around the OpenRouter token mix under background concurrency and batching. Also preserve an Artificial Analysis methodology-matched 10K-input single-stream view. Measure saturation rather than assuming interactive settings are economical.

Use text-only, non-reasoning traffic for initial cost discovery. Vision/video and reasoning are separate product modes; add them before claiming full OpenRouter feature eligibility, not before the first useful performance experiments.

## Autonomy, spend, and stopping

The campaign has an initial autonomous experiment-spend cap of `$25` and at most one live paid provider allocation at a time. Each allocation needs a declared deadline, actual metered rate, durable telemetry, and reliable cleanup. A failed placement or runtime route is one branch result: switch hardware, provider, runtime, representation, or experiment geometry rather than spending cycles polishing the same failure.

The director should keep a small portfolio of independent, falsifiable projects and retire weak lines quickly. Researchers use their judgment, record concise decision-relevant evidence, and continue until the project decision is supported or its stated budget expires. The supervisor improves research cadence only when traces show a real bottleneck; it must not add ritual or deterministic gates.

## Shared resources and lab files

- Shared factory tools: `research/factory/tools/`
- GPU prices and accelerator capabilities: `research/factory/data/`
- Proven Nebius lifecycle mechanics, reusable after replacing GLM-specific model assumptions: `research/sol/experiments/glm47flash/campaign_100/nebius/`
- `DIRECTOR_LOG.md`: portfolio decisions.
- `projects/<project>/PROJECT.md`: delegated question and scope.
- `projects/<project>/RESEARCH_LOG.md`: concise progress and evidence.
- `projects/<project>/STATUS.json`: scheduler state and next action.
- `SUPERVISOR_LOG.md`: process bottlenecks and useful improvements.
- `STATUS.md` and `runtime/`: generated current status, events, timings, and Codex traces.
