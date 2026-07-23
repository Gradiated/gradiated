# Group-64 INT4 local KV on H200

## Question

Can one fixed signed-INT4 representation halve the compulsory KV-read traffic of Gemma 4's 50 local-attention layers while preserving the qualified E5M2 global path and producing a material exact-workload endpoint gain?

## Why this matters

The exact current-stack trace assigns `29.2729%` of wall time to attention/KV, and prior source-bound evidence assigns `15.3120%` to the 50 local layers. E5M2 already uses one byte per K/V value, while the pinned FA3 consumer cannot read E5M2 and all E4M3 branches were slower. This project changes a different physical variable: compulsory local KV bytes.

Use symmetric signed INT4 `[-7, 7]`, packed two values per byte, with one FP16 scale per token, KV head, K-or-V tensor, and 64 head-dimension values. At head dimension 256 this adds four scales per K or V and reduces stored local KV bytes by `46.875%` versus E5M2. If the exact Triton consumer dequantizes in registers without losing that traffic reduction, the theoretical local-bound contribution is about `7.18%` of the whole request. This is explicitly a quality-unsafe execution proxy until later model-quality and feature validation.

## Immutable identity

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, image digest `6113665a…`.
- Accelerator: one NVIDIA H200 SXM, 132 SMs and 4.8 TB/s nominal HBM bandwidth.
- Workload: exact c32, 32 requests, 4,214 prompt and 358 completion tokens each, exactly 17,120 cached and 117,728 fresh prompt tokens.
- Control: qualified E5M2 endpoint at `0.6743258590313417 s/request`.
- Local geometry: 50 layers, batch 32 decode, 32 query heads, 16 KV heads, head dimension 256, page size one, 1,024-token window.
- Global geometry: ten layers `[5,11,17,23,29,35,41,47,53,59]`, 32 query heads, four KV heads, head dimension 512, unchanged page-one E5M2 Triton.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically bind the stack, control, trace, current producer/consumer source, and local wall fraction.

## Immediate experiment

Use `$kernel-research`. Reuse the proven controller, resident read-only checkpoint, pinned image, and current producer-fused FP8/QKV stack. Freeze one local-only packed producer and actual paged Triton consumer; do not create an offline cache conversion. The producer must quantize BF16 K/V directly into packed INT4 plus separate FP16 group scales. The decode consumer must unpack/dequantize through the exact online-softmax/GQA path, accumulate at the current precision, and return the current BF16 layout. Global layers remain byte-identical E5M2 Triton.

After the `$14` reservation is durable, claim `h200-sync-linear-e00vhh6h29fj68x91g`. The first target-GPU call is the discovery test. Repair ordinary compile/API/layout defects in the retained claim, then run one exact actual-producer/consumer component covering batch 32/context 1,024 plus page boundaries, negative padded slots, CUDA-graph padding, zero/tiny/large values, and a multi-token cache append/read sequence. Consume every output. Report max error, relative L2, cosine, saturation, nonfinites, warm distributions, generated-code identity, registers/spills, grid waves, and only the L2/DRAM sectors needed to test the byte hypothesis.

Require finite output, relative L2 at most `0.05`, cosine at least `0.995`, exact 50-local/10-global routing, at least `35%` lower local K/V DRAM sectors, and a conservative whole-request bound of at least `3%`. If all pass, run exactly one profiler-off c32 control/candidate pair with 32/32 sane responses, exact cache accounting, candidate-path proof, and cheap output coherence. A positive candidate remains quality-unqualified.

## Stop rules and resources

Close on incoherent quantization, any global-layer change, page/padding/state failure, missing actual-consumer execution, less than `35%` local K/V sector reduction, a bound below `3%`, invalid accounting, or endpoint regression. Do not sweep group size, bit width, zero points, packing, tiles, page/window geometry, or quantization schemes; do not reopen E4M3, FA3, or local-window reduction.

- Researcher profile: `deep`.
- One retained H200; at most 80 claimed GPU-minutes and 110 wall minutes from first claim.
- Project authorization: `$14.00`.
- Absolute deadline: `2026-07-23T15:20:00Z`.
- At most 8 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
