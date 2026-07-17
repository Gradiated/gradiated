# Group-32-preserving hidden-permutation MoE trunk falsifier

## Question

Do exact coupled hidden-channel permutations expose a shared-trunk plus low-rank routed-expert representation that the raw-order decomposition screens missed, while preserving the checkpoint's group-32 W4 structure and 64-expert/top-4 semantics?

Each 1,536-channel SwiGLU expert is invariant to applying the same hidden-channel permutation to gate/up output rows and down input columns. `moe_shared_trunk_delta_codesign` and `moe_shared_basis_factorization` compared experts in their stored channel order. This project tests whether that arbitrary ordering caused their approximation closes; it is materially separate from the live physical-expert-65 execution lane.

## `$0` experiment

Within 1,200 seconds, 16 GiB RSS, and 96 MiB of new artifacts, use the exact layer-24 routed gate/up/down tensors from `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`. Use no network, provider, checkpoint mutation, shared-code mutation, kernel work, or training.

Start with the prior worst pair `(14,46)`. Align expert 46 to expert 14 using only permutations that preserve down-projection group-32 quantization exactly: jointly permute the 48 contiguous 32-channel groups and deterministically permute channels within each matched group. Use coupled gate-row, up-row, and down-column signatures; record the objective, solver, tie-breaking, tensor/payload hashes, and prove the same permutation preserves exact dequantized SwiGLU/down output and the W4 group/scale association.

After alignment, recompute the exact best-rank-256 tail for each of gate, up, and down expert differences. Fail fast as `PERMUTATION_CLOSE` if any tail exceeds `0.1 * (||W14||F + ||W46||F)` with numerical margin, because two rank-128 expert deltas cannot explain that difference after a common trunk cancels. Also close on any permutation, group-32, or exact-function invariant failure.

Only if the pair certificate survives, align all 64 experts to a deterministic medoid with the same group-preserving rule and evaluate a full-width common trunk plus rank-64/128 expert deltas. Report median/worst per-linear weight error, held-out complete-expert output cosine/relative L2, exact W4 payload, tile legality, and exact c32 top-4 active work: one common gate/up per token, four routed residual branches and nonlinearities, and the mathematically valid common/residual down path. Do not use parameter count or summed FLOPs alone as a wall-time claim.

Return `PERMUTED_TRUNK_CANDIDATE` only if all of the following hold:

- median/worst weight relative error is at most `0.10/0.20` for gate, up, and down;
- held-out complete-expert output cosine is at least `0.98` and relative L2 at most `0.15`;
- exact group-32/payload/tile accounting saves at least `2,343.7 MiB` across the serving model;
- a conservative source-bound complete routed-MoE component path remains at least `1.63x` at c32.

Otherwise return `PERMUTATION_CLOSE`, `APPROXIMATION_CLOSE`, `GEOMETRY_CLOSE`, or `ECONOMIC_CLOSE`. A survivor is synthetic architecture-cost evidence only and may motivate later kernel/training work; it is not deployable quality. Do not prepare a successor.

## Starting evidence

- `../moe_shared_trunk_delta_codesign/`
- `../moe_shared_basis_factorization/`
- `../expert_count_geometry/`
- exact stock c32 `609.606365 tok/s` and fused-MoE wall-share prior `12.374%`
- `../../hardware/L40S.md`
