# H200 Triton decode KV-split endpoint

## Question

Can one model-geometry-informed reduction in the Triton flash-decode KV split count lower exact Gemma 4 c32 service cost without changing model computation, precision, cache behavior, or serving semantics?

## Why this matters

The recent scheduling candidates are closed: four continuous decode steps regressed service by 1.25%, while mixed chunked prefill/decode made the endpoint 2.94x slower. Both runs saturated the H200, so the next useful target is compulsory attention-kernel work rather than more scheduler batching.

Pinned SGLang defaults `--triton-attention-num-kv-splits` to 8 and documents that larger values are better for longer contexts. Exact Gemma 4 has 60 attention layers: 50 local layers read at most the 1,024-token window with 16 KV heads of dimension 256, while only 10 global layers reach about 4,571 tokens with 4 KV heads of dimension 512. At c32, four splits still expose ample sequence/head/split parallelism for 132 H200 SMs, but halve partial-result and reduction work in the dominant short-window layers. The sole candidate is therefore 4, not a sweep.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM at `$2.46/hour`, protected by `gemma-modelopt-export-h200-202607181843z-watchdog.service` through `2026-07-18T20:55:00Z`.
- Canonical control: `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.9194573941250042` service seconds/request.
- Frozen request generator: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Pinned server-argument source: `projects/sglang_gemma4_exact_precreate_binding/probes/source/server_args.py`, SHA-256 `27178e43bc54574d8a39651db57900d045719e23f21cfd19268f867d761acfcd`; it binds the default split count to 8 and states that larger counts target longer contexts.
- Exact attention geometry evidence: `projects/gemma4_precision_hardware_frontier/h200_sdpa_backend_discriminator.py` binds local `(1024, 16, 256, 50 layers)` and global `(4571, 4, 512, 10 layers)` cases.
- Closed mixed-chunk terminal: SHA-256 `178c5c4fd33db43fb025db89e5011d6c9a201745dec877cac66eb99794937cf8`.
- Frozen workload: 32 simultaneous requests, exactly 4,214 prompt and 358 generated tokens each, deterministic shared 535-token prefix, temperature zero, ignored EOS, and no tokenizer-side special-token mutation.

These identities are frozen. Do not substitute the checkpoint, revision, image, runner, workload, comparator, precision, or attention backend.

## Immediate experiment

Claim the warm H200 and start one bounded durable execution owner. Stop only the retained mixed-chunk container. Launch the pinned SGLang image/checkpoint once with the canonical retained baseline: c32, BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK normalization/RoPE, Triton prefill/decode, page size 1, continuous decode steps 1, mixed chunk disabled, and CUDA graphs through batch 32. Change only `--triton-attention-num-kv-splits` from 8 to 4.

Require readiness and prove from resolved server arguments/logs that the split count is exactly 4, both attention phases remain Triton, and no fallback or unrelated flag was introduced. Before timing, prove zero running/queued requests and record an HTTP-200 cache flush. Invoke the unchanged exact-mix runner exactly once in a fresh output root. Retrieve raw rows/SSE responses, request hashes, cache/phase/queue metrics, GPU utilization/power/memory samples, server identity/logs, and a typed terminal.

Require 32/32 finite, nonempty outputs with exact 4,214/358 usage and exactly 17,120 cached / 117,728 fresh prompt tokens. Report service time as the primary cost proxy and retain TTFT/decode telemetry for mechanism interpretation.

## Decision gate and limits

- `promote`: all identity, output, request, cache, and reliability gates pass with service time at most `0.873484524419` seconds/request, at least 5% faster than the canonical control.
- `retain_incremental`: the same gates pass with any service improvement below `0.9194573941250042` seconds/request. Retain without split tuning.
- `negative`, `unsupported`, `startup_failure`, `oom`, `cache_accounting_failure`, `quality_sanity_failure`, or `owner_failure`: typed terminal after this one candidate. Do not test 2, 8, 16, per-layer splits, or a tile-size companion.

Maximum claim: 30 wall minutes, 25 H200 compute minutes, 3 GiB temporary storage, and `$1.30` provider exposure at `$2.46/hour`, ending by `2026-07-18T20:45:00Z` with ten minutes reserved before watchdog cleanup. Release without teardown. Do not replay the comparator, change scheduling/chunking/concurrency/backend/page/precision, patch source, restage or rehash the checkpoint, run broad quality, create provider resources, or change the watchdog.

## Admitted consumer-boundary repair

The first owner started the intended split-4 server successfully but stopped before SCP, cache flush, or any request because the shared runner path transiently hashed to `235f5de7a5ae66aa9732742c2fef65e49fe13bffcfae5299823c5c1e9837622d`. The durable local hash artifact now records the required `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`, the current source path hashes to that value, and the canonical fused terminal independently proves that exact runner identity. This is a shared-file race, not intervention evidence.

One same-project consumer-only repair is admitted. Before claiming the bench, atomically snapshot the current source bytes into a project-local immutable input and require the canonical hash; do not edit or regenerate them. Claim the released bench, prove the already-loaded `gemma-triton-kv-split4-c32` server is healthy and still resolves every candidate identity, then copy that immutable runner to `/home/glmrunner/gemma-attention-endpoint/workspace/exact_mix_runner.py` and prove the remote hash. Do not restart or reload the server. Establish zero running/queued requests, perform the first HTTP-200 cache flush for this candidate, invoke the runner exactly once, retrieve and classify the original experiment, and release.

The project retains its aggregate `$1.30` authority; `$0.17` is already conservatively consumed. The repair must finish by `2026-07-18T20:40:00Z`, preserving fifteen minutes before watchdog cleanup. Any further identity failure, unhealthy server, request failure, or missing artifact closes the split-4 line without another repair.
