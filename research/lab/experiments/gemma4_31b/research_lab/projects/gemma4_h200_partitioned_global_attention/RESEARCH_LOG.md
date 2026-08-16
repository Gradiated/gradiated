# Research log

## 2026-07-22 — activated

Opened from exact NCU evidence that the global head-512 path is register-residency limited. The immediate result is an exact-shape H200 implementation/measurement followed by one endpoint pair when the component mechanism passes; documentation alone is not progress.

## 2026-07-22 — exact component implemented; pool boundary

Question: can a value-accumulator partition or an L2-for-residency trade reduce the exact 255-register global kernel enough to justify endpoint promotion?

Action: materialized the pinned `extend_attention.py` bytes project-locally, implemented an exact 2048-token/32-Q-head/4-KV-head/head-512 CUDA benchmark with a full output-consuming control oracle and NCU consumer, and compiled bounded V-split/M/N geometries offline for sm90. The initial two-way V split was revised after its compiler result contradicted the causal requirement. The selected specialization leaves the proven 32x64 kernel unchanged and passes `maxnreg=128` only for Hopper global head-512, explicitly trading local-memory/L2 spills for two-CTA register residency.

Evidence: `artifacts/OFFLINE_COMPILE.json` is derived proxy evidence from Triton 3.7.1, not target-runtime evidence. Control compiled at 255 registers/thread, 102,400 B shared memory, 1,328/1,276 B spill store/load. Natural V-split candidates remained at 180-255 registers/thread; two-way split worsened spills to 1,812/1,512 B. The selected forced cap compiled at 128 registers/thread with the same 102,400 B shared memory and 4,250/4,100 B spill store/load, predicting two CTAs/SM by registers and shared memory without duplicated QK work. Four standard-library tests pass, including a numerical split-V identity oracle and both hash-bound source transformations. The exact pool claim returned `no available GPU bench matches this project`; no CUDA/scientific invocation or spend occurred (`artifacts/POOL_CLAIM_DIAGNOSTIC.json`).

Interpretation: direct two-way V partitioning does not reduce allocated registers in the proxy compiler and is not worth the first GPU arm. A forced register cap is the smallest exact realization of the measured causal trade; its extra spills make H200 component timing and L2/DRAM counters decisive.

Next: claim the first shared v0.5.13 H200, run `remote_component.sh` from the immutable project-local snapshot, and promote directly to the paired retained-stack endpoint only when the exact oracle, >=5% median latency reduction, <=128 registers/thread, and >=2 CTA residency gates all pass.

## 2026-07-22 — exact H200 component rejects forced residency

Question: does forcing the unchanged exact 32x64 global head-512 kernel to 128 registers trade spills for enough two-CTA residency to clear the preregistered 5% component gate?

Action: materialized the exact checkpoint and retained-stack bytes inside this project before the claim, then ran one retained owner on `h200-residual-kernel-e00fpjxk4ww2g49apd`. A lower-priority orphaned claim was corrected only after its two local failures proved pre-invocation and a direct healthy-guest probe proved `/home/glmrunner/gemma4-fp8-layer-fusion` absent. This project claimed at `12:49:46.784502Z`, hash-staged only the component inputs, pulled the pinned v0.5.13 image, ran the exact alternating timing/oracle plus one NCU capture, retrieved the compact/raw terminal set, and released ready at `12:55:29.015942Z`. Claim exposure was 342.222 seconds / `$0.233852`.

Evidence: the control median is `2.425440 ms`; `maxnreg=128` is `4.300480 ms`, a `-0.773072` reduction (77.31% slower). The oracle is exact (`max_abs_error=0`, all finite, allclose passes). NCU confirms the intended mechanism inputs—128 registers/thread and two CTA limits from both registers and shared memory—but shows `69.384687%` L2 throughput, `54.155986%` DRAM throughput, only `6.728070%` tensor activity, and a `4.554272 ms` captured kernel. The spill/L2 cost dominates the residency benefit. Durable evidence is `artifacts/FINAL_TERMINAL.json`; the verified raw bundle is `artifacts/remote-component/component-compact.tar.gz` at SHA-256 `c4f1939076a5bcac8e05167cb2478005289f3588711a9e00106966ca47933bed`.

Decision: reject `extend_attention_fwd.global_head512_maxnreg128`. The component gate failed, so the exact paired FP8+QKV+deferred-local-KV endpoint and checkpoint staging were not executed. No retry or successor in this project is admitted; the warm image/caches are released to FP8 layer-dataflow fusion.

## 2026-07-22 — portfolio-continuity continuation

The forced-register candidate is terminal, but the broader partitioned-dataflow hypothesis is not. Reactivated to implement one true multi-stage QK/softmax plus sliced-V realization whose kernel boundary actually ends the large accumulator live range. Do not retry `maxnreg`, BLOCK_M changes, or parameter sweeps.

## 2026-07-22 — true multi-stage dataflow rejects on exact H200

Question: can an explicit grouped-QK/causal-softmax boundary plus four independent width-128 value GEMMs end the head-512 accumulator live range and beat the pinned fused global-attention control?

Action: implemented `multistage.grouped_qk_softmax.sliced_v_4x128`, materializing FP32 scores/probabilities and concatenating four FP32 sliced-V results into the BF16 output. The durable owner waited behind the current-runtime claimant. That claimant's completed checkpoint producer had stopped before its remote worker because an unbound `.gitignore` made `rmdir` fail; the retained repair consumed the verified remote checkpoint in place without another bulk transfer. On its release, this project atomically claimed `h200-continuity-e00hzj9a8khp0fevy5`, ran the one exact component process, retrieved and verified the compact evidence, and released warm after 344.357 seconds. Incremental cost was `$0.235310`; cumulative project cost is `$0.469162`.

Evidence: at the exact 2048-token, 32-Q-head/4-KV-head, head-512 causal shape, the pinned control median is `2.437984 ms` and the multi-stage candidate is `2.562208 ms`, a `-0.050954` reduction (5.10% slower). The candidate also fails the preregistered numerical oracle: all values are finite, but `allclose(atol=0.005, rtol=0.005)` is false, with `0.171875` maximum and `0.00142872` mean absolute error. A post-terminal source audit identifies the scientific implementation defect: the measured `probabilities` path omitted the baseline's default `1/sqrt(512)` softmax scale, although the unexecuted paged endpoint path supplied it. The admitted invalid path is preserved and not replayed. The explicit dataflow materializes `1,375,731,712` bytes. The raw bundle SHA-256 is `816d76adce98a6c9fe963b2be86cd4f6af275cf6a480bd4cc69056152b13cd39`.

Telemetry audit: the NCU report is durable, but its selected launch is a 30.08-us elementwise `direct_copy` kernel rather than a sliced-V matrix multiplication. `artifacts/NCU_CAPTURE_AUDIT.json` therefore marks that counter gate inadmissible. This ordinary profiler-selection defect is not decision-bearing because the exact-shape latency gate independently rejects and the admitted bytes also fail the oracle; replay is not authorized after release to the next claimant.

Decision: reject the true multi-stage candidate and skip the paired endpoint. Close this lineage; a distinct successor would need to remove the 1.376-GB materialization burden and explain the numerical mismatch, not retune the already-rejected source or replay its telemetry consumer.
