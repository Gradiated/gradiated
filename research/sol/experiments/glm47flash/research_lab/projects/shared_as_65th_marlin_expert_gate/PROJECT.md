# Shared expert as the 65th fused Marlin expert

## Decision question

Can the exact always-active shared expert be appended as a weight-1 65th assignment in the stock expert-sorted W4 Marlin path, preserving 64 logical routed experts and top-4 semantics while eliminating separate shared-branch launches and accumulation?

The shared expert has the same 2,048↔1,536 gate/up/down geometry as each routed expert and consumes the same layer input. Once represented with official W4, it is an always-active dense-M expert: one extra assignment per token, independent of the four routed choices. Fusing it with routed work attacks hardware realization without deleting weights, experts, routes, or the shared branch.

## `$0` contract

Within 900 seconds, use pinned vLLM/compressed-tensors source and retained L40S traces only. Use no checkpoint mutation, GPU/provider, install, or controller.

- Bind stock `moe_align_block_size`, WNA16 Marlin expert-count/layout constraints, gate/up and down launches, route-weighted reduction, and the current separate shared-expert path.
- Construct a source-bound descriptor fixture that appends expert ID 64 with weight 1 for every token while preserving the original top-4 IDs/weights. Prove exact SwiGLU, down projection, shared-plus-routed sum, dtype, and deterministic duplicate/empty/skew cases.
- Prove 65-expert packed layout and SM89 kernel legality without scalar fallback or broad loader changes. Account padded rows, launch count, workspace, and added descriptor/reduction work at c16/c32.
- From timestamped trace spans or a conservative dependency model, bound only removable sequential shared-branch wall time; do not use summed overlapping kernel time as an Amdahl coefficient. Close if exact attribution is absent or the perfect overlap/fusion ceiling cannot reach `606.355 tok/s` from a future scope-compatible full47 baseline.

Return `CONDITIONAL_FUSION_READY` only if source/shape/numerical legality and a conservative endpoint interval survive. It then waits for an official-W4 full47 baseline; it does not nominate GPU alone. Otherwise return `MECHANISM_CLOSE`, `RUNTIME_CLOSE`, or `ECONOMIC_CLOSE`.

## Starting evidence

- `../full47_group128_w4_codesign_gate/`
- `../expert_sorted_marlin_moe_sm89/` stock sorting/launch evidence
- retained L40S V24R2/V25R1 traces
- `../../hardware/L40S.md`

## Cycle 127–128 direct component reopen

The later exact unchanged-stock c32 endpoint is `609.606365 tok/s`, above this project's preregistered `604.02 tok/s` conditional-reopen threshold. Reopen the existing project for one direct component measurement, not another source/readiness gate.

Cleanup is now authenticated zero. Use the proven supplied-script controller and pullable vLLM v0.15.0 image for one L40S create (`$0.55`, 1,800 seconds, no retry). Stage only one exact layer, roughly `347 MiB`, from the stock root `/root/.cache/glm47flash-awq-ab31d120` and official selective-W4 root `/root/.cache/glm47flash-awq-full47-official-head-shared-w4-7ab75a5258cc`; do not transfer or load full47. In the same researcher turn, freeze and test the exact benchmark, remote wrapper, spec, one-layer payload manifest, source hashes, wrapper CLI, `sweep_pass` negative-result retrieval, SSH, price/orderability, unique names, and zero inventory, then launch. A pre-create failure is a typed terminal close, not readiness. Preseed the controller output's `repair-decision.json` with `{"action":"teardown"}` so any pre-artifact error tears down immediately rather than consuming its generic 600-second hold.

The exact config has `norm_topk_prob=true` and `routed_scaling_factor=1.8`. Form candidate IDs `[r0,r1,r2,r3,64]` only after top-4 normalization, with weights `[1.8*w0,1.8*w1,1.8*w2,1.8*w3,1.0]`, and apply no outer routed scale. This must equal stock semantics `1.8 * routed + shared`; appending weight 1 under the unchanged outer `1.8` is invalid.

Measure randomized, warmed CUDA-event wall trials across all stream joins for three exact c32 arms:

- `A0` current-stock economic comparator: routed group32-W4 Marlin top4 plus the exact BF16 shared MLP through pinned vLLM's actual auxiliary-stream `SharedFusedMoE` path, including clone, waits, and final add;
- `A1` representation-matched comparator: the same routed path plus the identical official group32-W4 shared payload executed separately through native dense WNA16 Marlin, with actual overlap and final sum;
- `B` candidate: one E=65/topk=5 fused WNA16 Marlin call using the same routed payload and byte-identical shared W4 codes/scales as A1.

Do not implement A0 or A1 as sequential summed kernels. Pinned `fused_marlin_moe` selects `block_size_m=8` for both M32/top4/E64 and M32/top5/E65: shared ID64 adds 32 valid rows with zero shared-row padding. The old block-64 fixture is historical semantic evidence only, not target-runtime geometry.

Use balanced and skew routes for performance and balanced/duplicate/empty/skew routes for semantics. Hash raw codes/scales and prove B's expert-64 slot derives from A1 bytes. Compare B to A1 with preregistered BF16-aware max and normalized-L2 tolerances; separately report A1/B error against A0's BF16 shared output as a quality proxy. Require profiler-confirmed Marlin kernel names/counts, source hashes, launch grid/block, workspace, and p50/p95 wall time; report registers/shared/spills/occupancy when tooling exposes them, but do not invent or make unavailable counters a gate.

Return `SHARED65_COMPONENT_PASS` only if `A0/B >=1.63x` at p50 on both balanced and skew c32 routes, B p95 is no slower than A0, A1/B isolates the fusion delta, and every semantic/numerical/kernel-identity gate passes. A scientifically valid negative must still emit `sweep_pass:true`, `component_pass:false`, and a typed close so the controller retrieves it. No full47 integration packet can be ready through an existing content-bound retained path within ten minutes, so retain nothing and clean normally. Do not return readiness, repair, retry, or create a successor.
