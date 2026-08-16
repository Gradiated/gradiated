# L40S FP8 c12/c14 background queue bound

## Decision question

At the campaign's required completed-request rate and background-agent latency tradeoff, what arrival rate, in-flight concurrency, completion time, and pooling/queue conditions are required to realize c12/c14 decode batching on one L40S, and when would the batching geometry cease to be a credible commercial endpoint even if component cost passes?

This is independent `$0` queueing/saturation evidence. It must not poll, edit, wait for, or infer from the live component owner, and it cannot claim endpoint performance.

## Scope

Bind the campaign workload, planning/conservative required request rates and all-in factors, c12/c14 memory geometry, 358-token decode length, and any valid existing c16/c32 batching/queue derivations by hash. Treat latency as secondary but require completion time and reliability to remain usable; do not silently impose an interactive SLO or assume a full synchronized batch.

Derive curves for continuous batching under arrival rates from the strict planning hurdle through 2x that rate. Use Little's Law and explicit service-time/decode-token assumptions to distinguish resident sequence concurrency from instantaneous decode batch and prefill chunking. Quantify the minimum mean/p95 completion time or multiplexed traffic needed to maintain average decode M=12 and M=14, the startup/pooling penalty at low arrival rates, stable-utilization headroom, and sensitivity to one versus multiple replicas. Include the separate 10K c1 methodology view without substituting it into primary economics.

Return thresholds/curves, not a fabricated hard SLO. State the exact live-component fields a later merge needs (per-token decode batch distribution, prefill/decode overlap, completion time, queue wait, arrivals/completions, failures/reloads). Emit one typed result: `background_batching_credible_region`, `c12_c14_requires_unusable_latency_under_target_rate`, or `none_missing_authoritative_inputs`.

## Budgets and terminal

- Wall clock: 25 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 384 MiB retained plus 128 MiB temporary.
- Spend: `$0`; no provider query/mutation, image/checkpoint, or endpoint.

Write a reproducible calculator, source/hash manifest, `QUEUE_BOUND.json`, concise log, and terminal status.
