# Research log

## 2026-07-29T03:23Z — exact M32 hot-block boundary

Question: can SM120 remove recurring launch, host-dispatch, or synchronization
work across the pinned stock post-attention residual/RMSNorm, dynamic
per-token FP8 quantizer, gate-up GEMM, BF16 cast, and first BF16 consumer?

Action:

- Bound Gemma 4 revision `b9ea41a...` and SGLang `28b095c...`.
- Materialized the layer-0 source component, pinned runtime sources, current
  SGLang/vLLM support snapshots, and the retained exact endpoint consumer
  audit under this project.
- Implemented `sm120_hotblock_taskgraph.py`, a fixed M32/K5376/N43008
  standalone CUDA Graph entrypoint using the stock
  `fused_add_rmsnorm`, `sglang_per_token_quant_fp8`,
  `fp8_scaled_mm`, and `GeluAndMul` calls.
- Added a target-SM120 bitwise oracle over normalized BF16, activation E4M3,
  FP32 activation scale, BF16 residual, BF16 GEMM output, and BF16 GELU/mul
  output before any timing.

Evidence:

- Measured offline: 23 project-local hashes and all required source fragments
  verify. The retained endpoint audit records gate-up input `[32,5376]`,
  weight `[5376,43008]`, activation scale `[32,1]`, weight scale `[1,43008]`,
  and BF16 output.
- Source-backed: the pinned M32 SM120 path is four ordered stock nodes. Batch
  size 32 is in SGLang's default decode graph set, and the pinned runner
  captures the whole model forward and calls `graph.replay()`. Current
  SGLang and vLLM retain equivalent full-decode graph ownership.
- Derived: one c32 batch makes `60 * 358 = 21,480` selected calls, or `671.25`
  calls per completed request. The no-cache-credit stock traffic model is
  240,683,776 bytes/call, 5,169,887,508,480 bytes/c32 batch, and
  161,558,984,640 bytes/request.
- Inferred, not measured on GPU: standalone replay can collapse four
  Python-level submissions to one, but a child graph inside the production
  outer graph removes zero endpoint launches, synchronizations, or bytes.

Interpretation: the entrypoint is working and offline-describable, but its
only valid runtime boundary is strictly contained by the existing full decode
CUDA graph. CUTLASS, cuBLASLt, and CUDA programmatic dependent launch expose
no stock-semantics cross-operator primitive that deletes a surviving
production boundary.

Decision: `typed_none_no_non_overlapping_sm120_runtime_boundary`. No GPU was
claimed, no provider operation occurred, no scientific sample was consumed,
and project spend remains `$0.00`. Reopen only if an exact RTX PRO 6000 trace
shows M32 decode outside the full graph or a stock host synchronization
between these nodes.
