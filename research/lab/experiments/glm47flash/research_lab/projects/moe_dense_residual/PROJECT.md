# MoE and dense residual falsification

## Question

Does the AWQ/vLLM/L40S c8 decode path contain a named dense GEMM/GEMV, MoE expert, or routing operation with a correctness-preserving intervention and a conservative end-to-end ceiling of at least 5%?

## Why it matters

Eight KV splits reduced exact-shape grouped-MLA component time by 40.27% and summed attention/MLA work by 33.43%, yet two bracketed server effects were only 1.0476% and 1.0447%. That falsifies MLA split count as the material serving bottleneck. Dense GEMM/GEMV is the largest measured residual decode family, but the available shares are diagnostic summed durations and some come from a different BF16/H100 stack. The next intervention must be earned with scope-matched evidence rather than another broad observer campaign.

## Relevant evidence

- `campaign_100/analysis/SPLIT8_TRACE_DELTA_V24R2_V25R1.json`, `SPLIT8_BRACKET_RESULT_V24R2_V28R1.json`, and `TRACE_BOTTLENECK_V13.json`.
- `campaign_100/allocations/nebius_l40s_mla_microbench_v23r1/` and the V24R2 through V28R1 serving artifacts.
- `campaign_100/analysis/OPPORTUNITY_REGISTER_2026-07-14.json`, especially stopped `OPP-001` and residual `OPP-003`.
- Measured guardrail: a large component win transferred to only about 1.05% c8 throughput, below the 5% campaign gate.

## Scope

Start by mining existing AWQ/L40S traces and installed runtime sources to name exact operations, shapes, launch resources, and a conservative removable fraction. Prefer deterministic trace replay, analytical bounds, and correctness-checked standalone microbenchmarks. A bounded L40S component run is allowed only after local fixtures, source/checkpoint identities, failure capture, deadline, cost cap, and cleanup are explicit. Do not repair or rerun the Nsight observer launcher, alter the quality suite, study caching/scheduling, or run a full-model candidate A/B unless a component candidate is hardware-legal, passes an independent oracle, retains raw interleaved timings, and has a defensible prospective c8 ceiling of at least 5%. Retire split-count-only MLA variants.

## Available resources

Use the shared factory tools, campaign trace analyzers, vLLM source-pinning and microbenchmark controls, existing L40S provider controls, and prior allocation artifacts. Keep any paid component stage within $1.00 and 45 minutes with verified teardown; public IPv4/egress remain excluded from derived cost.

## Portfolio-changing result

A scope-matched operation with a correctness-passing component improvement and conservative >=5% c8 ceiling promotes exactly one matched server A/B. If no named operation clears that bar, stop custom kernel work on this c8 stack and move capacity to serving mechanisms or representation/runtime controls. A cross-stack-only lead is not promotable.
