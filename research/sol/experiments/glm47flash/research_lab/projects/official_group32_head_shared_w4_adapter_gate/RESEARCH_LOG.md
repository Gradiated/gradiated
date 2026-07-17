# Research log

## 2026-07-16 — Director opening handoff

Use the official compressed-tensors group-32 producer and a fresh-process actual `ParallelLMHead`/shared-linear consumer. The former roots are quarantined and may not be repaired. This is one terminal `$0` implementation gate: actual producer/consumer readiness nominates the full47 endpoint; a precise execution boundary or any contract failure closes without another validation ladder.

## 2026-07-16 — OFFICIAL_SELECTIVE_W4_RUNTIME_CLOSE_CUDA_KERNEL_SELECTION_BOUNDARY

Question/action: executed the one fresh pinned-image gate with the only permitted adapter: before the consumer process imports vLLM, its installed compressed-tensors selector is changed from `LinearBase` to `(LinearBase, ParallelLMHead)`. The candidate config adds only `ParallelLMHead` as a W4 target and removes ignores only for the 139 named serving tensors. The process initializes a one-rank CPU test group and constructs the exact `[154880, 2048]` `ParallelLMHead` so vLLM invokes the existing `CompressedTensorsLinearMethod.create_weights` / `CompressedTensorsWNA16.create_weights` path.

Evidence: [`OFFICIAL_GROUP32_ADAPTER_GATE.json`](artifacts/official_group32_adapter_gate/OFFICIAL_GROUP32_ADAPTER_GATE.json) retains the exit-1 diagnostic. Actual head construction reaches `choose_mp_linear_kernel`, which rejects every WNA16 backend because the fresh process has no CUDA (`MarlinLinearKernel cannot implement due to: Marlin only supported on CUDA`; device capability is `-1`). Thus this is not a source-presence result: parameter registration stops before producer bytes can load, post-load/repack can run, or the actual logits/shared-sum consumer can execute. No BF16 duplicate/fallback was introduced because the WNA16 registration fails before a layer state exists. No checkpoint mutation, GPU/provider/controller, or spend occurred.

Interpretation/next move: terminal close under the explicit `$0` contract. The selector adapter itself is narrow, but its only credible target execution requires CUDA. It does not nominate the full47 c16/c32 endpoint and must not acquire a successor ladder; only separately authorized CUDA target execution could test registration/load/post-load/logits and native shared semantics.
