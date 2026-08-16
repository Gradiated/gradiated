# Exact vLLM H200 c32 endpoint on the retained checkpoint

## Question

Can the pinned Gemma-capable vLLM runtime serve the exact campaign c32 request bytes on the retained H200 faster and more economically than the canonical SGLang baseline, with valid outputs and measured prefix-cache behavior?

## Why this matters

The campaign has exhausted the immediately exposed SGLang flag stack: dynamic chunking and fused QK/RoPE are small retained wins, while higher concurrency, explicit repeated-KV attention, Torch compilation, online ModelOpt conversion, and the official offline ModelOpt exporter are negative or unsupported. A different mature runtime is now a more independent hypothesis than another SGLang repair.

Earlier work in this same project never reached model load or an endpoint request. Its attempts failed in checkpoint views, transfer markers, workspace ownership, or program transfer and cleaned their provider resources. Those terminals are not vLLM performance evidence. The present warm H200 already has the exact checkpoint and a safe lifecycle, eliminating the failed transfer/controller path. Reactivate this project rather than creating a repair or successor project.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- vLLM image: `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, previously observed as vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM at `$2.46/hour`, protected by `gemma-modelopt-export-h200-202607181843z-watchdog.service` through `2026-07-18T20:55:00Z`.
- Canonical SGLang control: `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.9194573941250042` service seconds/request.
- Frozen request generator and SGLang consumer: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Existing vLLM OpenAI consumer and token-ID/telemetry logic: `projects/exact_vllm_h200_fixed_session_endpoint/trace_endpoint_runner.py`, SHA-256 `b70a2b7804aad77784a66b9f768bf5d338f9d04f7436d69f3f063909b7529918`.
- Workload: 32 simultaneous requests, exactly 4,214 prompt and 358 generated tokens each, deterministic shared 535-token prefix and frozen per-request suffixes from seed `gemma4-background-exact-mix-c32-20260718`, temperature zero, ignored EOS, and no tokenizer-side special-token mutation.

These identities were mechanically extracted from the named artifacts. Do not substitute a checkpoint, revision, image, request generator, workload, or comparator.

## Immediate experiment

Claim the warm H200 and start one bounded durable execution owner. The previous ModelOpt owner already stopped the SGLang server; do not require or infer a healthy resident endpoint. Pull only the pinned vLLM image if it is not resident, and launch the exact checkpoint on port 30000 with prefix caching, c32 capacity, BF16 weights, and supported FP8-E5M2 KV when the pinned runtime exposes that exact representation. Bind context and batch limits to the frozen 4,214/358 c32 workload without tuning them. Allow one ordinary launch/API repair; do not change the image, precision, concurrency, workload, or open a support successor.

Create the minimum vLLM consumer adapter needed to reuse the exact request bodies produced by the frozen runner while using vLLM's own cache-reset and metrics endpoints. Preserve request-body SHA-256 values and raw SSE responses. Prove server identity, model revision/path, weight and KV dtypes, c32 admission, prefix-caching state, and zero running/queued requests before a recorded successful cache reset. Run one unscored one-token warmup with a distinct suffix, snapshot metrics, then release the 32 unchanged scored bodies simultaneously exactly once. Retrieve all raw request bodies, responses and token IDs, usage, TTFT/decode/end-to-end timing, batch wall time, cache query/hit deltas, queue/prefill/decode metrics, GPU utilization/power/memory samples, server logs, image identity, and a typed terminal.

The request bytes must remain identical even if vLLM's block-aligned cache reports fewer than SGLang's 17,120 cached tokens. Record the realized cache hits and fresh tokens exactly; do not alter the shared prefix to manufacture matching cache accounting. Label any cache-accounting difference in the comparison.

## Decision gate and limits

- `promote`: intended vLLM runtime and precision path proven; 32/32 finite, nonempty outputs with exactly 4,214 prompt and 358 completion tokens; request hashes match the frozen generator; cache queries equal 134,848 prompt tokens and cache hits are valid for the unchanged 535-token shared prefix; no failures/reloads; service time at most `0.873484524419` seconds/request (at least 5% faster than canonical SGLang).
- `retain_incremental`: the same identity, output, request, cache, and reliability gates; any improvement below `0.9194573941250042` seconds/request. Retain without runtime or batching tuning.
- `negative`, `unsupported`, `oom`, `startup_timeout`, `quality_sanity_failure`, `cache_accounting_failure`, or `owner_failure`: typed terminal after the single candidate. A c32 failure does not authorize c16, a second image, precision fallback, or a sweep.

Maximum claim: 100 wall minutes, 80 H200 compute minutes, 25 GiB temporary image/artifact storage, and `$4.50` provider exposure at `$2.46/hour`, ending by `2026-07-18T20:45:00Z` with ten minutes reserved for retrieval and release. Release without teardown. Do not transfer or rehash the resident checkpoint, rerun SGLang, rerun the comparator, alter concurrency/token geometry/cache prefix, sweep vLLM settings, retry ModelOpt, run broad quality, create provider resources, or change the watchdog.
