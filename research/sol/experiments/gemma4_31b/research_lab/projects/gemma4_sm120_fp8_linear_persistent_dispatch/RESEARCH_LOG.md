# Research log

## 2026-07-29 — exact sm_120 M32 gate/up grouped dispatch

Question: can one recurring decode-c32 dynamic-FP8 linear remove a real
sm_120 launch/dataflow boundary without changing SGLang's numerical contract?

Action: traced the pinned SGLang `v0.5.16` / `sglang-kernel 0.4.5` dense
Gemma 4 path from `pre_feedforward_layernorm` through online per-channel
weight FP8, per-token activation FP8, `sgl_kernel::fp8_scaled_mm`, its BF16
epilogue, and the bench-installed native `GeluAndMul` consumer. Implemented
`sm120_fp8_linear_persistent_dispatch::gate_up_m32`: one exact-shape CUDA
kernel fuses residual RMSNorm with BF16-rounded per-row E4M3 quantization,
then the same custom-op entrypoint calls the unchanged stock sm_120 GEMM.
The integration retains stock fallback for every other shape or layout.

Evidence: the exact boundary is `M=32, K=5376, N=43008`, activation scale
`amax(abs(BF16 row))/448`, weight strides `[1,5376]`, and FP32 per-output
weight scale. Across 60 layers and 358 c32 decode steps it occurs 21,480
times per batch, or 671.25 times per completed request. The candidate removes
one launch and 1,032,192 normalized-BF16 HBM bytes per call. Pinned CUTLASS
also falsified a scheduler-only candidate: its sm_120 `void` scheduler already
maps to persistent scheduling. No GPU was claimed, no SSH was attempted, and
spend is `$0.00`.

Interpretation: this is a source-complete offline candidate, not a performance
claim. The analytical sensitivity is only about 0.08–0.32% of the measured
2.2338-second endpoint, so one exact component run should decide it cheaply.
`SM120_FP8_LINEAR_PERSISTENT_DISPATCH_OFFLINE_RESULT.json` binds source
hashes, the build/run command, the bitwise producer/scale/residual/GEMM/
consumer oracle, and the auditable per-batch/per-request conversion.

Next move: keep the RTX bench behind
`gemma4_rtxpro6000_vllm_current_fp8_endpoint`. If the director later binds a
component run, execute the recorded sm_120 command in a fresh process and
require every oracle field before timing.
