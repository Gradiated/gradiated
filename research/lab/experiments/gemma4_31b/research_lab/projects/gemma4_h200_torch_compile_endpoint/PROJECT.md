# H200 Torch-compiled endpoint

## Question

Can pinned SGLang's Torch-compiled execution path fuse enough of Gemma 4 31B's remaining elementwise, normalization, activation, and residual work to reduce exact-mix H200 service cost when stacked on the retained dynamic-chunking and fused-QK/RoPE baseline?

## Why this matters

The campaign now has two simple compatible wins: dynamic chunking at 2,048 tokens improves service time 4.05%, and fused QK normalization/RoPE adds another canonical 1.198%. The endpoint still runs BF16 dense weights and compulsory per-layer residual, RMSNorm, and gated-activation work. The pinned runtime exposes `--enable-torch-compile`; one full-runtime consumer is the shortest way to learn whether compilation removes material launch/intermediate overhead. This is a distinct runtime/compiler intervention, not further tuning of chunk size or the QK/RoPE fusion.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM, protected through `2026-07-18T18:48:52Z`.
- Working comparator: `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.919457394125` service seconds/request.
- Comparator cache accounting: 17,120 cached and 117,728 fresh prompt tokens, 12.6957759848% cache reads.
- Exact runner: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.

These identities were mechanically extracted from the canonical terminal, runner, and live bench inventory. Do not substitute a checkpoint, image, workload, or model revision.

## Immediate experiment

Claim the warm bench and stop only the currently loaded fused server. Relaunch from the resident image/checkpoint with the complete working baseline—c32, BF16 weights, FP8-E5M2 KV, dynamic chunking at 2,048, and fused QK normalization/RoPE—plus the pinned runtime's Torch-compile path and the minimum required compile/graph binding for batch sizes through 32. Change no other scientific variable. The exact launch is the compile discovery: allow one ordinary explicit flag/API repair, but do not implement a new compiler backend or open a preparation successor.

Require readiness and proof that compilation was actually enabled and consumed. Before timing, prove zero running/queued requests and record an HTTP-200 cache flush. Invoke the unchanged runner once in a fresh output root and retrieve raw rows, compile/path identity, compile/load time, cache/phase/power/memory/queue telemetry, logs, and a typed terminal. Do not rerun the comparator.

## Decision gate and limits

- `promote`: verified compiled path; 32/32 exact, finite, nonempty/coherent rows; exact comparator cache accounting; service time at most `0.873484524419` seconds/request (at least 5% incremental improvement).
- `retain_incremental`: the same path, correctness, and cache gates; any improvement below `0.919457394125` with no material reliability regression. Retain without compile-option tuning.
- `negative`, `unsupported`, `compile_timeout`, `quality_sanity_failure`, or `owner_failure`: no improvement, wrong/uncompiled path, invalid outputs/cache accounting, or bounded startup/compile failure.

Maximum claim: 21 GPU minutes and `$0.90` at `$2.46/hour`, ending by `2026-07-18T18:44:00Z`. Release without teardown. Do not transfer the checkpoint, pull the image, rerun the comparator, sweep compiler/graph modes, alter chunk size or concurrency, mount the rejected attention patch, run broad quality, allocate hardware, or extend the watchdog.
