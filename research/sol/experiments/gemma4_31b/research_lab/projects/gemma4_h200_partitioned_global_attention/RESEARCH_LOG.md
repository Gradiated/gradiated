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
