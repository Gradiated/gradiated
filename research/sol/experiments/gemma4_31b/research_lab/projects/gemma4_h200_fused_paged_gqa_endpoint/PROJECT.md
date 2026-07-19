# Gemma 4 H200 fused paged-GQA endpoint

## Question

Can one native-GQA Hopper kernel consume the paged FP8-E5M2 KV cache directly—without dense FP8-to-BF16 gathering or repeated-KV materialization—and remove at least 5% of the exact canonical c32 service time while preserving the exact model computation?

## Why this is the final useful H200 discriminator

The canonical exact-mix endpoint is `0.9194573941250042` seconds/request and already averages `99.284%` GPU utilization. Serving flags, compiler mode, decode split count, mixed chunking, stream interval, larger prefill batches, vLLM E5M2, and TRTLLM/XQA have closed. The prior explicit attention endpoint was numerically correct but `4.2234x` slower because its global route gathered/dequantized paged KV and repeated four KV heads across 32 query heads. At c32 it added 8,389,656,576 bytes per global layer and an analytical 55.1767 TB of decode KV movement per 358-token batch. Its measured terminal explicitly leaves only a fused paged native-GQA kernel as a mechanism that can reopen attention.

This is distinct from the failed TRTLLM/FlashInfer XQA path: use the pinned SGLang/Triton route, preserve head dimensions, page size 1, and FP8-E5M2 KV, and change only the dataflow that gathers/dequantizes and maps grouped queries to KV heads.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: `docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`, SGLang v0.5.12 commit `127b9e3283f7c2a43234b852ff5c9f1796d53624`.
- Checkpoint, conditional endpoint only: eight files and 62,578,655,208 bytes from the authoritative local checkpoint bound in `../gemma4_h200_attention_endpoint_integration/IDENTITIES.json`, whose SHA-256 is `79958515caad9b6e30db161a137a24291be31fb28b68ad982652261913f89516`.
- Canonical comparator: `../gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`.
- Exact runner: SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Causal evidence: `../gemma4_h200_attention_endpoint_integration/artifacts/h200-attention-endpoint-20260718t1638z/ANALYSIS.json`, SHA-256 `c815f4418020f0f2b88762bc9c220a7a03f27bb74f1c7f5911c29d25d2c63568`.

Mechanically re-hash all named inputs before the first paid invocation. Snapshot any shared source or runner under this project before claiming the bench.

## Work

Use one bounded outer mutable-session controller for claim, heartbeat, repairs, and final release. First run a checkpoint-free exact-shape H200 component falsifier. Trace the pinned selected paged-attention source and implement one Triton/CUDA candidate that directly indexes page-1 FP8-E5M2 K/V, applies scales without materializing a full BF16 cache, and maps 32 query heads to the native local/global KV groups without repeated K/V tensors. Cover the exact 50 local 1,024-window layers and ten global layers through their prompt/decode lengths at c32. Compare against the pinned stock paged path with cold/warm control, GPU telemetry, bytes, and a finite numerical oracle.

The component passes only if the measured layer-mix savings conservatively sum to at least `0.04597286970625021` seconds/request (5% of the canonical endpoint), with normalized RMSE at most `0.01`, cosine similarity at least `0.995`, no illegal access, no fallback, and no dense/repeated KV allocation. One candidate invocation is allowed; repair ordinary pre-invocation build/API/path defects in the same claim, but do not try another tile, split, page geometry, backend, precision, or kernel design.

Only after that component pass, stage the exact checkpoint and pinned image on the same retained H200, source-mount the passing kernel without changing checkpoint bytes, and run one canonical c32 exact-mix endpoint. Preserve BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK normalization/RoPE, page size 1, continuous decode steps 1, stream interval 1, KV splits 8, and the frozen requests. Require zero running/queued requests, HTTP-200 cache flush, 32/32 finite nonempty 4,214/358 responses, exactly 17,120 cached and 117,728 fresh prompt tokens, and no fallback. Promote only at `<=0.8734845244187539` seconds/request; retain a smaller valid gain without tuning. A component miss, compile/runtime incompatibility, numerical failure, endpoint failure, or slower endpoint closes the line.

## Limits

- Profile: `deep` until the causal source/geometry/dataflow and first CUDA discriminator resolve; switch to `execution` only if the conditional endpoint becomes routine integration.
- Wall clock: 85 minutes, ending by `2026-07-19T01:16:00Z`.
- Provider lifecycle: one preemptible H200, at most 80 claimed compute minutes, one 250-GiB disk, absolute director watchdog `2026-07-19T01:26:00Z`.
- Spend: at most `$4.40` including provider compute and storage; this consumes the final campaign reservation.
- Temporary project artifacts: 5 GiB excluding the conditional remote checkpoint/image.
- No comparator replay, second kernel, tuning sweep, head-dimension or architecture change, XQA retry, checkpoint rewrite, training, broad quality run, second allocation, or researcher-owned lifecycle mutation.

Retrieve the component/endpoint terminal, raw timings/oracle/telemetry, source and binary identities, server diagnostics if conditional execution occurs, and concise bench contents. Release without teardown for director disposition.
