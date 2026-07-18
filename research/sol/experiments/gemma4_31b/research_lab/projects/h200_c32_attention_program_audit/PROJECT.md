# H200 c32 attention program adversarial audit

## Decision question

Do the final staged bytes for `../h200_c32_actual_attention_residual_floor` behaviorally implement the admitted actual-attention experiment before its one provider creation, or must creation fail closed?

This is an independent read-only `$0` audit. It may inspect files written by the paid project and shared lifecycle tools, but it must not edit that project, mutate provider state, invoke CUDA, pull the image, or weaken/replace the paid owner's own typed pre-create gate.

## Required audit

Wait at most 15 wall-clock minutes for the paid project to publish its immutable staged runner/wrapper, source-probe terminal, transitive-byte manifest, and claimed final audit. Waiting is only for local files, never provider state. If they do not appear, return `not_ready_no_provider_opinion` rather than inventing a pass.

Audit actual behavior and bound bytes, not required-substring presence:

1. Exact model revision, pinned image digest/observed vLLM build, H200 shape, c32, 50/10 layer geometry, Q/KV heads/dims, sliding 1,024, and global contexts 4,214..4,571.
2. The concrete installed pinned-vLLM/FlashAttention CUDA decode consumer is resolved and invoked; PyTorch SDPA, analytical timing, fallback kernels, and fake/synthetic pass rows are rejected. CPU source probing may establish planned symbols but cannot substitute for the GPU terminal.
3. Deterministic BF16 tensors, global K=V, no checkpoint/server/model weights, small numerical oracle, finite output consumption, CUDA-event plus synchronized-wall distributions, warmup/repetition/stability, memory/allocator and H200 telemetry.
4. Architecture weighting is exactly `sum_358(50*t_sliding + 10*t_global(context))/32`; the measured attention is added to c32 linears+head `0.22476958992984145` and the analytical KV floor is not added again.
5. The conditional residual program is fully staged before create, uses actual pinned consumers and exact source-derived counts/shapes, avoids fused-work double counting, and runs sequentially on the retained session only when every `RESIDUAL_OPS_TRIGGER` term passes within ten minutes. Trigger failure causes immediate cleanup.
6. One allocation/no paid repair, 30 provider minutes/0.5 H200-hours/$1.50/100-GiB limits, durable owner plus independent watchdog, full create-to-cleanup cost accounting, atomic retrieval, typed zero-resource cleanup, and fail-closed pre-GPU/zero-row handling.
7. Manifest hashes cover the actual transitive lifecycle/program bytes the durable process will consume; reject mutable path-only assurances and stale cross-project runners.

Write `AUDIT.json` with individual checks, concrete evidence paths/hashes/line references where practical, and one terminal: `pass_independent_behavioral_audit`, `fail_closed_before_create`, or `not_ready_no_provider_opinion`. A pass is advisory and cannot authorize spend by itself.

## Budgets

- Wall clock: 20 minutes including at most 15 minutes bounded local-file wait.
- Compute: 1 local CPU-hour; no GPU.
- Storage: 128 MiB retained plus 64 MiB temporary.
- Spend: `$0`; provider access/mutation forbidden.
