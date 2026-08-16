# Research log

## 2026-07-27 — single-rank sparse residual recovery terminal

- **Question:** Can one exact Gemma projection combine a native H200 2:4
  E4M3 base with one cost-derived low-rank E4M3 residual and materially recover
  pruning error while retaining a complete positive boundary?
- **Action:** Before reading payload bytes, selected the deterministic middle
  sampled `down_proj` (layer 29, `[5376,21504]`). A closed-form bound against
  measured M32/M384 dense consumers selected the maximum jointly admissible
  128-aligned rank, 512. Implemented and ran one source-complete packed producer
  and BF16 reference consumer on only that tensor/rank.
- **Evidence:** Exact-weight relative L2 changed `0.3481866 → 0.3188157`
  (8.435% recovery); deterministic synthetic-M32 output relative L2 changed
  `0.3491855 → 0.3195506` (8.487%). The complete model remains nominally
  positive at `+0.992 us` M32 and `+6.494 us` M384, mapping conservatively to
  `0.000182635 s/request` (0.0292%) without M32 credit. All representation and
  finite-output checks passed; the pre-payload 25% material-recovery checks
  failed. The qualified SGLang image records no cuSPARSELt or exact sparse-E4M3
  adapter; a separate TensorRT-LLM image's library presence is not an exact
  current-runtime consumer.
- **Interpretation:** Typed `none_insufficient_residual_recovery`. A positive
  hardware opportunity cannot promote a correction that recovers only ~8.4%
  of the required information. No quality or deployability claim is made.
- **Next:** Close without rank/layer/kernel/threshold sweeps or GPU spend.
  Terminal: `SPARSE_LOWRANK_RESIDUAL_OFFLINE_TERMINAL.json`.
