# Research log

## 2026-07-22 — activated

Opened as an independent stackable lane from measured quantization plus normalization/activation work. The project should reach an exact H200 component measurement quickly and proceed to an endpoint pair when stable.

## 2026-07-22 — exact gated-activation fusion implemented; H200 pool boundary

- **Question:** Which actual dynamic-FP8 producer adjacency is both highest-relevance and coherently fusible on the retained v0.5.13 stack?
- **Action:** Joined the pinned Gemma3MLP/FP8 sources to the residual-profile CUDA stream, implemented `fused_gelu_tanh_mul_quant_kernel`, connected its prequantized output to the unchanged CUTLASS down GEMM, built the exact M=32/M=2048 numerical/timing consumer and the conditional paired c32 owner, and materialized all 62,578,655,208 checkpoint bytes plus retained stack bytes project-locally.
- **Evidence:** [Measured] GELU(tanh)-and-mul is 0.214656804 s/3,660 launches; its immediately adjacent down-projection per-token quantizer is 0.185469039 s, 57.3504% of dynamic-quant time. [Derived from measured grid geometry] shared-memory fusion removes 3,660 launches and 944,006,676,480 BF16 HBM bytes in the captured window. `ADJACENCY.json` and `GPU_INPUT_MANIFEST.json` bind the evidence and runnable bytes. Python/shell/DevEx checks pass. The atomic H200 claim returned `no available GPU bench matches this project`; CUDA/scientific invocation remains false and spend is $0.
- **Interpretation:** Gated activation is preferable to norm fusion because its BF16 output has exactly one consumer and the stock down GEMM already accepts the candidate's per-token E4M3 bytes/scales. Target timing remains unmeasured; the pool result is an external hardware boundary, not evidence for or against the kernel.
- **Next:** After the simultaneous-ready partitioned-attention lane gets first use of the shared v0.5.13 kernel H200, run `run_bench_owner.py`; promote a component-positive result directly to the single stacked endpoint pair under the same claim.

## 2026-07-22 — retained H200 owner launched

- **Question:** Does the bound GELU(tanh)-and-mul-to-dynamic-FP8 fusion pass the exact H200 component gate and, only if positive, improve the contemporary c32 endpoint?
- **Action:** Atomically claimed `h200-residual-kernel-e00fpjxk4ww2g49apd` at `2026-07-22T12:27:50Z`, verified the project-local bound snapshot and owner syntax, and started `gemma4-fp8-dataflow-fusion-20260722t122858z.service` with a 150-minute absolute owner window. Artifact root: `artifacts/h200-fp8-dataflow-fusion-20260722t122858z/`.
- **Evidence:** [Measured operational state] the user service is active (`MainPID=3285174`). The owner is performing its required remote size/hash reconciliation and will stage only missing or mismatched immutable files before its first CUDA call. No component or endpoint CUDA/scientific invocation has started, and no project spend is yet measured.
- **Interpretation:** The scheduled experiment is now durably executing on the shared bench; the first decision-bearing result will be the exact component terminal, with the endpoint pair conditionally chained in the same retained claim.
- **Next:** Attach only to reconcile the durable terminal or a `REPAIR_READY.json` diagnostic; do not cold-restart the owner or replay any completed stage.

## 2026-07-22 — pre-CUDA SSH repair

- **Evidence:** [Measured] `h200-fp8-dataflow-fusion-20260722t122858z.service` reached the remote identity operation but received `Permission denied (publickey)` before remote mutation, CUDA, or scientific invocation. The bench cloud-init authorized-key fingerprint is `SHA256:g5df+MD3rnTnW0lmqaEvI+esJ+H14qj/g7NeeJgDBXg`; the owner had selected a different key. `OUTER_FAILURE.json`, `remote-identity.stderr`, and `outer-events.jsonl` preserve the diagnostic.
- **Repair:** Bound the owner to the matching existing provider key and corrected its pool release call to provide a JSON path, then rebound the owner hash in `GPU_INPUT_MANIFEST.json`. The intervention, workload, model, and acceptance gates are unchanged.
- **Next:** Start one replacement durable owner on the same claim and retry the identity/staging path only; the component arm remains unconsumed.

## 2026-07-22 — second pre-CUDA binding repair

- **Evidence:** [Measured] the replacement service was inactive and the warm kernel bench was available. Its retained stderr identifies `project_local_snapshot_invalid:run_bench_owner.py`; the newly patched owner was 17,340 bytes while the manifest still specified 17,238. No artifact directory, remote mutation, CUDA invocation, or scientific invocation was produced.
- **Repair:** Reclaimed `h200-residual-kernel-e00fpjxk4ww2g49apd`, updated only the owner byte count and manifest digest, and will launch a third bounded owner on the same model/intervention/workload/decision gates.
- **Next:** The first target-GPU CUDA component call remains the next decision-bearing action.

## 2026-07-22 — component arm consumed, consumer-layout failure

- **Action:** The repaired owner hash-reconciled and staged all `62,578,655,208` checkpoint bytes, all bound stack/program bytes, and the pinned v0.5.13 image on the warm H200. It then invoked the exact component container.
- **Evidence:** [Measured] `COMPONENT_INVOCATION_STATE.json` records `compile_started`, `candidate_cuda_started`, and `candidate_science_started` all true. The component failed at the pinned `fp8_scaled_mm` consumer: `RuntimeError: mat_b must be a column major tensor`; raw stderr hash `f00ce5e6…`. No numerical/timing rows or component terminal persisted. Exposure was `2088.937475 s`, conservatively `$1.427441` at `$2.46/hour`.
- **Interpretation:** This is a consumer-layout harness defect, not a fusion performance result. However, the candidate CUDA arm is consumed and its output was not persisted, so a consumer-only repair cannot complete without another candidate invocation. The no-retry contract therefore blocks replay; endpoint promotion did not occur.
- **Next:** Closed as `component_consumer_failure_after_candidate_cuda`; retain the warm bench state for the lab, but do not replay this candidate.

## 2026-07-23 — RMSNorm-to-FP8 real-consumer component negative

- **Question:** Can one shared H200 producer cover the pre-attention and fused-add pre-MLP RMSNorm paths, preserve BF16 residual state, and replace 7,320 of the exact profile's 14,640 standalone dynamic-E4M3 quantization calls with a positive endpoint bound?
- **Action:** Source-bound hidden width 5,376, BF16 inputs/residuals, per-token FP32 scales, E4M3 activations, layer-0 real QKV `[5376,16384]` and gate/up `[5376,43008]` column-major weights, and unchanged `fp8_scaled_mm`. Implemented `rmsnorm_quant_kernel<AddResidual>` and ran complete-output component pairs at M=32/118/1409/1631/2048 on `h200-sync-linear-e00vhh6h29fj68x91g`. The first owner hit measured pre-CUDA ENOSPC while copying the full snapshot; its temporary partial was removed and a 638,605,176-byte seven-tensor component snapshot derived from the already-verified project-local shard was transferred instead.
- **Evidence:** [Measured] The BF16 residual is bitwise equal at every shape and all values are finite. Plain QKV dequantized relative L2 is `0.000701–0.002190`; residual-fed gate/up is `0.014367–0.015340`, with consumer relative L2 `0.014561–0.015523`, so correctness fails. M=32 producers improve `0.030096→0.017376 ms` and `0.043984→0.025216 ms`, but dominant M=2048 regresses `0.037776→0.041200 ms` and `0.064128→0.073360 ms`; exact components similarly regress QKV `0.281008→0.294928 ms` and gate/up `0.692496→0.699312 ms`. [Derived from measured shape counts] the conservative saved bound is `0.00133632 s` per 23.038600455-second batch, only `0.00580035%`. The `14,640→7,320` call prediction and both bypass paths are mechanically proven. No c32 endpoint ran because the component gate failed. Artifacts: `artifacts/rmsnorm-fp8-iteration3-repair-20260723t1109z/TERMINAL.json`.
- **Interpretation:** The residual implementation normalized the BF16-rounded residual state; the pinned fused-add baseline emits that BF16 residual but normalizes the pre-rounding sum, explaining the scale/output error. Even the numerically closer plain path loses at the dominant prefill geometry, so this implementation has neither correctness nor a material endpoint case.
- **Next:** Close this RMSNorm-to-FP8 candidate without replay. Return to the director for a materially distinct mechanism; do not reopen the activation/down candidate or tune GEMMs. Conservative cumulative project exposure is `$2.512937207` (`$1.629740604` historical plus `$0.883196603` for all three iteration-3 claim intervals).
