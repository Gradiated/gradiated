# Depth plus MLA capacity co-design

## Question

Can the smallest recoverable MLA latent/value-rank reduction, combined with the physical 39-layer student, robustly admit the campaign's c32 workload on L40S and create a better background-cost operating point than the student alone?

## Why it matters

The materialized 39-layer student attacks full-block work and has a derived 631.312-tok/s c16 endpoint bound, but its projected c32 peak is 47,291 MiB, 1,223 MiB above the 46,068-MiB card limit. Its c24 projection is admissible but leaves higher background concurrency unexplored. The earlier standalone MLA screen found that rank 256 makes a better BLOCK_N=64/stage-2 tile legal yet transfers only 3.25% endpoint benefit, so MLA alone closed. In combination, a milder rank change may instead be valuable for the discrete c32 capacity transition while depth supplies the economic work reduction.

## Relevant evidence

- `../distilled_depth_student_architecture/distilled_depth_student_bound.json` and the content-addressed student manifest bind the 39-layer weight/KV/economic geometry.
- `../l40s_model_chip_codesign/RANK_TILE_BOUND.json` binds ranks 512/384/256, L40S shared-memory legality, exact token-state accounting, and the weak standalone endpoint transfer.
- `../current_awq_saturation_bound/` closes higher concurrency for the full-depth checkpoint, not for a physically smaller student.
- `../../hardware/L40S.md` is the target resource model; the campaign gate is 594.466 output tok/s or `$0.514/M` at `$1.10/L40S-hour`.

## Scope

At zero provider spend, screen the minimum useful MLA change for the exact 39-layer student. Include ranks 448, 384, 320, and 256 only where the checkpoint tensors, config, pinned vLLM loader, attention kernel, rotary/nope/value dimensions, quantization geometry, and L40S tiles are source-supported. Recompute exact W4/BF16 weight bytes, per-token KV state, c16/c24/c32 peaks, allocator/workspace headroom, arithmetic work, and conservative endpoint economics. Require at least 3 GiB of c32 card headroom rather than treating nominal fit as admission.

Separate capacity benefit from kernel benefit: do not credit the rank-256 BLOCK_N=64/stage-2 path unless exact source geometry proves it, and do not transfer the old full-depth saturation result as a student throughput measurement. Use sensitivity anchored to the paid student's c16/c24 gate and state what c32 result would still be required. Build a small source-bound config/tensor/shape fixture for the best minimal-rank candidate only after the analytical screen passes; do not materialize another full checkpoint unless the exact loader path and conservative economic case both pass.

No provider, CUDA, shared-launcher edit, training, distillation, or quality claim is authorized. Treat checkpoint similarity or published rank-recovery evidence only as a labeled recovery prior.

## Available resources

- Student checkpoint: `/root/.cache/glm47flash-awq-student39-183247870f89`.
- Source checkpoint: `/root/.cache/glm47flash-awq-ab31d120` and BF16 geometry at `/root/.cache/glm47flash-bf16-33faccf4`.
- Shared traces and tools: `/root/workspace/research/sol/experiments/glm47flash/campaign_100` and `/root/workspace/research/factory/tools`.
- Fresh accelerator prices: `/root/workspace/research/factory/data/gpu_prices.json`.

## Artifact contract and portfolio decision

Produce `DEPTH_MLA_C32_BOUND.json`, `depth_mla_c32_fixture.py`, and `RESEARCH_LOG.md` with measured, source-bound, derived, and inferred labels. Nominate at most one later c32 arm only if the minimal supported rank has at least 3 GiB conservative L40S headroom, an exact pinned-loader representation, and a conservative path to at least 594.466 output tok/s beyond what the paid c16/c24 session already resolves. Otherwise close this interaction at `$0`.

## Director audit invalidation — Cycle 54

Do not materialize the nominated rank-256 checkpoint. The inherited student c32 formula omitted removed AWQ weights, overstating student39 c32 peak by 2,831.483 MiB. Correct values are 44,459.517 MiB / 1,608.483 MiB headroom at rank 512; rank 448 has 2,856.483 MiB and fails the 3-GiB rule, while rank 384 has 4,104.483 MiB and is the smallest screened rank that passes. The same bug changes student34 from 217 MiB to 4,818.160 MiB of c32 headroom. The fixture's `loader_static_contract_passes` is only a shape/divisibility check: no transformed checkpoint, runtime load, compile, throughput, recovery, or quality evidence exists. Quarantine `DEPTH_MLA_C32_BOUND.json` as invalid for nomination. Retain rank 384 only as a later conditional fallback after direct stock-rank student measurements; no further work is delegated in this project now.
