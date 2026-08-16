# H200 TensorRT-LLM decode-attention backend endpoint

## Question

Can pinned SGLang's supported TensorRT-LLM MHA decode backend reduce exact Gemma 4 c32 service cost when prefill remains on the proven Triton path and the candidate is stacked on retained dynamic chunking and fused QK/RoPE?

## Why this matters

The canonical c32 endpoint uses Triton for both prefill and decode. The exact workload generates 358 tokens per request after a 4,214-token prompt, so a decode-only backend can attack repeated paged hybrid-attention work without changing weights, KV precision, scheduling, or model semantics. Pinned source explicitly admits `trtllm_mha` for decode on Hopper SM90 and requires a 16/32/64-token page size. This is a supported engine dataflow change, unlike the rejected explicit KV gather/repetition patch.

The vLLM branch is closed: its sole repaired launch reached Gemma 4 GPU profiling but the pinned runtime rejects E5M2 KV. Do not change vLLM precision or reopen that runtime in this project.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM at `$2.46/hour`, protected by `gemma-modelopt-export-h200-202607181843z-watchdog.service` through `2026-07-18T20:55:00Z`.
- Canonical control: `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.9194573941250042` service seconds/request.
- Frozen request generator: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Pinned backend-selection source: `projects/sglang_gemma4_exact_precreate_binding/probes/source/server_args.py`, SHA-256 `27178e43bc54574d8a39651db57900d045719e23f21cfd19268f867d761acfcd`. It admits TRTLLM MHA decode on SM90 and binds supported page sizes to 16, 32, or 64.
- Frozen workload: 32 simultaneous requests, exactly 4,214 prompt and 358 generated tokens each, deterministic shared 535-token prefix, temperature zero, ignored EOS, and no tokenizer-side special-token mutation.

These identities are frozen. Do not substitute a checkpoint, revision, image, request generator, workload, or comparator.

## Immediate experiment

Claim the warm H200 and start one bounded durable execution owner. Stop and remove only any retained vLLM container; do not replay checkpoint staging, hashing, or image pull. Launch the pinned SGLang image/checkpoint once with the full retained working baseline: c32, BF16 weights, FP8-E5M2 KV, dynamic chunking at 2,048, fused QK normalization/RoPE, CUDA graphs through batch 32, and all canonical sampling/request settings. Keep prefill explicitly on Triton. Change only decode attention to `trtllm_mha` and page size to `64`, the source-supported Hopper geometry.

Require readiness and prove from server arguments/logs that prefill is Triton, decode is TRTLLM MHA, page size is 64, E5M2 KV is active, and no backend fallback occurred. Before timing, prove zero running/queued requests and record an HTTP-200 cache flush. Invoke the unchanged exact-mix runner exactly once in a fresh output root. Retrieve raw rows and SSE responses, request hashes, cache/phase/queue metrics, GPU utilization/power/memory samples, server identity and logs, and a typed terminal.

The request bodies remain identical, but page-size 64 changes prefix-cache granularity. Require 134,848 total prompt tokens and record realized cached/fresh deltas exactly; the source-predicted shared-prefix accounting is 16,384 cached and 118,464 fresh tokens (512 reusable tokens per request). Do not change the prefix to imitate the page-1 comparator. A different valid realized cache count must be labeled and prevents a direct performance promotion unless its effect is conservatively normalized.

## Decision gate and limits

- `promote`: intended backend identities proven with no fallback; 32/32 finite, nonempty rows with exact 4,214/358 usage and frozen request hashes; valid cache accounting; no failures/reloads; service time at most `0.873484524419` seconds/request (at least 5% faster than the canonical Triton-decode control).
- `retain_incremental`: the same identity, output, request, cache, and reliability gates; any valid service improvement below `0.9194573941250042` seconds/request. Retain without backend/page tuning.
- `negative`, `unsupported`, `startup_failure`, `oom`, `cache_accounting_failure`, `quality_sanity_failure`, or `owner_failure`: typed terminal after this single candidate. No second backend, page-size sweep, or repair is authorized.

Maximum claim: 77 wall minutes, 65 H200 compute minutes, 5 GiB temporary storage, and `$3.50` provider exposure at `$2.46/hour`, ending by `2026-07-18T20:45:00Z` with ten minutes reserved for retrieval and release. Release without teardown. Do not rerun the comparator, alter weights/KV precision/concurrency/token geometry/chunk size/scheduling, mount source patches, enable Torch compile, retry vLLM or ModelOpt, run broad quality, create provider resources, or change the watchdog.
