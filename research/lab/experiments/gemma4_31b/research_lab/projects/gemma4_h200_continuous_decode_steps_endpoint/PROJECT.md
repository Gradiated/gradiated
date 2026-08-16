# H200 continuous-decode scheduling endpoint

## Question

Can pinned SGLang reduce exact Gemma 4 background-serving cost by executing four decode steps per scheduler admission, while preserving the retained c32 runtime, model representation, request bytes, and cache mix?

## Why this matters

The TensorRT-LLM decode candidate is closed by a model-geometry incompatibility: FlashInfer XQA rejects Gemma 4's 512-wide global attention head. The retained exact endpoint still pays one scheduler round trip per generated token. Pinned SGLang exposes `--num-continuous-decode-steps` specifically to reduce that scheduling overhead, with the documented tradeoff of potentially higher time to first token. That is aligned with this campaign's background-agent workload, where sustainable service cost dominates interactive latency.

This is one supported scheduling intervention, not a sweep. Four steps is the sole candidate: it quarters scheduler admission frequency while bounding the added admission delay well below the 358-token generation span.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM at `$2.46/hour`, protected by `gemma-modelopt-export-h200-202607181843z-watchdog.service` through `2026-07-18T20:55:00Z`.
- Canonical control: `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.9194573941250042` service seconds/request.
- Frozen request generator: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Pinned scheduling source: `projects/sglang_gemma4_exact_precreate_binding/probes/source/server_args.py`, SHA-256 `27178e43bc54574d8a39651db57900d045719e23f21cfd19268f867d761acfcd`. Its CLI contract says continuous decode runs multiple decoding steps to reduce scheduling overhead and may trade throughput against TTFT.
- TRTLLM close evidence: `projects/gemma4_h200_trtllm_decode_backend_endpoint/artifacts/trtllm-decode-c32-20260718t1937z/TERMINAL.json`, SHA-256 `b6b16097bd57aec0fc816f081b521211186291b5803ca8923106798a86578dbf`.
- Frozen workload: 32 simultaneous requests, exactly 4,214 prompt and 358 generated tokens each, deterministic shared 535-token prefix, temperature zero, ignored EOS, and no tokenizer-side special-token mutation.

These identities are frozen. Do not substitute a checkpoint, revision, image, request generator, workload, comparator, or precision.

## Immediate experiment

Claim the warm H200 and start one bounded durable execution owner. Remove only the failed TRTLLM candidate container if it remains. Launch the pinned SGLang image/checkpoint once with the full retained baseline: c32, BF16 weights, FP8-E5M2 KV, dynamic chunking at 2,048, fused QK normalization/RoPE, Triton prefill and decode, page size 1, and CUDA graphs through batch 32. Change only `--num-continuous-decode-steps` from `1` to `4`.

Require readiness and prove from server arguments/logs that continuous decode is exactly 4, both attention phases remain Triton, page size remains 1, E5M2 KV is active, and no fallback or unrelated compile/backend flag was introduced. Before timing, prove zero running/queued requests and record an HTTP-200 cache flush. Invoke the unchanged exact-mix runner exactly once in a fresh output root. Retrieve raw rows and SSE responses, request hashes, cache/phase/queue metrics, GPU utilization/power/memory samples, server identity and logs, and a typed terminal.

The valid cache boundary is exact: 134,848 total prompt tokens, 17,120 cached and 117,728 fresh. Require 32/32 finite, nonempty outputs with exact 4,214/358 usage. Record TTFT and inter-token latency as secondary tradeoff telemetry; neither may invalidate a service-time win unless requests fail or violate the bounded output sanity gate.

## Decision gate and limits

- `promote`: intended scheduling/runtime identities proven; 32/32 valid outputs; exact request and cache accounting; no failures or reloads; service time at most `0.873484524419` seconds/request (at least 5% faster than the canonical control).
- `retain_incremental`: the same identity, output, request, cache, and reliability gates; any valid service improvement below `0.9194573941250042` seconds/request. Retain without tuning the step count.
- `negative`, `unsupported`, `startup_failure`, `oom`, `cache_accounting_failure`, `quality_sanity_failure`, or `owner_failure`: typed terminal after this single candidate. No second step count, scheduler flag, or repair is authorized.

Maximum claim: 55 wall minutes, 45 H200 compute minutes, 3 GiB temporary storage, and `$2.25` provider exposure at `$2.46/hour`, ending by `2026-07-18T20:45:00Z` with ten minutes reserved for retrieval and release. Release without teardown. Do not rerun the comparator, alter weights/KV precision/concurrency/token geometry/chunk size/cache geometry/attention backend, enable Torch compile, patch source, replay checkpoint staging or hashing, run broad quality, create provider resources, or change the watchdog.
