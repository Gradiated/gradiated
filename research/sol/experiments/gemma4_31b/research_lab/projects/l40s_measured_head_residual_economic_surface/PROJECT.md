# L40S measured-head residual economic surface

## Decision question

After substituting the actual pinned-runtime tied-head measurements for prior FLOP proxies, does any L40S one-byte decoder region at c8/c16/c32 still have enough residual request budget to beat the campaign market hurdle, and what single later direct arm—if any—would change the decision?

This is independent `$0` evidence while the H200 checkpoint materializer runs. It cannot poll, read partial checkpoint files, delay, or mutate that owner.

## Authoritative evidence

- Exact head rows and cleanup: `../gemma_l40s_parallel_lm_head_measurement_final/artifacts/gemma-l40s-head-final-20260717t065653z/summary.json`.
- Exact workload/economic hurdle and service budgets: `../l40s_saturation_economic_gate/SATURATION_GATE.json`.
- Corrected one-byte phase/capacity bound: `../gemma_l40s_w4_c16_economic_bound/`.
- Queue/background regions: `../w4_background_batching_queue_bound/`.
- Exact geometry/KV accounting: `../exact_geometry_runtime_opportunities/GEOMETRY.json` and `../fp8_kv_contract_reconciliation/KV_CONTRACT.json`.
- Representation/consumer limits: `../exact_w4_producer_quality_route/`, `../gemma_l40s_w4_marlin_component_bridge/`, and `../tied_head_joint_onebyte_consumer_route/NONE.json`.

Exclude the source-rejected generic-Ada exact-shape claim, zero-row consumer attempts, and any bandwidth value with incorrect units. Do not transfer timing across a consumer, representation, or shape without an explicit analytical-bound label.

## Required analysis

Recompute primary and separate 10K c8/c16/c32 surfaces with the measured BF16 head rows. Phase-separate prompt/prefill, decode, head, KV/cache, sampling/scheduler, queueing, runtime reserve, failures/reloads, and production headroom. Use valid measured quantities where available and optimistic/conservative analytical lower bounds for missing decoder work. The optimistic lower bound must not silently credit impossible simultaneous full-weight bandwidth reuse; the conservative case must not double-count resident vision or KV bytes.

For each concurrency report:

- measured head seconds/request and fraction of the 1.394581 planning and 0.86329 conservative service envelopes;
- residual seconds available for the rest of the endpoint;
- representation-specific capacity and queue stability;
- minimum completed requests/s and cost/request at the `$1.10/hour` planning rate plus `$1.00-$1.25` sensitivity;
- which missing measured consumer could still reverse the decision.

Return `RESIDUAL_SURFACE.json` plus `DECISION.md`, choosing at most one of: close L40S one-byte endpoint economics; retain c16 only; retain c32 only; or retain c16/c32 with one ranked direct falsifier. Any nominee must acknowledge absent exact-revision checkpoint provenance/quality and cannot reopen a closed consumer lineage. No provider action follows automatically.

## Budgets

- Wall clock: 35 minutes.
- Compute: 1 local CPU-hour; no GPU.
- Storage: 512 MiB project-local; no shared `/tmp`.
- Spend: `$0`; no provider, checkpoint, image pull, compilation, CUDA, endpoint, or quality execution.

Write the typed surface, concise decision/log, and terminal status.
