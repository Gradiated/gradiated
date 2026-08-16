# Gemma 4 background serving-system frontier

## Question

Can model-specific scheduling, batching, cache policy, graph capture, or prefill/decode organization reduce exact Gemma 4 serving cost by at least 5% while preserving the model computation and OpenRouter request/tool behavior?

## Work

Use the exact 4,214/358 prompt-heavy distribution, 12.7% cache-read share, and separate AA 10K single stream. Analyze and directly compare the strongest few interactions among background pooling, c16/c32 occupancy, async scheduling, chunked prefill, CUDA-graph geometry, prefix reuse, and hybrid local/global attention scheduling. Start from measured endpoint telemetry and pinned source; do not run a broad parameter sweep or preserve interactive latency assumptions when background-agent traffic can wait.

Run one bounded actual-server comparison on a compatible retained bench when available; otherwise produce and execute the fastest exact simulation or component falsifier while queued. Preserve complete-request throughput, queueing, memory, failures, power, and all-in cost. Outputs need only cheap validity/coherence checks during exploration. Full GPQA-Diamond and TauBench evaluation is deferred to performance survivors.

## Limits

The project-wide cumulative provider authorization is `$2.75`; the current iteration may add at most `$1.30` of provider exposure. Use at most 3 GiB of temporary artifacts, avoid setup replay, and release without teardown.

## Current iteration — mixed chunked prefill/decode

The c32 working baseline now includes both retained simple wins: dynamic chunking at 2,048 and fused QK normalization/RoPE. Its canonical terminal is `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.9194573941250042` service seconds/request. The separate continuous-decode-steps=4 arm is closed at `0.9309568604062406` seconds/request; do not tune or retain it.

Pinned SGLang source `projects/sglang_gemma4_exact_precreate_binding/probes/source/server_args.py`, SHA-256 `27178e43bc54574d8a39651db57900d045719e23f21cfd19268f867d761acfcd`, exposes `--enable-mixed-chunk` to mix prefill and decode in a batch when chunked prefill is active. Run exactly one candidate that keeps continuous decode steps at 1 and changes only this flag from false to true. This is a distinct prefill/decode organization test, not a scheduler or chunk-size sweep.

Reuse warm bench `h200-attention-endpoint-e00vbbb709tzxscaan`, the resident exact eight-file 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`, pinned SGLang image `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`, and exact runner SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`. Stop only the retained step-4 container and launch once with c32, BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK/RoPE, Triton prefill/decode, page size 1, continuous decode steps 1, and mixed chunk enabled. Prove the flag remains enabled after runtime argument resolution and no fallback occurred.

After zero running/queued requests and an HTTP-200 cache flush, invoke the frozen 32-request 4,214/358 runner once. Require 32/32 finite nonempty outputs and exact 17,120 cached / 117,728 fresh prompt-token accounting. Promote at `<=0.873484524419` seconds/request; retain any smaller valid improvement below `0.9194573941250042` without tuning; otherwise close. Retrieve raw rows/SSE, phase/cache/queue metrics, GPU telemetry, server identity/logs, and a typed terminal, then release without teardown.

This iteration adds at most 30 wall minutes, 20 retained-H200 minutes, 3 GiB temporary artifacts, and `$0.82` measured provider exposure, keeping the project's aggregate authorization at `$1.50` and ending the claim by `2026-07-18T20:35:00Z`. No comparator replay, continuous-step/chunk/backend/concurrency sweep, repair, source patch, setup replay, provider creation, watchdog change, or broad quality run is authorized.

## Current iteration — double the prefill batch-token ceiling

The canonical retained endpoint spends about `9.43` seconds to first token and `20.31` seconds after first token while processing 117,728 fresh prompt tokens. Its resolved runtime caps a prefill batch at 16,384 tokens even though all 32 requests arrive together. Pinned SGLang source defines `--max-prefill-tokens` as the maximum tokens in a prefill batch; increasing that cap can expose larger prompt GEMMs without changing the retained dynamic chunk size of 2,048.

Run one candidate at 32,768 max prefill tokens. This is a single workload-derived doubling, not a cap or chunk-size sweep. The canonical endpoint explicitly fixes `mem_fraction_static=0.85`, so the fallback token-reservation formula is inactive. Its measured KV token pool is 170,792 tokens versus 146,304 tokens for the complete exact c32 batch, and startup reported 20.70 GiB available GPU memory. OOM, request retraction, or a reduced pool below the complete workload is a typed negative rather than authority for a smaller cap.

Before claiming the bench, atomically snapshot `projects/gemma4_background_serving_frontier/exact_mix_runner.py` under a project-local immutable input and require SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`. Claim warm bench `h200-attention-endpoint-e00vbbb709tzxscaan`, stop only the retained interval-8 container, and launch the pinned resident checkpoint/image once with the full canonical runtime: c32, BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK/RoPE, Triton prefill/decode, page size 1, continuous decode steps 1, mixed chunk disabled, KV splits 8, FlashInfer sampling, CUDA graphs through 32, and stream interval restored to 1. Change only max prefill tokens from 16,384 to 32,768.

Prove the resolved argument and a token pool of at least 146,304, then require zero running/queued requests and an HTTP-200 cache flush. Invoke the immutable runner exactly once. Require 32/32 finite nonempty 4,214/358 rows, exact frozen request hashes, and exactly 17,120 cached / 117,728 fresh prompt tokens. Retrieve raw SSE/rows, server identity/logs, GPU utilization/power/memory, phase/cache/queue metrics, and the prefill-forward/chunked-prefill counter deltas needed to interpret batching.

Compare only to canonical terminal SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3` at `0.9194573941250042` service seconds/request. Promote at `<=0.873484524419`; retain any smaller valid improvement without tuning; otherwise close the cap line. The aggregate project authorization is `$2.75`, of which `$0.92` is already recorded; this iteration adds at most 32 wall minutes, 25 H200 compute minutes, 3 GiB temporary artifacts, and `$1.30` provider exposure, ending by `2026-07-18T21:20:00Z`. Release without teardown. Do not replay the comparator, try another cap, alter chunk size/concurrency/scheduler/backend/precision, add a companion intervention, patch source, create provider resources, or change the watchdog.

## Admitted consumer-only capacity-guard correction

The first 32,768-cap owner completed setup but invoked zero workload requests. It proved the already-loaded candidate server is healthy, every frozen runtime identity resolves correctly, the pool is 170,792 tokens, running and queued requests are zero, cache flush returns HTTP 200, and neither OOM nor retraction occurred. The owner stopped only because its lexical guard `1[4-9][6-9][0-9]{3}` does not match `170792`, even though the required numeric predicate `170792 >= 146304` is true. This is an ordinary pre-invocation launcher defect, not intervention evidence; the campaign and lab repair contract supersede the earlier local no-repair wording.

One same-project consumer-only correction is admitted. Before claim, reuse the immutable snapshot `inputs/exact_mix_runner-143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7.py` and verify SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`. Claim the released bench and require the existing `gemma-prefill-cap32768-c32` server to remain healthy. Do not restart the container or reload the model. Re-prove the full resolved candidate identity, extract `max_total_num_tokens` as digits, compare it numerically to 146,304, verify the remote runner hash, establish zero running/queued requests, and perform a fresh HTTP-200 cache flush. Then invoke the immutable exact-mix runner once—the first workload invocation for this candidate—and retrieve the original experiment's raw evidence and typed terminal.

The original comparator, promotion/retention gates, exact output/cache requirements, and telemetry contract remain unchanged. Cumulative project spend is `$1.17`; this correction may add at most 20 wall minutes, 10 H200 compute minutes, 3 GiB temporary artifacts, and `$0.75` provider exposure within the existing aggregate `$2.75` authorization, ending by `2026-07-18T21:20:00Z`. Release without teardown. Any further identity, consumer, or server failure closes the cap line; do not reload, replay, try a smaller cap, change another setting, create provider resources, or mutate the watchdog.
