# Gemma 4 H200 GeluMul → dynamic-FP8 quantization fusion

## Question

Can the exact pinned Gemma 4 31B decode MLP path fuse the `GeluAndMul`
producer directly into the dynamic per-token E4M3 quantized input consumed by
the down projection, preserving the consumer's scale convention while
eliminating the intermediate BF16 write/read and one launch?

## Why it matters

The campaign's fixed qualified H200 denominator is
`0.625149101968745 s/request` and the target is
`0.500119281574996 s/request`. At c32 decode, the exact gate/up output is
approximately `[32, 43008]`; `GeluAndMul` produces `[32, 21504]`, which is
immediately quantized for the FP8 down projection. A producer-consumer fusion
could remove roughly 2.6 MiB of compulsory BF16 traffic per invocation plus a
launch, but only if the pinned v0.5.13 source actually has this adjacency and
the fused scale/orientation contract remains legal.

## Scope and evidence contract

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: pinned SGLang v0.5.13 source used by the campaign.
- Workload: exact c32 mixed endpoint geometry.
- Accelerator target: NVIDIA H200 SXM / SM90.
- Producer: the production gate/up `GeluAndMul` boundary.
- Consumer: the production dynamic per-token E4M3 quantizer and unchanged FP8
  down-projection GEMM.
- Strongest baseline: the exact pinned separate activation, quantization, and
  down-projection path.

Trace the loaded symbols, layouts, scale convention, strides, and graph
capture behavior. Build a typed opportunity register and one concrete
source-level fusion candidate or a typed analytical negative. A candidate
must include:

1. A deterministic CPU/reference oracle covering finite, zero, saturation,
   odd/tail, and representative exact-shape rows.
2. An H200 physical model for bytes, launches, grid waves, register/shared
   pressure, and a whole-request upper bound.
3. A minimal exact-consumer target-GPU contract with predicted counter
   movement and a falsifier.
4. A direct path to component timing and then the fixed-denominator endpoint.

Write the decision to `MECHANISM_TERMINAL.json`. A lower-fidelity pass may
promote the exact H200 measurement contract but cannot approve performance or
endpoint transfer.

## Budget and boundaries

- Researcher profile: `deep`.
- Wall time: 45 minutes.
- GPU/provider spend: `$0`; do not claim a bench or invoke CUDA.
- Do not inspect or depend on the R5 fixed-floor project or its artifacts.
- Do not create, delete, or mutate provider resources.
- Do not substitute a generic fusion proposal, SM120 result, or synthetic
  layout for the exact pinned producer and consumer.

Use `$researcher`, `$kernel-research`, and `$experiment-run`.
