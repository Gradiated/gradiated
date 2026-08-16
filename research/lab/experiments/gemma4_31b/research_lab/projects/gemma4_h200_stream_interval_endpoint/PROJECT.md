# H200 streamed-output interval endpoint

## Question

Can coarser server-side streaming reduce exact Gemma 4 background-serving cost by amortizing output serialization and SSE delivery, while preserving the canonical model computation, request bodies, completed outputs, and cache behavior?

## Why this matters

The retained endpoint streams every generated token because pinned SGLang defaults `stream_interval` to 1. The exact workload therefore emits roughly 11,456 generated tokens across 32 simultaneous responses. Pinned source describes `--stream-interval` as the token-length streaming buffer and explicitly says that a larger value raises throughput at the cost of smoother streaming. That trade is aligned with this campaign: sustained background-agent service cost is primary and interactive latency is secondary.

This is distinct from the now-closed scheduling and kernel candidates. Continuous decode steps 4 regressed service time by 1.25%, mixed chunking regressed by 193.60%, and Triton KV splits 4 regressed by 1.67%. The sole candidate is interval 8, large enough to materially reduce SSE event frequency while still yielding about 45 updates over each 358-token response. It is not a sweep.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM at `$2.46/hour`, protected by `gemma-stream-interval-h200-202607182033z-watchdog.service` through `2026-07-18T21:30:00Z`.
- Canonical control: `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.9194573941250042` service seconds/request.
- Frozen request generator: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Pinned server-argument source: `projects/sglang_gemma4_exact_precreate_binding/probes/source/server_args.py`, SHA-256 `27178e43bc54574d8a39651db57900d045719e23f21cfd19268f867d761acfcd`; it binds the default interval to 1 and states that larger intervals raise throughput.
- Closed split-4 terminal: `projects/gemma4_h200_triton_kv_split_endpoint/artifacts/triton-kv-split4-c32-repair-20260718t2026z/TERMINAL.json`, SHA-256 `c59b934a84d6b9fdfcc810a2c72ce2aa850ec329676f977950e352dd05b27f03`, at `0.9348447529375221` service seconds/request.
- Frozen workload: 32 simultaneous requests, exactly 4,214 prompt and 358 generated tokens each, deterministic shared 535-token prefix, temperature zero, ignored EOS, streaming enabled, and no tokenizer-side special-token mutation.

These identities are frozen. Do not substitute the checkpoint, revision, image, runner, workload, comparator, precision, attention backend, or retained interventions.

## Immediate experiment

Before claiming the GPU, atomically snapshot the canonical runner under this project and verify SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`. Transfer only that immutable snapshot; do not resolve the cross-project path again after claim.

Claim the warm H200 and start one bounded durable execution owner. Stop only the retained split-4 container, then launch the pinned image/checkpoint once with the canonical retained endpoint: c32, BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK normalization/RoPE, Triton prefill and decode, page size 1, continuous decode steps 1, mixed chunk disabled, Triton KV splits restored to 8, and CUDA graphs through batch 32. Change only `--stream-interval` from 1 to 8.

Require readiness and prove from resolved arguments/logs that stream interval is exactly 8, KV splits are 8, and every other bound runtime setting is canonical. Prove zero running/queued requests, record an HTTP-200 cache flush, and invoke the unchanged exact-mix runner exactly once in a fresh output root. Retrieve raw request rows and SSE responses, request hashes, cache/phase/queue metrics, GPU utilization/power/memory samples, server identity/logs, and a typed terminal.

Require 32/32 finite, nonempty outputs with exact 4,214/358 usage and exactly 17,120 cached / 117,728 fresh prompt tokens. Preserve the complete concatenated response text and token accounting. Derive the SSE data-event count from the raw responses and report it with TTFT as a secondary latency/transport trade; service seconds/request is the primary economic proxy.

## Decision gate and limits

- `promote`: all identity, request, output, cache, and reliability gates pass with service time at most `0.873484524419` seconds/request, at least 5% faster than the canonical control.
- `retain_incremental`: the same gates pass with any service improvement below `0.9194573941250042` seconds/request. Retain interval 8 without tuning.
- `negative`, `unsupported`, `startup_failure`, `oom`, `cache_accounting_failure`, `quality_sanity_failure`, or `owner_failure`: typed terminal after this one candidate. Do not test another interval or add a companion intervention.

Maximum claim: 45 wall minutes, 35 H200 compute minutes, 3 GiB temporary storage, and `$2.25` provider exposure at `$2.46/hour`, ending by `2026-07-18T21:20:00Z` with ten minutes reserved before watchdog cleanup. Release without teardown. Do not replay the comparator, change scheduling/chunking/concurrency/backend/page/split/precision, patch source, restage or rehash the checkpoint, run broad quality, create provider resources, or change the watchdog.
