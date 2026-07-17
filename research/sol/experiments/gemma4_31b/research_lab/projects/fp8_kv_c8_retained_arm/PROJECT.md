# FP8-KV c8 retained-session arm

## Question

Can current pinned vLLM FP8 KV cache make the exact Gemma 4 31B primary workload fit and complete at c8 on one L40S when BF16-KV c8 is 0.342 GiB outside the conservative bound, without corrupting deterministic text or worsening sustainable cost?

## Why this is the adjacent arm

The paid online-FP8 weight arm must first reach CUDA through the proven shared controller. Independent `$0` evidence now bounds BF16-KV totals at 42.198 GiB for c4 and 45.046 GiB for c8 against 44.704 GiB usable capacity. Halving KV bytes is therefore directly coupled to the measured capacity/economic decision, whereas generic async scheduling does not solve the c8 residency discontinuity. Checkpoint and image setup will dominate scored time, so this project must make one same-session arm start-ready without touching the live owner.

## Immediate `$0` experiment

Use the pinned runtime image/source identities, exact hybrid-KV geometry, `SATURATION_GATE.json`, and current first-party vLLM code already captured in the workspace. Do not query prices, download weights/images, mutate a provider, edit the paid owner, or wait for it.

Produce one `FP8_KV_ARM.json` that:

1. Binds the exact supported Ada launch delta and scale behavior for FP8 E4M3 KV in the pinned runtime. Distinguish static/default scales from calculated scales and fail closed if current Gemma4 support cannot make the scale identity explicit.
2. Recomputes c8 and 10K residency with exact K/V bytes plus scale/workspace allowance. State the guaranteed-fit and runtime-dependent cases; do not transfer throughput from another model.
3. Renders the same-session server restart and complete c8 workload using the paid project’s shared controller, checkpoint/image content, raw-output capture, deterministic token-ID comparator, telemetry, and cleanup. No new provider create, checkpoint download, image pull, owner, or watchdog is allowed.
4. Names one trigger: stock online-FP8 weights pass raw correctness and c4 completes, while BF16-KV c8 is measured memory-limited or c4 misses the sustainable-cost hurdle. The packet must be start-ready within ten minutes of that typed result. If the trigger is false, the paid owner cleans up immediately.

This is an explicitly non-promoted representation intervention. Any token mismatch, incoherence, scale ambiguity, reload, or incomplete request kills the arm. Production eligibility still requires later representative quality and feature validation.

## Budgets

- Wall clock: 45 minutes.
- Provider mutation/spend: prohibited (`$0`).
- Compute: at most 2 local CPU-hours; no CUDA.
- Storage: 512 MiB.
- Artifacts: `FP8_KV_ARM.json`, `DECISION.md`, and only the minimal pinned source excerpt/hash needed to bind the launch.
