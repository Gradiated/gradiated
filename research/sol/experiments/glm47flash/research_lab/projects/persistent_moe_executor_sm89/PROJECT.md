# Persistent MoE executor for SM89

## Decision question

Can one exact-model SM89 executor reduce GLM-4.7 Flash routed-MoE wall time by persistently scheduling or fusing routing/sort, grouped W4 expert work, and reduction without changing the 64 experts, top-4 routes/weights, routed weights, or shared expert?

Use scope-matched L40S evidence. `TRACE_BOTTLENECK_V13.json` is H100/SM90 and is not an attribution source here. The retained L40S V24R2/V25R1 evidence assigns `12.374%` of c16 wall time to fused MoE and `3.177%` to routing/sort; these are summed work shares, not critical-path proof. At c16/c32 there are 64/128 routed assignments per layer against 142 SMs, making tiny-M scheduling the concrete target.

## `$0` executable gate

- Bind layers 1–46 and the exact c16/c32 assignment geometry (64/128 assignments), with current packed W4 weights, routes, weights, top-4 aggregation, and shared-expert semantics unchanged.
- Build one bounded candidate: a persistent queue or fused routing/sort/grouped-W4/reduction executor. Do not build a general profiler/framework.
- Preserve SM89 legality, including at most 99 KiB shared memory per block, and record tile geometry, registers/shared memory where available, launches, useful bytes/FLOPs, warmup, p50/p95 elapsed time, and expert-M histograms.
- Emit a numerical oracle over adversarial and representative assignments, including duplicate/empty experts and route-weighted reduction. No silent fallback is allowed.
- Decide quickly: the campaign requires an `8.936%` c16 wall reduction to move the current full-depth reference to the robust endpoint. Perfect transfer therefore requires at least `2.349x` on combined MoE+routing work, or `3.77x` if only fused-MoE time changes.

A candidate below the applicable component floor closes. A pass only nominates one later full47 endpoint; it is not endpoint evidence and authorizes no provider work this cycle.

## Required artifacts

Within 1,200 seconds produce `gate.json`, `numerical_oracle.json`, candidate source, and a compile log. Label all extrapolation as derived and keep L40S and H100 evidence separate.

## Starting evidence

- retained L40S V24R2/V25R1 traces and reports
- `../expert_count_geometry/`
- `../l40s_layer_cache_profile/`
- `../../hardware/L40S.md`
