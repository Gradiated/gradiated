# Gemma 4 H200 FP8 2:4 structured-sparsity co-design

## Question

Can Hopper's native 2:4 sparse tensor-core path turn a deliberately sparsified version of the exact Gemma 4 FP8 linear workload into enough measured H200 service-time headroom to close the remaining 7.42% endpoint gap?

## Why this matters

The retained exact endpoint is `0.689220013 s/request` against the `0.6381105231 s/request` ceiling. Current runtimes, attention redesigns, adjacent FP8 fusion, and static FP8 representation are measured negative. Structured sparsity changes the model/kernel contract rather than replaying those mechanisms and can reduce the dominant dense linear work if the exact shapes reach a real sparse consumer efficiently.

This is initially a quality-unsafe execution proxy. It measures the cost mechanism only and must not be described as a deployable model or quality-preserving result.

## Immutable scope

- Authoritative binding: `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json` with SHA-256 `cebc435c4eb1e5716c4aa9bd854785a3e7cac4b0665c96ea6a44040b3e96fb62`.
- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Checkpoint index SHA-256: `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Baseline runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Baseline representation: TP1 dynamic in-memory FP8-E4M3FN linears, FP8-E5M2 KV, dynamic chunking with chunk size 2048, no MTP.
- Endpoint workload if promoted: 32 requests at concurrency 32, 4,214 prompt and 358 completion tokens per request, 17,120 cached and 117,728 fresh prompt tokens total.
- Target accelerator: one NVIDIA H200 SXM shared bench provisioned only by the director after the `$24.00` reservation is durable.

## Immediate experiment

Use `$kernel-research`. Inspect only the pinned linear call path and the prior exact profile needed to select the hottest eligible FP8 linear family. Implement one genuine compressed 2:4 FP8 consumer using a current supported Hopper library path such as cuSPARSELt or CUTLASS; a mask followed by dense GEMM is not the intervention.

First measure exact real-weight component rows at decode-representative `M=32` and prefill-representative `M=2048`. At minimum include the layer-0 down projection weight `[5376, 21504]`; select one additional hottest eligible family only if the prior profile shows it materially improves the endpoint bound. Compare the sparse consumer with the strongest dense FP8 consumer using the same sparsified FP8 tensor, so correctness measures the kernel implementation rather than pruning quality. Record compressed-layout identity, producer and consumer symbols, warmup/repetition policy, kernel timing, and enough counters to distinguish sparse tensor-core realization from packing, bandwidth, launch, or occupancy limits.

The component passes only if both shapes satisfy relative L2 error at most `0.02`, cosine at least `0.999`, and the measured eligible-linear wall-time bound predicts at least a 7.42% endpoint gain. If it passes, integrate exactly one unchanged c32 endpoint pair in this project against `0.689220013 s/request`; otherwise terminate the mechanism without tile sweeps or a successor project. Endpoint promotion additionally requires 32/32 accounting, exact token counts, sane outputs, and service time at or below `0.6381105231 s/request`.

## Budget and artifacts

- Total authorized project spend: `$24.00`.
- At most one shared H200 bench and six claimed GPU-hours; no second provider resource.
- Cold setup, component discovery, and a conditionally promoted endpoint must finish within six wall-clock hours of the first claim.
- Preserve immutable inputs and write each attempt to a fresh artifact directory.
- Emit a typed terminal containing component correctness, timings, physical interpretation, predicted endpoint bound, actual provider exposure/cost, and any conditional endpoint result.

No researcher may create, delete, or retire provider resources. Ordinary compile, ABI, path, and runtime defects are repaired in place on the retained bench.
