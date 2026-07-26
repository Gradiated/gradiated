# Research log

## 2026-07-26 — exact M384 MLP seam returns typed none

Question: which highest non-attention producer/consumer boundary in the
current c32 target-verification trace can support a persistent 10%-class
executor?

Action: materialized the exact trace and prior H200 real-down-consumer
terminal under this project. The highest coherent non-attention block is the
60-layer gate/up GEMM, SwiGLU, dynamic E4M3 quantization, down GEMM, and
residual chain at target shape `M=384`. Implemented the real
SwiGLU-to-quantized-activation producer and an exact runner that feeds its
`[384,21504]` E4M3 output and per-row FP32 scales to the unchanged
column-major `[21504,5376]` `fp8_scaled_mm` consumer. The producer repairs the
prior implementation's extra BF16 rounding.

Evidence: the trace contains exactly `15*60=900` same-stream MLP chains.
Their full interval is `337.997877 ms` (`14.2306%`) but the gate/up and down
GEMMs consume `311.951989 ms` (`92.2941%` of the block). Even deleting the
entire implemented SwiGLU-plus-quant seam, including all launch gaps, saves at
most `17.898803 ms` of the `2375.141908 ms` verification window:
`0.753589%`. The implementation removes 900 launches and at most
`44,590,694,400` BF16 materialization bytes in the trace. The exact-M384 CPU
rounding fixture matches stock on all `8,257,536` BF16 elements with finite,
nonzero output; the rejected extra-rounding form differs on `2,053,347`.

Interpretation: this is a typed physical negative,
`measured_removable_wall_share_below_target`. The optimistic
verification-window bound is already `13.2698x` too small for 10%, and a
whole-request bound can only be lower. No GPU claim, CUDA sample, provider
mutation, or spend occurred; the project status forbade a claim and the only
live H100 was reserved and claimed by the paged-KV recovery.

Next: no replay or GPU nomination for this mechanism. Return the typed none to
the director; retain the corrected source and exact consumer runner only as a
small stackable candidate if a future project has a lower success threshold.
