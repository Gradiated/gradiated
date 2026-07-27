# H200 fixed-floor cross-operator executor

## Question

Can one source-complete, exact-consumer cross-operator intervention reduce a
decision-bearing part of Gemma 4 31B's measured non-FP8-linear
`0.45975358056249493 s/request` floor, rather than trying to compress FP8
weights whose lossless entropy is already too high?

## Why this matters

The exact full-checkpoint Huffman result is a typed negative: even with a free
decoder, its measured `0.8357700419` stream ratio yields
`0.5979862024 s/request`, above the locked campaign target
`0.5001192816 s/request`. Its deliberately favorable bound leaves only
`0.0403657010 s/request` for all FP8-linear work at the target, so a credible
route must also attack the measured fixed runtime floor. This project is
materially independent of the 55-local/5-global endpoint proxy and of further
lossless representation work.

## Scope and evidence

Use `$kernel-research`. Bind the exact model revision
`b9ea41a2887d8607f594846523f94c6cc75ac8a4`, exact c32 workload, pinned
SGLang v0.5.13 source, and H200. Start from:

- `../gemma4_h200_lossless_fp8_entropy_gemm/LOSSLESS_FP8_ENTROPY_GEMM_OFFLINE_TERMINAL.json`
- `../gemma4_h200_dense_fp8_linear_schedule/inputs/evidence/ATTRIBUTION.json`
- `../gemma4_h200_dense_fp8_linear_schedule/inputs/evidence/FP8_LINEAR_SHAPE_MAP.json`

Within 75 wall-clock minutes, reconstruct the non-overlapping source and
producer/consumer path behind the largest actionable portion of the fixed
floor. Select exactly one boundary, state its physical hypothesis, and
implement a source-complete exact-shape consumer intervention. Favor an
existing CUDA/CUTLASS/SGLang primitive when it covers the semantics. Candidate
boundaries may span recurring RMSNorm, dynamic-FP8 quantization, residual,
attention/MLP handoff, sampling, or scheduler/graph synchronization, but the
evidence—not the label—must select the boundary.

Persist `FIXED_FLOOR_CROSSOP_OFFLINE_TERMINAL.json` with direct input/source
hashes, exact shapes/layouts/dtypes, current producer and consumer symbols,
baseline path, complete candidate source, correctness contract, useful
FLOPs/bytes/grid estimate, predicted counter movement, and a conservative
whole-request bound. A typed `none` is valid if no single source-complete
boundary can plausibly move the target.

## Budgets and prohibitions

- GPU/provider/SSH/endpoint spend: `$0`.
- Storage: at most 2 GiB.
- No checkpoint copying or mutation.
- No generic executor design, literature survey, flag sweep, profiler-only
  terminal, or second candidate.
- Do not claim the hybrid H200; a later director may admit one exact target-GPU
  call only from a source-complete positive terminal.

## Portfolio-changing result

A source-complete candidate with a credible positive complete-request bound
becomes the next checkpoint-free H200 exact-consumer arm. A typed `none` closes
only the selected fixed-floor boundary and redirects the portfolio to another
runtime, hardware, or model/chip mechanism.
