# Research log

Opened from the 2026-07-16 user-directed architecture/kernel pivot. Optimize the measured execution geometry, not nominal FLOPs alone.

## 2026-07-16 — Director executable gate

Correct the evidence base: the V13 bottleneck trace is H100/SM90, while retained L40S evidence places fused MoE at 12.374% and routing/sort at 3.177% of c16 wall time. This cycle is `$0` and provider-prohibited. Build one exact-semantics executor for layers 1–46 and c16/c32's 64/128 assignments, then require at least `2.349x` combined MoE+routing speedup or `3.77x` if only fused-MoE work changes. Below the applicable floor, close; above it, nominate a later endpoint only.

## 2026-07-16 — Offline executor gate executed

**Action.** Added one SM89 persistent assignment-queue W4 candidate in `persistent_moe_executor_sm89.cu` and executed `run_offline_gate.py`. The source binds the current 2,048×1,536 group-32 packed layouts, 64 experts, top-4 route weights, layers 1–46, and c16/c32's 64/128 assignments. The oracle reads current checkpoint W4 samples and checks direct versus grouped queue reduction for duplicate-expert c16, empty-expert balanced c16, and skewed c32 routing.

**Evidence.** `numerical_oracle.json` passes all three cases (maximum difference `1.7763568394002505e-15`, tolerance `1e-12`). `compile.log` records the typed `nvcc`-absent boundary (exit 127); this host also has no CUDA device. `gate.json` records zero dynamic shared memory (under SM89's 99 KiB/block limit), but registers, launch realization, elapsed p50/p95, and speedup are unavailable.

**Decision.** No endpoint nomination and no provider mutation. The semantic gate passes, but no component measurement can be inferred; the director-owned floors remain `2.349x` combined MoE+routing or `3.77x` fused-MoE-only. Reopen only on an SM89 build/measurement host.

## 2026-07-16 — MECHANISM_CLOSE

Source audit shows the candidate does not test the declared mechanism: assignments are not expert-grouped, routing/sort is precomputed rather than fused, full expert weights are scalar-loaded and dequantized per assignment without a Tensor-Core W4 path, and BF16 output is mutated through an invalid float atomic pattern. The CPU oracle executes none of this code and proves only queue-order equivalence. Close without spending compilation or GPU time. A separate stock-Marlin expert-sorted scheduling project may test the exact-weight hypothesis without inheriting this source.
