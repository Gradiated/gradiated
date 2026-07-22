# Research log

## 2026-07-22 — activated

Opened as an independent stackable lane from measured quantization plus normalization/activation work. The project should reach an exact H200 component measurement quickly and proceed to an endpoint pair when stable.

## 2026-07-22 — exact gated-activation fusion implemented; H200 pool boundary

- **Question:** Which actual dynamic-FP8 producer adjacency is both highest-relevance and coherently fusible on the retained v0.5.13 stack?
- **Action:** Joined the pinned Gemma3MLP/FP8 sources to the residual-profile CUDA stream, implemented `fused_gelu_tanh_mul_quant_kernel`, connected its prequantized output to the unchanged CUTLASS down GEMM, built the exact M=32/M=2048 numerical/timing consumer and the conditional paired c32 owner, and materialized all 62,578,655,208 checkpoint bytes plus retained stack bytes project-locally.
- **Evidence:** [Measured] GELU(tanh)-and-mul is 0.214656804 s/3,660 launches; its immediately adjacent down-projection per-token quantizer is 0.185469039 s, 57.3504% of dynamic-quant time. [Derived from measured grid geometry] shared-memory fusion removes 3,660 launches and 944,006,676,480 BF16 HBM bytes in the captured window. `ADJACENCY.json` and `GPU_INPUT_MANIFEST.json` bind the evidence and runnable bytes. Python/shell/DevEx checks pass. The atomic H200 claim returned `no available GPU bench matches this project`; CUDA/scientific invocation remains false and spend is $0.
- **Interpretation:** Gated activation is preferable to norm fusion because its BF16 output has exactly one consumer and the stock down GEMM already accepts the candidate's per-token E4M3 bytes/scales. Target timing remains unmeasured; the pool result is an external hardware boundary, not evidence for or against the kernel.
- **Next:** After the simultaneous-ready partitioned-attention lane gets first use of the shared v0.5.13 kernel H200, run `run_bench_owner.py`; promote a component-positive result directly to the single stacked endpoint pair under the same claim.
