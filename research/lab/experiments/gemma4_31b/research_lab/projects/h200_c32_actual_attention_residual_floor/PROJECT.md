# H200 c32 actual attention and residual floor

## Decision question

Does the actual pinned-image H200 decode-attention consumer for exact Gemma 4 31B, added to the measured transformer-linears and `ParallelLMHead` floor, falsify or preserve the sole remaining BF16 operating point at concurrency/batch 32?

The component evidence closes c1/c4/c8, and the exact BF16 KV-read floor closes c16 even at peak H200 bandwidth with a full L2 credit. c32 remains below the strict whole-service ceiling by `0.247242 seconds/request` after measured linears+head, or `0.189244 seconds/request` after the optimistic KV-read floor. A full-checkpoint endpoint owner then spent its session in staging before a fail-closed program audit. This checkpoint-free actual-consumer measurement is the shortest target-GPU result and changes only the missing attention/residual work.

## Mechanically bound scope

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning, TP=1.
- Runtime: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, observed vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Hardware: one Nebius H200 SXM, `1gpu-16vcpu-200gb`, authenticated preemptible experiment rate refreshed before create; production planning `$3.25/hour`.
- Exact hybrid attention:
  - 50 sliding layers: 32 query heads, 16 KV heads, head dimension 256, window/context 1,024.
  - 10 global layers: 32 query heads, 4 KV heads, head dimension 512, exact decode contexts 4,214 through 4,571 inclusive; `attention_k_eq_v=true`.
  - Batch 32, BF16 Q/K/V/cache and output. The primary consumer must be the concrete FlashAttention/vLLM CUDA path shipped in the pinned image, such as its installed `flash_attn_with_kvcache`/paged decode implementation—not PyTorch SDPA or an analytical bandwidth proxy.
- Measured linears+head c32 floor: `0.22476958992984145 seconds/request` from `../h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json`, SHA-256 `9f12b3ae4c8d82176f0ec9b09845c6e97ab1f278a458bd023adcbe433fd004fe`.
- Exact KV evidence: c32 optimistic read floor `0.05799790933333333 seconds/request`, c16 closed, from `../h200_bf16_kv_attention_bandwidth_floor/KV_ATTENTION_FLOOR.json`, SHA-256 `8d0d1ef6bc39adef386a072947bc0ae820e3193af4d6e8b28c19bc6f59fcb442`.
- Market whole-service ceilings: `0.47201182295214134-0.47751364375858635 seconds/request`, from `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`.

The director-generated `artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass before delegation. No checkpoint, tokenizer, endpoint server, or provider-resident model state is required.

## Immediate actual-attention experiment

Use the proven shared Nebius microbenchmark lifecycle and one bounded user-systemd owner plus independent watchdog. Before provider create, run a CPU-safe import/source probe inside the exact immutable image that identifies the concrete CUDA attention symbol, source/build identity, supported H200/head/GQA geometry, and final staged imports. Bind the benchmark, wrapper, owner, transitive lifecycle files, image, and identity artifact in an actual behavioral audit. Do not build a new provider framework.

Allocate deterministic BF16 Q and maximum K/V caches for c32. Global K and V should be identical to respect `attention_k_eq_v`; the performance claim is shape/consumer scoped. Require a small numerical oracle against an explicit reference at tractable context, finite/consumed exact-shape outputs, actual H200 identity, allocator/HBM telemetry, and no fallback consumer.

Measure CUDA-event and synchronized wall distributions outside allocation/setup:

1. Sliding decode attention at batch 32, 32 Q heads, 16 KV heads, dim 256, context 1,024.
2. Global decode attention at batch 32, 32 Q heads, 4 KV heads, dim 512 for every context 4,214..4,571, or a deterministic interpolation only if an exact-all-context run cannot fit the budget and its error is bounded by held-out contexts.

Use sufficient warmups/repetitions to expose stable p50/p95. Compute the architecture-weighted attention seconds/request as the sum across all 358 decode positions of `50*t_sliding + 10*t_global(context)`, divided by 32. This actual attention measurement already includes its KV reads; never add the analytical KV floor to it. Add only the measured c32 linears+head value `0.22476958992984145` and compare with both market ceilings. A miss falsifies stock BF16 c32. A pass preserves c32 but remains short of an endpoint claim because prefill, scheduling, sampling, queueing, failures, and reliability are not all represented.

## Conditional same-session residual arm

Prepare one actual pinned-image residual program while attention runs. `RESIDUAL_OPS_TRIGGER` requires valid attention rows, a combined attention+linears+head floor below at least one market ceiling, the residual program start-ready within ten minutes, provider deadline headroom, and a plausible ability for remaining operators to change the decision or materially narrow the next endpoint test.

If true, sequentially measure the concrete pinned-vLLM consumers for the exact c32 shapes/counts of RMSNorm, rotary embedding, SwiGLU/SiluAndMul, KV write/cache reshape when not already inside the attention call, and greedy full-vocabulary sampling/argmax after the already measured head. Count each operator only where the exact Gemma source executes it; avoid double-counting fused work. Require actual symbols/source hashes, finite/consumed outputs, CUDA/wall timing, and an architecture-weighted request total. Add it to linears+head+attention and classify again. If false, persist the typed trigger and clean immediately. No endpoint server, SGLang, prefix arm, MTP, or second allocation is authorized.

## Budgets and terminal

- Wall clock: 65 minutes including image probe, create, measurement, conditional arm, retrieval, and cleanup.
- Provider exposure: 30 minutes; one allocation, no paid repair.
- Compute: 0.5 H200 GPU-hours and 3 local CPU-hours.
- Storage: one 100-GiB provider disk; 6 GiB retained plus 2 GiB project-local temporary; no shared `/tmp`, checkpoint, or model weights.
- Spend: `$1.50` maximum including compute, disk, and other provider charges.

Any pre-GPU or zero-row terminal closes without another create. Write the exact-image consumer probe, final audit, owner/watchdog snapshot, raw attention/residual rows, telemetry, trigger, source/environment manifests, provider/useful/cost accounting, `artifacts/SUMMARY.json`, concise log/status, and authenticated zero-resource cleanup.
