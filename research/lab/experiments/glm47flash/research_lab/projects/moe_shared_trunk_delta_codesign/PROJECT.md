# Shared-trunk plus routed-delta MoE co-design

## Decision question

Do the real routed W4 experts admit one global trunk plus tile-friendly low-rank expert deltas that preserves 64 logical experts and top-4 routing while clearing both the full47 memory and L40S throughput floors?

This is an offline architecture screen, independent from exact-weight executor work. It measures decomposition and functional geometry only and must not build a routing kernel, launch training, or mutate provider state.

## `$0` fail-fast contract

Use the already-local pinned image and `/root/.cache/glm47flash-awq-ab31d120`; install nothing and use no provider. Finish the certificate within 600 seconds.

- Run analytical payload/work gates before dequantization. Across 46 layers, global ranks 64/128 save about `10,807.258/6,943.258 MiB` and have ideal active-FLOP ratios `3.097x/2.526x`; rank 256 loses about `784.742 MiB` before metadata and is inadmissible.
- Start with layer 24 gate projection only. Preregister a deterministic pair selection, such as the maximum Frobenius distance among pairs `(i,i+32)`, then hash/dequantize those exact group-32 W4 tensors. Compute the exact best-rank-256 SVD tail of `W_e-W_f`. If it exceeds `0.1 * (||W_e|| + ||W_f||)` with a recorded numerical margin, no common trunk plus rank-128 per-expert deltas can meet the per-expert 0.10 Frobenius gate; close.
- If not falsified, return only `PAIR_SCREEN_SURVIVES` with the tensor hashes, selection rule, norms, singular-value tail, tolerance, and margin. Do not fit all 64 experts or evaluate the full SwiGLU/down function in this turn; that would require a separately admitted follow-up.
- Keep 4/8 clusters as representation diagnostics only. Without exact router traces, charge up to four trunks/token; their ideal active-FLOP ratios are only about `0.932x/0.873x` at ranks 64/128, so they cannot nominate execution work.

A representation survivor requires at least 99% retained weight energy (approximately relative Frobenius error `<=0.10`) and at least `2,343.7 MiB` exact memory saving. Moving the optimistic full47 reference from `585.046` to `606.355 tok/s` requires a `3.514%` wall improvement; against the measured `12.374%` fused-MoE share, the later component floor is `1.397x`. This CPU screen may return one representation/payload/ideal-work survivor, but cannot claim that measured speed floor.

Return `PAIR_DIFFERENCE_CLOSE` or `PAIR_SCREEN_SURVIVES`. Do not train, fit the full decomposition, use a GPU/provider, build an endpoint, or implement routing.

## Starting evidence

- `../expert_count_geometry/`
- `../adaptive_moe_architecture/`
- retained L40S V24R2/V25R1 attribution
- `../../hardware/L40S.md`
