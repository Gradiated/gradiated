# SGLang H100 capacity and economic surface

## Decision question

For the exact content-bound SGLang BF16 plus FP8-E5M2-KV route, which primary and 10K concurrency points can physically fit one H100 80GB, and what completed-request throughput is required to beat both the campaign market hurdle and the matched vLLM promotion gate?

This is independent `$0` evidence while the L40S tied-head owner runs. It must not poll, delay, inspect transient files from, or mutate that owner. It does not create a provider resource or replace the queued full-stack measurement.

## Authoritative inputs

- `../sglang_gemma4_exact_precreate_binding/START_PACKET.json` and `validation.json`.
- Exact target `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, 60 layers, 50 sliding/10 global, hidden 5,376, 32/16 attention/KV heads, four global KV heads, 1,024 local window, BF16 weights, FP8-E5M2 KV.
- Exact BF16 weight bytes `62,546,177,752` from `../h200_bf16_bandwidth_economic_falsifier/BOTTLENECK_BOUND.json`.
- Primary 4,214 input / 358 output with 12.7% cache reads under background concurrency; separate 10K-input/358-output single stream.
- Market request-cost hurdle `$0.000614–$0.000621`; production H100 planning rate `$2.80/GPU-hour` with `$2.50–$3.10` range. Shared prices are fresh; do not search them again.
- SGLang promotion contract: sustainable cost/request `<=0.90x` matched same-H100 vLLM and packet floor `>=1.825` completed requests/s. Reconcile rather than assume the provenance of that floor.

## Required analysis

Mechanically derive the SGLang-specific resident memory surface for c1/c2/c4/c8/c16/c32 at the primary geometry and c1/c2/c4/c8/c16 at 10K. Account separately for exact BF16 weights, text-only vision residency, FP8 K/V payload, scale/block metadata, output/head workspaces, CUDA graph capture, scheduler/request state, and configured allocator reserve. Bind any SGLang default or formula to the immutable source files already retained by the predecessor; label unknown runtime fragmentation as a sensitivity, not a fabricated constant.

Report raw-capacity, configured-memory-fraction, and conservative-reserve cases. Identify the largest concurrency that fits before runtime measurement and the first allocator-sensitive point. Do not transfer the earlier vLLM BF16-KV capacity result without converting the exact dtype/layout and engine reserve.

Derive the completed-request throughput needed at `$2.50/$2.80/$3.10` per GPU-hour to clear both ends of the market hurdle, then explain what additional utilization/headroom assumption—if any—turns that into the packet's `1.825 req/s` floor. Express the matched SGLang-versus-vLLM 10% gate independently, because it cannot be decided without contemporaneous measurements. Convert viable concurrency points into one recommended saturation ladder and explicit stop points for the later H100 owner.

Return `CAPACITY_COST_BOUND.json` plus `DECISION.md`. Nominate at most one of:

- H100 ladder admissible, with exact c points and allocator/throughput gates;
- H100 single-stream only plus conditional H200 capacity branch using the already completed H200 packet; or
- typed none if the immutable SGLang configuration cannot fit the exact checkpoint even at c1 under a defensible reserve.

This is a derived screening result, not endpoint throughput, quality, latency, or sustainable-cost evidence. Do not create another readiness successor.

## Budgets

- Wall clock: 35 minutes.
- Compute: 1 local CPU-hour; no GPU.
- Storage: 512 MiB project-local, including at most 128 MiB bounded source/metadata probes; no shared `/tmp`.
- Spend: `$0`; no provider mutation, weights, image layers, compilation, CUDA, endpoint, or quality execution.

Write the typed bound, concise decision/log, and terminal `STATUS.json`.
