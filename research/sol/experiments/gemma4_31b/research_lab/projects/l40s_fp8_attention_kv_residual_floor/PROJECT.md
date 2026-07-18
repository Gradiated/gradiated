# L40S FP8 attention/KV residual floor

## Decision question

For the exact Gemma 4 campaign workload at online-FP8 c12/c14 on one L40S, what optimistic compulsory attention/KV seconds/request must remain outside the measured linear/head/KV-writer component sum, and what maximum component total can still fit the planning and conservative whole-service ceilings?

This is independent `$0` analytical evidence. It must not poll, edit, wait for, or infer from `l40s_online_fp8_actual_consumer_floor`, and it has no provider authority.

## Scope and method

- Bind exact model/revision, hybrid 50 sliding / 10 global layer geometry, 4,214 input / 358 output / 12.7% cache mix, 10K sensitivity, and c12/c14 from content-addressed lab artifacts.
- Bind FP8-per-token-head K/V payload and scale layout from `../fp8_kv_contract_reconciliation/KV_CONTRACT.json`; do not retain the predecessor's erroneous BF16 local payload.
- Bind actual L40S memory bandwidth, L2 capacity, dense/FP8 compute formats and peaks from `research/factory/data/accelerator_inventory.json`; do not browse or transfer H200 timing.
- Bind planning/conservative service ceilings from `../l40s_saturation_economic_gate/SATURATION_GATE.json`.

Derive exact compulsory decode KV bytes/request across all 358 positions for 50 local-window layers and 10 global layers, including GQA heads/dims, FP8 cache data, required dynamic scales, and the exact context progression. Credit at most the full bound L2 once per request and divide by peak L40S bandwidth as an impossible-ideal lower bound. Show whether concurrency changes per-request bytes; do not divide by c12/c14 twice.

Separately derive fresh-prompt QK/AV FLOPs/request for the campaign cache mix and decode QK/AV FLOPs/request, correctly handling the 1,024 sliding window, causal global contexts, GQA query-head work, cached-prefix sensitivity, and 358 generated positions. Translate only through a supported optimistic arithmetic denominator and label any kernel-format/softmax mismatch. Combine arithmetic and bandwidth floors only when the resource/no-overlap argument is valid; otherwise report max and sum sensitivities.

Emit planning and conservative maximum admissible measured-component totals at c12/c14 under each defensible floor, plus a merge formula for the live actual-consumer project. List omitted softmax, norms/rotary, sampling, scheduler/queue, reliability, and service overhead. Return one typed result: `residual_threshold_bound`, `component_floor_already_closes`, or `none_identity_failure`. This is not endpoint, quality, or achieved-throughput evidence.

## Budgets and terminal

- Wall clock: 25 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 384 MiB retained plus 128 MiB temporary.
- Spend: `$0`; no provider query/mutation, image pull, checkpoint read, compilation, or endpoint.

Write a reproducible calculator, source/hash manifest, `ATTENTION_KV_RESIDUAL_FLOOR.json`, concise `RESEARCH_LOG.md`, and terminal `STATUS.json`.
