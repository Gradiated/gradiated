# Gemma 4 H200 local-KV-head discriminator

## Question

Does changing the 50 sliding-attention layers from 16 to 8 KV heads, while retaining 32 query heads, head dimension 256, all 60 layers, MLP width, residual width, and global-attention geometry, reduce the exact H200 fused-QKV plus paged-KV boundary by at least 5% of the measured `0.3633031778124973` seconds/request endpoint?

This is a checkpoint-free hardware discriminator for one small architecture change. It is not evidence that an untrained 16→8 checkpoint is usable. Exact sampled weights already falsify a no-training adjacent-head merge, so checkpoint conversion and quality work remain forbidden unless the measured mechanism passes.

## Why it matters

The completed co-design proxy nominates this as the only model/chip change with both material work relevance and an established recovery method. Across the 50 local layers, 16→8 KV heads changes the c32 fused-QKV shape from `[32,5376,16384]` to `[32,5376,12288]`, removes `150,156,083,200` compulsory decode KV bytes/request, and has a measured-anchored relevance estimate of 10.98%. The physical risk is decisive: the assumed H200 QKV grid falls from 128 blocks to 96, so underfilled-SM and fixed-launch costs may erase the nominal savings. A direct exact-shape measurement is cheaper and more informative than training first.

## Bound identities and evidence

- Model identity: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime image: `docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`, pinned SGLang v0.5.12 source lineage.
- Co-design result: `../gemma4_small_architecture_chip_codesign/artifacts/exact-shape-proxy-20260718T1538Z/RESULT.json`, SHA-256 `b85d11488e4ba85a4b472e70b818985bd4c660802ca9e8f575c845367a694d0b`.
- Co-design status/nomination: `../gemma4_small_architecture_chip_codesign/STATUS.json`, SHA-256 `bc7a6f58319c17751eadb46440b2063f708cb755763f766bb65b1efee6627861`.
- Exact-mix canonical reference: `../gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, used only to report transfer relevance; the preregistered discriminator gate remains 5% of the measured `0.3633031778124973`-second endpoint that anchors the co-design proxy.

Mechanically re-hash these files before the first paid invocation. Snapshot any shared source or benchmark bytes under this project before claiming the bench.

## Direct experiment

Use the director-allocated shared H200 and one retained mutable development claim. Inspect the pinned fused-QKV and selected page-1 FP8-E5M2 paged-attention paths, then implement the smallest exact-shape benchmark that compares baseline 16-head local KV against candidate 8-head local KV without dense repeated-KV materialization or fallback.

Measure paired, randomized baseline/candidate rows for:

- fused-QKV `[32,5376,16384]` versus `[32,5376,12288]`;
- matched local paged-KV write/read and attention at 1,024-token window, 32 query heads, head dimension 256, page size 1, and the campaign's 4,214-prompt/358-output decode geometry;
- enough repetitions and cold/warm controls to resolve launch, HBM/L2, and active-SM-wave effects.

Consume every output and require finite nontrivial results. Record CUDA-event and synchronized-wall timing, selected source/operator identities, allocation deltas, achieved bandwidth, active blocks/SM waves, launch count, and the smallest available DRAM/L2/warp counters. Missing optional counters may limit interpretation but does not erase valid timings.

The component passes only when the conservative 50-layer aggregate saves at least `0.0181651588906249` seconds/request, with no fallback, illegal access, dense/repeated KV allocation, or numerical failure. Report the implied fraction of the later `0.9194573941250042`-second exact-mix endpoint as a derived transfer bound, not an endpoint claim.

On pass, stop after preserving the discriminator terminal and release the bench ready. The next director turn may retain the same bench and extend this same project into bounded GQA checkpoint conversion and cheap retrieval/coherence gates. On miss, close the 16→8 local-head line without training, endpoint staging, or a more aggressive head-count sweep.

## Limits

- Researcher profile: `deep` for source/geometry/accelerator causal reasoning.
- Wall clock: 120 minutes, ending by `2026-07-19T14:17:22Z`.
- Shared H200 claim: at most 70 minutes; one scientific candidate program with in-place repair of ordinary pre-invocation build/API/path defects.
- Provider exposure authority: `$6.00` including the director-created preemptible H200 and disk; absolute cleanup watchdog `2026-07-19T14:47:22Z`.
- Storage: one 100-GiB provider disk; 5 GiB retained project artifacts plus 3 GiB temporary.
- No checkpoint transfer, model load, training, distillation, endpoint run, broad quality evaluation, second architecture candidate, tile/split sweep, second allocation, or researcher-owned provider lifecycle mutation.

Retrieve a typed terminal, exact program/source hashes, paired raw rows, numerical/allocation oracles, and telemetry. Release without teardown for director disposition.
