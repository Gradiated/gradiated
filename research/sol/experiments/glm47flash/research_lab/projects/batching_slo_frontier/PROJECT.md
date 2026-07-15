# Fixed-workload batching and SLO frontier

## Question

What cache-off concurrency and admission point minimizes sustainable dollars per output token for the fixed 8,192-input/1,024-output GLM-4.7-Flash background workload on AWQ/vLLM/L40S when interactive latency may be traded for cost?

## Why it matters

V21 measured 355.772 output tok/s at c8 and a derived $0.670/M output tokens. At the measured $0.8581222/hour VM-plus-disk rate, 397.28 output tok/s reaches the campaign's $0.60/M strong gate, while a 5% same-stack cost improvement requires at most $0.6365/M. The server was capped at eight sequences and 65,536 batched tokens, so the background-cost saturation frontier was never measured. The old 10-second TTFT and 100-millisecond TPOT gates are interactive constraints and no longer outrank the campaign's explicit latency-for-cost policy.

## Relevant evidence

- `campaign_100/allocations/nebius_l40s_vllm_awq_prefill65k_v21/summary.json` and `preregistration.json`.
- V19's c8 control: 344.211 output tok/s, 0.5954-second mean queue time, and $0.6925/M with a 32,768-token scheduler budget.
- V21's c8 result: 355.772 output tok/s, near-zero mean queue time, and $0.6700/M after raising only the budget to 65,536 tokens.
- V21 reported 333,488 KV-cache tokens; the all-request prompt-plus-output upper bounds are 147,456 tokens at c16 and 294,912 at c32, before runtime reserve and fragmentation checks.

## Scope

Use the existing c16-capable V31 controller/runner and the proven external systemd controller/watchdog boundary to run one cache-disabled retained-session ladder with an adjacent c8 control, c16, and c32 if the exact local KV/preflight gate admits it. Extend only the already arm-scoped concurrency contract needed for c32; do not spend another cycle on preparation. Hold model, AWQ checkpoint, vLLM revision, activation dtype, 65,536-token scheduler budget, generation, exact token geometry, prefix-cache state, seed, and scoring fixed. Record throughput, TTFT, TPOT, queueing, makespan, batch/KV state, success, VRAM, utilization, power/energy, useful GPU time, allocation exposure, lifecycle overhead, and both steady-state and duty-cycle-amortized cost.

Treat TTFT and TPOT as measured tradeoffs, not interactive rejection gates. The background reliability envelope requires every exact request to complete successfully and without truncation within a 120-second arm deadline. Reject identity/geometry drift, semantic divergence, OOM, incomplete evidence, or reliability failure. Report c16/c32 even if they exceed the historical interactive SLO; promotion depends on cost and the declared background envelope.

Do not modify kernels, enable prefix caching, amend the agent-session workload, recalibrate quality, repair observer tooling, or claim quality-adjusted economics until the separate prospective gate passes. Do not overlap another lab paid allocation; use one provider owner and prefer sequential arms on one retained server.

## Available resources

Use the shared factory tools, V19/V21/V31 runner and provider controls, frozen fixed workload, vLLM metrics, existing L40S checkpoint/runtime identities, and the proven external systemd ownership pattern. Authenticated inventory is empty. This project is the sole provider-mutation owner for one fresh L40S session under a $1.00 all-in cap and 3,600-second absolute timeout, including a $0.07 cleanup reserve. Validate the exact controller unit, source hashes, inventory, watchdog, and terminal artifact path before create. If that preflight cannot pass in this researcher turn, stop without create and record one typed operational result; do not begin another controller lineage. No other project may mutate a provider concurrently.

The provisional major-provider anchor is Cloudflare's vendor-listed GLM-4.7-Flash price of $0.88 per million output-equivalent tokens at the fixed 8:1 ratio. It is not matched evidence and cannot support a competitive claim; the independent comparator project will refresh and qualify it. `claims_permitted: false` continues to prohibit quality-adjusted or provider-advantage claims from this diagnostic.

## Portfolio-changing result

A reliable point at or above 397.28 output tok/s reaches the strong $0.60/M steady-state gate conditionally on quality and becomes the new serving control. A reliable >=5% cost reduction versus V21 is still a useful tuned incumbent. If no admitted c16/c32 point improves cost by at least 5%, or all points fail the background envelope, close batching and transfer the next serving session to prefix reuse. The result must separately report lifecycle-amortized cost and does not repair absolute quality or establish provider competitiveness.
