# Current-AWQ saturation bound

## Question

Does the measured current-AWQ L40S c16 point leave enough scheduler, memory, or GPU headroom for one c24/c32 background measurement to improve output throughput by at least 5%, or is c16 already the useful saturation frontier?

## Why it matters

c16 improved the adjacent c8 control by 52.02% to 535.286 output tok/s and $0.445308/M productive output, but it was capped at `max_num_seqs=16` and no higher-concurrency arm ran. The stricter historical provider hurdle leaves only modest sustainable overhead headroom, so one higher batching point is valuable only if retained telemetry supports a credible gain; a blind GPU ladder would waste setup time and budget.

## Relevant evidence

- `nebius_current_awq_c16_direct/artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/summary.json` and its request, metrics, GPU, profiler, cost, and lifecycle artifacts.
- Exact current AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, vLLM 0.15.0, 8,192-input/1,024-output workload, `num_kv_splits=4`, `max_num_batched_tokens=65536`, and cache-off c8/c16 controls.
- c16 measured 2.072 seconds mean server queue time, 61.216 seconds arm wall, exact completions, and a 535.286 tok/s denominator; the promotion threshold is 562.050 tok/s.

## Scope

Run one zero-provider, content-bound saturation falsifier using the retained c8/c16 telemetry and exact workload geometry. Separate prefill, decode, scheduler/queue, memory/KV, and GPU-utilization limits; do not infer wall-time share from overlapping summed kernel time. Reconcile `max_num_seqs`, batched-token capacity, KV occupancy, observed request waves, power/utilization, and profiler evidence. Bound c24 and c32 throughput under conservative and optimistic assumptions, including completion-time and reliability effects allowed by the campaign's background latency policy.

Nominate at most one later matched c24 or c32 L40S arm only if the retained evidence gives a credible >=5% path over 535.286 tok/s and exact server arguments fit the measured memory envelope. Otherwise close higher concurrency and retain c16. Do not invoke a provider, alter the checkpoint/runtime, build a controller, enable prefix caching, or claim sustainable/quality-adjusted economics.

## Available resources

Use the complete c16 artifact bundle, `campaign_100` vLLM runners and telemetry parsers, and shared factory analysis tools. Produce a machine-readable bound, a reproducible calculator, and a short research-log decision.

## Portfolio-changing result

A conservative >=5% path promotes exactly one later c24/c32 matched measurement after quality releases provider ownership. A bound below 562.050 tok/s closes this scheduling extension and moves future cost work to different hardware, representation, or serving mechanisms.
