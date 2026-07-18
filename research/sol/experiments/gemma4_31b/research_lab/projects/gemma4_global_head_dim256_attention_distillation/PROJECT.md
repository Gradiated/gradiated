# Falsify modest layerwise recovery for the global head-256 architecture

## Question

Can one bounded layerwise teacher-distillation pass recover basic language coherence for the measured global-head-256 architecture while preserving its endpoint performance advantage?

## Why this matters

The exact sliced endpoint measured `0.8354320380624358` seconds/request, `9.13858%` faster than the canonical `0.9194573941250042` endpoint. Restoring the original 128-coordinate rotary subspace produced an exact inverse-frequency match but did not change the repetitive `la/L/de` failure, so the untrained first-coordinate slice is conclusively not quality-credible. The campaign explicitly allows small architecture changes recoverable with modest post-training; another coordinate, rotary-factor, or dimension sweep would not answer whether the measured headroom is usable.

## Hypothesis

Freeze the entire original model except the compressed Q/K/O and Q/K-normalization tensors in the ten full-attention layers. Starting from the content-addressed RoPE-preserving head-256 overlay, fit those tensors once against original-model full-attention outputs on representative frozen prompt bodies. If the lost subspace is recoverable without changing model depth, hidden width, local layers, routing, or runtime geometry, held-out block fidelity and all three cheap coherence rules should improve enough to justify one exact endpoint measurement.

## Scope and scientific program

Before claiming the GPU, materialize the 32 frozen 4,214/358 request bodies under this project and verify their aggregate manifest SHA-256. Use request indices where `index % 4 == 3` as the eight immutable holdout prompts and the remaining 24 as training prompts. Content-address the capture/training implementation, exact token sampling, optimizer, loss weights, update count, and seed before claim; they may not be swept after the scientific run starts.

Claim warm bench `h200-attention-endpoint-e00vbbb709tzxscaan` once with a bounded durable owner. Use the resident read-only checkpoint and pinned image to:

1. Load the unmodified head-512 teacher and capture only the inputs and outputs needed to supervise the ten full-attention blocks on the fixed train/holdout split. Do not benchmark or broadly evaluate the teacher.
2. Train one content-addressed overlay for only the candidate's 50 compressed tensors, initialized from the RoPE-preserving head-256 patch. Freeze every other tensor. Stream or subsample activations within the storage budget and record per-layer train and holdout cosine/NRMSE against both the untrained candidate and teacher.
3. Load that overlay once in the exact head-256, 128-rotary-coordinate Triton runtime. Run the three frozen coherence prompts once. If any fails, emit a typed recovery negative and stop.
4. Only if all three coherence rules pass, prove idle state, flush with HTTP 200, and invoke the frozen c32 exact-mix runner exactly once.

Ordinary pre-invocation launcher/path/API/telemetry defects may be repaired in place without changing the intervention. The trained overlay is a new scientific candidate; there is no second training schedule, seed, loss, coordinate set, or candidate invocation.

## Decision gates

- Exactly ten full-attention layers and exactly 50 trainable/overlaid tensors; every other model tensor remains frozen and the resident checkpoint remains unchanged/read-only.
- The candidate retains head dimension 256, full-attention rotary width 128, Triton attention, BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK/RoPE, page size 1, KV splits 8, max prefill 16,384, continuous steps 1, mixed chunk disabled, and stream interval 1.
- Held-out aggregate block NRMSE must decrease and held-out cosine must increase versus the untrained RoPE-preserving candidate; report every layer and reject a result supported only by training loss.
- All three frozen coherence rules must pass before endpoint timing.
- Conditional endpoint gate: 32/32 valid requests, exactly 17,120 cached and 117,728 fresh prompt tokens, and service time `<=0.8734845244187539` seconds/request.
- Passing this project only nominates the overlay for later GPQA-Diamond and TauBench. It does not authorize a production or quality claim.

## Limits

- Finish by `2026-07-19T00:25:00Z` within 90 wall-clock/H200 minutes and `$4.25` provider exposure at `$2.46/hour`.
- Use at most 32 GiB temporary capture/training storage and 4 GiB for the final overlay; reserve 15 minutes for artifact retrieval and bench release.
- No coordinate/dimension/rotary/attention-scale sweep, second training run, comparator timing replay, broad benchmark, checkpoint rewrite, local-layer or MoE change, provider allocation, or researcher lifecycle mutation.
- OOM, non-finite training, failure to improve held-out fidelity, coherence failure, conditional endpoint failure, or deadline exhaustion is terminal for this recovery line.
- Release without provider teardown and preserve useful resident checkpoint/image/cache state.

## Bound evidence and inputs

- RoPE-preserving coherence-negative terminal: `../gemma4_global_head_dim256_rope_preserving_endpoint/artifacts/global-head256-rope-c32-resume-20260718t2250z/TERMINAL.json`, SHA-256 `f9226e55b48b96e32d22cb6c915aa749513dbc6d0a7d31062f2a1efb4b52c9ee`.
- Promoted head-256 endpoint terminal: `../gemma4_global_head_dim256_sliced_endpoint/artifacts/global-head256-sliced-c32-resume-20260718t2225z/TERMINAL.json`, SHA-256 `ffecdc4a6072189e0156463ae8c17c5371124f360c4aaf76cee2855d1cef8142`.
- RoPE-preserving patch manifest: `../gemma4_global_head_dim256_rope_preserving_endpoint/PATCH_MANIFEST.json`, SHA-256 `22d466c3d4f7b2b22151fa45161271e0dd4ef12dd0cefc9c767808a83794ec1f`.
- RoPE-preserving model source: `../gemma4_global_head_dim256_rope_preserving_endpoint/patch/gemma4_causal.py`, SHA-256 `63c6e3151ae46fb05accfd71b23281d7a350e6fb8bbbd9cbef5903f0f065dc25`.
- Proven launcher: `../gemma4_global_head_dim256_rope_preserving_endpoint/launch_owner.sh`, SHA-256 `f119b311bfb41d5d342866db3497dfdf8a0feb827f3bef2663a7fb2183e3a556`.
- Frozen exact runner: `../gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Frozen calibration bodies: 32 `request-*.json` files under the promoted endpoint's `exact-mix/` artifact, path-independent sorted basename/SHA-256 manifest digest `e73a44c6fdaa84caaee5c9303c3295e84f39a3876130acda1c54c3ba90fc01aa`.
- Canonical comparator terminal: SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`.
- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Image: `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Checkpoint: eight files, 62,578,655,208 bytes at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
