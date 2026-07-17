# Research log

No researcher result yet. Start from the exact model architecture and current c16 telemetry; produce an executable cost proxy or falsifier rather than a generic design survey.

## 2026-07-15 — Exact-config c16 MoE proxy screen

**Question.** Can the project’s two smallest MoE changes independently, or together, plausibly cross the committed-price c16 cost target before recovery training?

**Action.** Derived a two-replicate, exact-config proxy from the AWQ config and retained L40S decode traces. The config has 46 MoE layers, four routed experts plus one shared expert per token, each at width 1,536. The proxy credits only the lower observed fused `marlin_moe` share for reducing routed top-k and the lower observed standard-Marlin plus explicitly shared residual shares for removing the shared expert; it credits no routing, attention, KV, or overlap benefit. Full inputs, hashes, formulae, and economics are in [ADAPTIVE_MOE_C16_PROXY_2026-07-15.json](artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json).

**Evidence.** At the shared $1.10/L40S-hour planning rate, measured c16 is $0.570827/M output and needs a 9.955% nonoverlapped wall-time reduction to reach $0.514/M. Top-3, top-2, and no-shared alone have only 3.094%, 6.187%, and 7.101% summed-trace ceilings, respectively. The combined top-2-plus-no-shared ceiling is 13.288%, corresponding ideally to 617.315 tok/s and $0.494975/M; the ceiling is not a wall-time or quality result.

**Interpretation and next move.** Close each individual minimal mechanism against the 10% target. The combined semantics-changing candidate is narrowly worth exactly one matched stock-c16/candidate L40S session if the existing director mutation gate is opened: it has only 3.333 percentage points of idealized wall-time headroom, so any material transfer loss closes the route. Require at least 594.46 output tok/s, complete exact-geometry requests, and retained quality diagnostics; do not infer production quality from the proxy.

## 2026-07-15 — Admitted-session launch-contract falsifier

**Question.** Can the Cycle 35 L40S MoE arm be safely dispatched through the named shared launcher?

**Action.** Inspected the pinned local vLLM image and the exact current launcher before provider create. The image’s GLM source has the required separate levers (`top_k=config.num_experts_per_tok` and a non-null `shared_experts` path); a source-pinned top-2/no-shared structural patch compiled locally. The patch is not promoted as a load or GPU result because shared checkpoint weights also require an explicit, narrow skip rule.

**Evidence.** [MOE_RUNTIME_AND_LAUNCH_CONTRACT_2026-07-15.json](artifacts/MOE_RUNTIME_AND_LAUNCH_CONTRACT_2026-07-15.json) binds the image and source hashes. More importantly, the director-named `vllm_smoke_control.py` is currently hard-wired to `gpu-h100-sxm`, `1gpu-16vcpu-200gb`, and $3.85/hour; its 3,900-second derived exposure exceeds $4.19, not the admitted $1 L40S envelope. It has neither an MoE-patch staging path nor the required execution-equivalent no-mutation precreate mode.

**Interpretation and next move.** No provider resource was created: dispatch would violate the project’s immutable hardware/budget contract and could not test the proxy. This is a launch-contract blocker, not negative MoE evidence. Restore or identify the last L40S-capable vLLM path, add the single source-hashed top-2/no-shared switch plus a narrow skipped-shared-weight rule, and prove its durable no-mutation service envelope before using the one admitted allocation.

## 2026-07-15 — Source-pinned top-2/no-shared runtime switch

**Action and evidence.** Implemented [moe_top2_no_shared_patch.py](moe_top2_no_shared_patch.py), which fails closed on the two exact pinned vLLM GLM source hashes, changes `top_k` only when `GLM_MOE_TOP2_NO_SHARED=1`, suppresses separate shared-expert construction, and skips only `mlp.shared_experts.*` checkpoint tensors under that switch. The exact pinned container copied, patched, and Python-compiled both source files; hashes and output are retained in [MOE_PATCH_CONTAINER_TEST_2026-07-15.txt](artifacts/MOE_PATCH_CONTAINER_TEST_2026-07-15.txt).

**Interpretation and next move.** The scientific intervention now has a source-bound, locally executable implementation, but no model load/GPU result. Integrate this one staged input into the Cycle 36 explicit L40S-AWQ profile, perform its required durable no-mutation terminal, and immediately dispatch the admitted stock/candidate session if it passes.
