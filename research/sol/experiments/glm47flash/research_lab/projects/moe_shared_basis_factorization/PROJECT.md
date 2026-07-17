# Shared-basis routed-MoE factorization

## Question

Can the 64 routed experts share learned input/output bases while retaining expert-specific reduced group-32 W4 cores, reducing active SM89 work enough for at least a 5% full47 endpoint path without the large approximation failure of the closed additive trunk-plus-delta design?

## Why this is distinct

`moe_shared_trunk_delta_codesign` tested an additive global trunk plus low-rank expert differences and failed one exact pair. This project instead tests a two-sided common subspace, `W_e ≈ U C_e Vᵀ`, with an expert-specific reduced core. The intended execution is one or two well-filled shared projections plus small routed W4 cores, preserving 64 logical experts and top-4 routing. It is an explicitly non-quality-preserving architecture-cost proxy; training/recovery is out of scope.

## `$0` falsifier

Within 1,200 seconds, 16 GiB RSS, 96 MiB new artifacts, and no provider/network/shared-code mutation:

1. Bind exact layer-24 routed gate/up/down tensors from `/root/.cache/glm47flash-awq-ab31d120`, checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
2. Fit deterministic shared input/output subspaces across all 64 experts at tile-legal ranks in `{128,256,384,512}` and expert-specific cores; do not substitute the prior additive trunk/delta form.
3. Report per-linear/per-expert relative Frobenius error, singular tail, held-out random-activation relative L2/cosine, exact parameter bytes, active FLOPs, group-32/tensor-tile legality, and the projected shared/core GEMM shapes at c32.
4. Translate only source-bound work savings through the measured fused-MoE wall share. A candidate needs a conservative component path of at least `1.63x`—enough for a 5% endpoint gain from the `609.606365 tok/s` stock c32 point—not merely fewer parameters.

Return `BASIS_CANDIDATE` only if one rank is tile legal, reduces routed-linear active work by at least 40%, has median/worst expert relative Frobenius error at most `0.10/0.20`, and held-out activation cosine at least `0.98` with relative L2 at most `0.15` for gate/up/down, while retaining a conservative `>=1.63x` component execution path. Otherwise return `APPROXIMATION_CLOSE`, `ECONOMIC_CLOSE`, or `GEOMETRY_CLOSE`. Label every result synthetic architecture-cost evidence. Do not prepare a kernel, checkpoint, training run, controller, or successor.

## Available evidence

- exact current-AWQ checkpoint and layer geometry
- `../moe_shared_trunk_delta_codesign/` negative additive-form evidence
- `../expert_count_geometry/` and `../expert_sorted_marlin_moe_sm89/`
- stock c32 `609.606365 tok/s`, fused-MoE wall share prior `12.374%`
- `../../hardware/L40S.md`
