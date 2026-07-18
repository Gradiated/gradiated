# Gemma 4 global-head-256 sliced endpoint

## Question

Can the nominated global-head-256 architecture proxy be realized as an actual pinned-SGLang H200 endpoint, using a deterministic load-time slice of only the ten full-attention layers, and retain at least a 5% exact-workload service gain?

This is an exploration endpoint for a targeted model/chip co-design change, not a production checkpoint. The slice is explicitly non-quality-preserving and only tests runtime realization, service performance, and cheap coherence. A passing arm still requires training or distillation plus GPQA-Diamond, TauBench, tool behavior, and full feature validation.

## Why it matters

The exact H200 component result measured `0.10425018715593391` seconds/request of complete saving, `11.3382%` of the canonical endpoint, when the ten full-attention layers use head dimension 256 rather than 512. Native-GQA Triton decode was supported, deterministic, avoided dense KV repetition, and matched a dequantized E5M2 oracle with cosine `0.9999986291` and normalized RMSE `0.00202139`. The failed XQA path remains closed; this endpoint uses canonical Triton only.

Gemma 4's 50 sliding layers already use dimension 256. The intervention changes only the ten full-attention layers (`5, 11, …, 59`): reshape each query or key projection by head, keep the first 256 coordinates of every head, keep matching output-projection columns, slice Q/K normalization weights, and preserve the checkpoint's full-attention K=V sharing. Do not delete layers, change hidden size, alter local attention, or touch MLP/MoE/embedding/head weights.

## Immediate experiment

Reuse warm bench `h200-attention-endpoint-e00vbbb709tzxscaan`, the resident exact eight-file checkpoint, and the pinned SGLang image. Before claiming, materialize a content-addressed source/loader patch and an immutable copy of the exact request runner. Use proven launcher `../gemma4_h200_fused_qk_norm_rope_endpoint/run_candidate.sh` as the launch basis, changing only the model override and load-time global-attention transform required by this intervention.

The loader must inspect real checkpoint tensor names and shapes, reject any unbound layout, and record before/after shapes for every transformed tensor. It must leave the resident checkpoint bytes unchanged. Launch one candidate with the full retained baseline: c32, BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK normalization/RoPE, Triton prefill/decode, page size 1, eight KV splits, max prefill 16,384, continuous decode steps 1, mixed chunk disabled, and stream interval 1. Prove the resolved full/local head dimensions are both 256, exactly ten layers were transformed, K=V sharing remains active, and no other parameter changed.

After readiness:

1. Run a tiny deterministic coherence set for instruction following, `2+2`, and one simple structured response. Record raw text and rule results. A failure blocks quality nomination but does not invalidate the performance measurement.
2. Prove zero running/queued requests and an HTTP-200 cache flush.
3. Invoke the immutable exact 32-request 4,214/358 runner once. Require 32/32 finite nonempty outputs, exact frozen request identity, and exactly 17,120 cached / 117,728 fresh prompt tokens.

Compare only to canonical terminal SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3` at `0.9194573941250042` service seconds/request. Endpoint performance passes at `<=0.8734845244187539`. Record raw SSE/rows, phase/cache/queue metrics, GPU telemetry, server logs, transformed-tensor manifest, patch identities, and a typed terminal. A performance pass with failed coherence remains a research-only distillation candidate; a performance and coherence pass nominates the change for a separately authorized training/quality decision. Unsupported loading, invalid outputs/cache accounting, or slower service closes this slice realization.

## Bound identities and limits

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Checkpoint: exactly eight files and 62,578,655,208 bytes at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Image: `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Exact runner SHA-256: `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Proven launcher SHA-256: `c7e381576c23229a67fa3210fdb43b7577fe04c5fd53f021e6511df9dd10affc`.
- Pinned Gemma model source SHA-256: `17d17e54ec25a593504d46a92abbe8014e704dc95aede01d2f34ebbaf655b68c`.
- Pinned model-config source SHA-256: `95e3d09ab9ed64e5cb43d8785231ecd3ca5b3d45a037717979fc3d8306834258`.
- Nominating component result SHA-256: `9ebc88c31731a2365a490b1fe1ca2d5a4870cb6d08547396d67fb65d722d8df5`.

Use `researcher_profile: deep`. Keep one bounded durable owner in this project if patching, load, or capture outlives a researcher response. Finish the claim by `2026-07-18T23:20:00Z`, use at most 90 H200 minutes, 8 GiB temporary storage, and `$3.75` provider exposure, then release without teardown. One pre-invocation loader/runtime repair may repeat only the invalidated operation inside the same claim. Admit no second scientific candidate, slice/rank/dimension/backend/chunk/concurrency sweep, comparator replay, checkpoint rewrite, training, broad quality run, provider allocation, or researcher lifecycle mutation.
