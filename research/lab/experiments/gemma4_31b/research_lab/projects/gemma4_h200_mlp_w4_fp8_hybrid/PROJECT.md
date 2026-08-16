# Gemma 4 H200 mixed W4-MLP / FP8-attention endpoint

## Question

Can the exact current H200 stack replace only decode-critical MLP projections with the verified exact-revision AWQ W4 representation, retain FP8 attention/QKV and FP8 prefill fallback, and reduce whole-request service time by at least 3%?

## Why this matters

The current producer-fused trace assigns `5.375939818 s` (`24.0589%`) of non-overlapping wall time to FP8 linears, including `2.612035063 s` in decode. Historical family attribution assigns about 70.37% of FP8-linear time to packed gate/up plus down projections. The paired-gate/up investigation also proved that pinned SGLang already uses one packed gate/up GEMM, so another launch or cluster change is low-value. At decode `M<=32`, a supported group-128 W4 consumer can instead reduce compulsory MLP weight bytes relative to E4M3 while leaving the measured FP8 attention stack untouched.

This is materially different from the old full-vLLM W4 endpoint, which used c96/c128 and never produced an endpoint row. It is also different from the failed FP8 Stream-K, multicast-cluster, and activation-to-down candidates.

## Scope and method

Use `$kernel-research`. Bind the exact current `MergedColumnParallelLinear gate_up_proj -> GeluAndMul -> down_proj` producer/consumer path, the observed decode shapes through `M=32`, the observed prefill shapes `M=397/1409/1631/2048`, E4M3 activation/weight scales, and the exact group-128 zero-point W4 tensors. Check current SGLang, vLLM, CUTLASS, Marlin, and Machete support before writing a custom kernel.

Freeze one hybrid consumer:

- W4 only for supported decode MLP gate/up and down projections;
- current FP8 path for attention/QKV, output head, unsupported shapes, and all prefill;
- unchanged BF16 `GeluAndMul`, residual, normalization, cache, sampling, and output layout.

The first H200 call is a real-weight exact-consumer discovery and correctness test against dequantized W4 reference outputs. Measure warm component timings and only the DRAM/L2, tensor, launch, register, spill, and grid-wave evidence needed to test the weight-byte hypothesis. Promote to one c32 current-FP8 control/hybrid pair only if all W4 numerical/path gates pass and the measured call-weighted bound predicts at least 3% whole-request improvement. The hybrid is a performance proxy until broad quality and feature validation; require finite/nontrivial outputs and three cheap coherence prompts before endpoint timing.

## Exact inputs and reusable execution path

- Current immutable identity: `../gemma4_h200_residual_h2d_sync_residency/EVIDENCE_BINDING.json`.
- Current trace: `../gemma4_h200_residual_h2d_sync_residency/artifacts/residual-h2d-current-frontier-20260723t0403z/CURRENT_TRACE_ATTRIBUTION.json`.
- W4 identity: `../h200_w4_full_endpoint_background_frontier/BINDINGS.json`.
- Local W4 bytes: `../h100_w4_full_endpoint_background_frontier/artifacts/w4-checkpoint-owner-20260717T223754Z/checkpoint-repair-2`.
- Reuse the claim/staging/retrieval pattern in `../gemma4_h200_dense_fp8_linear_schedule/run_bench_owner.py`; the old W4 endpoint owner is evidence for the W4 byte manifest, not the current runtime contract.
- Resident H200 state: `/home/glmrunner/gemma4-h200-dense-fp8-streamk/checkpoint`, pinned SGLang digest `6113665…`, and caches under `/home/glmrunner/gemma4-h200-dense-fp8-streamk/build-gate-up`.

## Budgets and decision

One retained H200, at most 120 claimed GPU-minutes, 2.4 wall-clock hours, 25 GiB retrieved/staged project data, and `$12.00`. Prepare offline while the higher-priority MTP endpoint runs; claim the bench only after the reservation is durable and MTP releases it. Do not create a provider resource or run a representation, kernel, group-size, or proposal sweep.
