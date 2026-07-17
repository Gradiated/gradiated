# W4 background batching and queueing bound

## Decision question

For the prompt-heavy 4,214-input/358-output campaign mix, do W4 c16 or c32 admit a stable, usable background-serving region that beats the market cost after queueing and headroom, and which one load geometry should a later endpoint test measure?

## Why now

The campaign explicitly permits latency-for-cost trades, while prior gates mostly report service floors and Little's-law ceilings at fixed concurrency. The corrected W4 bound makes c16 comfortable in capacity and c32 allocator-sensitive at 10K. A reproducible queueing surface can decide whether higher batching is economically necessary or merely adds latency before any endpoint successor exists.

## Authoritative inputs

- `../gemma_l40s_w4_c16_economic_bound/W4_C16_BOUND_V2.json`, SHA-256 `b697e8c43bcdecac9b0261ab79e363b39e11e9c37a0be282d357a21c9e24fe9d`.
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`, SHA-256 `690e0e457c6e8e9121b54fb7f88abc92c3dcc358e1d71accffddb083878d00d6`.
- `../exact_market_venue_decision_surface/MARKET_TARGET.json`, SHA-256 `5d636809dc25450050c565cdc108bf7e91eaa60ce07c027ca390c8011e3b8e51`.
- `../exact_geometry_runtime_opportunities/GEOMETRY.json`, SHA-256 `024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72`.
- Fresh shared L40S production planning rate `$1.10/GPU-hour`, range `$1.00–$1.25`, from price SHA-256 `3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01`.

Keep the Artificial Analysis 10K single-stream methodology separate from the aggregate campaign queue.

## Required experiment

Build a deterministic analytical/discrete-event bound over c8/c16/c32, arrival rate, batch-formation window, and whole-request overhead. Use the corrected W4 phase floors as optimistic service inputs and sweep explicit attention/KV/head/scheduler/sampling overhead rather than inventing one endpoint latency. Include the campaign cache mix, production utilization/headroom/reliability factors, primary memory envelope, and a distinct 10K single-stream check. Use fixed seeds and enough events or analytical convergence to make p50/p95 completion time, queue stability, realized batch size, throughput, idle fraction, and cost/request reproducible.

Report:

- the maximum non-linear overhead per request consistent with the planning and conservative market hurdles at c16 and c32;
- arrival/pooling thresholds needed to realize those batches without unstable queues;
- Pareto surfaces for cost/request versus p50/p95 completion time, without imposing an inherited interactive SLO;
- sensitivity to burstiness, 12.7% cache reads, the `$1.00–$1.25` rate range, and allocator-sensitive 10K c32;
- one later endpoint load geometry only if it discriminates c16 from c32 and remains conditional on a passing actual W4 mechanism plus an exact-revision checkpoint/quality route.

This is a synthetic/derived bound, not endpoint throughput. If no plausible non-linear-overhead and arrival region beats the market even under background latency tolerance, close W4 economics regardless of component speed. If c16 dominates c32 after queueing/fit risk, explicitly reject c32. Do not wait for or poll the live owner; parameterize its eventual measured aggregate as an input field so the terminal can be consumed without rerunning the simulation.

## Limits and artifacts

- Wall clock: 45 minutes.
- Compute: 2 local CPU-hours; no GPU.
- Storage: 2 GiB project-local; no shared `/tmp`.
- Spend: `$0`; no provider mutation, CUDA, full weights, or quality execution.

Write a reproducible script, `QUEUE_BOUND.json`, concise `DECISION.md` and `RESEARCH_LOG.md`, and terminal `STATUS.json`.
