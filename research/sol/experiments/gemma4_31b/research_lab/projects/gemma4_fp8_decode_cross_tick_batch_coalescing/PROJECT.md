# FP8 decode cross-tick batch coalescing

## Question

Can the exact pinned Gemma 4 31B SGLang decode scheduler coalesce compatible
linear work from adjacent scheduler ticks into larger FP8 GEMMs, reducing
repeated weight streaming and launch overhead enough to improve sustainable
background-traffic cost without changing model semantics or relying on the
already-negative c48/c64 resident-concurrency arms?

## Why it matters

The qualified H200 denominator is `0.625149101968745 s/request`; the campaign
target is `<=0.500119281574996 s/request` or an equivalent price-normalized
20% improvement. Decode repeatedly presents small `M<=32` QKV, gate/up, and
down projections even under c32 saturation. The completed down-projection
fusion has only a `0.607%` whole-request relevance ceiling, so the independent
portfolio needs a mechanism that can affect the dominant FP8 weight-stream
path. Latency is secondary for the campaign's background-agent traffic.

## Hypothesis

A source-level phase-aware scheduler can hold compatible decode rows for a
bounded interval and issue layer-consistent `M=64/96` FP8 GEMMs across
adjacent ticks while preserving per-request KV ownership, token order, CUDA
graph legality, and exact output semantics. The predicted physical signature
is fewer weight bytes and kernel launches per completed token, not merely
more queued requests or a higher headline batch size.

## Immediate evidence path

Use `$researcher` with deep profile, `$kernel-research`, and
`$experiment-run`.

1. Trace the exact pinned scheduler-to-FP8-linear source path and reconstruct
   the observed c32 decode tick geometry from the narrowest existing
   scope-matched telemetry.
2. Quantify the minimum coalescing interval and row count needed to amortize
   QKV, gate/up, and down weight streams on H200. Keep queueing/completion time
   explicit and do not transfer c48/c64 endpoint results into this mechanism.
3. Implement either a minimal source candidate plus deterministic
   trace/scheduler simulator, or a typed analytical negative if dependencies,
   KV ownership, graph addresses, or layer synchronization prevent legal
   cross-tick grouping.
4. Publish `MECHANISM_TERMINAL.json` with a concrete causal chain, source
   identities, simulated or measured trace rows, falsification conditions,
   and—only if positive—the smallest exact H200 discriminator contract.

## Scope and gates

- Exact model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact baseline family: qualified SGLang dynamic-FP8 c32 endpoint.
- Preserve target semantics, request/KV ownership, token order, and complete
  outputs.
- Compare completed-token service time, launch count, weight bytes, queue
  delay, and usable completion time; batch size alone is not evidence.
- Close only the tested scheduler/dataflow if the legal grouping cannot reach
  a credible positive whole-request bound.

## Resources and prohibitions

- Wall clock: 100 minutes.
- Compute: zero GPU, zero CUDA, and no provider access.
- Storage: 2 GiB.
- Do not claim a bench, request spend, run an endpoint, inspect the paused norm
  execution lineage, or mutate provider lifecycle.
- Do not perform a generic flag sweep or create a scheduler-readiness
  successor project.
