# Research log

## 2026-07-15 — exact layer/window bound and source-bound fixture

**Question.** Can periodic full-context MLA layers with 1,024/2,048/4,096-token local windows clear the exact 8,192-input/1,024-output L40S promotion gate?

**Action.** Derived decode context work over positions 8,192..9,215 for the exact 47-layer, rank-512+64-rope geometry. Screened zero-based global layers every fourth (`g=12`) and every eighth (`g=6`). Used the retained MLA split calibration (14.35% component reduction → 1.05% endpoint reduction, transfer factor 0.07317) as a conservative semantics-changing proxy. Implemented and ran `source_bound_window_fixture.py`, which checks global layers retain positions 0..9,215, local W=1,024 layers retain exactly 8,192..9,215, absolute positions remain correct, local KV state is bounded at 1,024 tokens, and stock full-context mode is unchanged.

**Evidence.** [`layerwise_sliding_window_bound.json`](layerwise_sliding_window_bound.json) contains exact work/KV accounting. The strongest screened policy is W=1,024 with every-eighth global: 76.97% attention-work reduction, 5.63% conservative endpoint-reduction bound, and 0.104 GiB endpoint MLA KV versus 0.465 GiB stock for one 9,216-token sequence. Every-fourth global gives 65.71% work reduction and 4.81% endpoint bound. W=2,048 and W=4,096 are weaker (4.88% and 3.38% endpoint bounds for every-eighth global). The retained calibration’s all-local ceiling is 7.32%, still below the 9.955% required non-overlapped wall reduction. The fixture returned `status=pass`; `py_compile` passed.

**Runtime boundary.** The retained pinned vLLM 0.15.0 v24r2 artifact reports `sliding_window="None"` and uses `unified_mla_attention`; no per-layer GLM window policy is present in the source-bound serving configuration. Supporting this would require a bounded MLA mask/KV-state runtime change, not an existing launcher setting. This is an implementation boundary, not an economic rescue.

**Decision.** `CLOSE_SLIDING_WINDOW_NO_GPU`. No paid or exact-shape proxy is nominated: all explicit policies miss the gate, and even the calibrated zero-cost ceiling misses it. Quality effects remain deferred and unmeasured.
