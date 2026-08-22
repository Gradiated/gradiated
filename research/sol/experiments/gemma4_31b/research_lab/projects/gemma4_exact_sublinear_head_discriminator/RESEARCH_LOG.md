# Research log

## 2026-07-28T11:31Z — exact centroid-radius block discriminator rejected

- **Question:** can a compact exact index over Gemma 4's tied
  `262144 x 5376` BF16 head certify enough vocabulary blocks irrelevant to
  justify a target-GPU component?
- **Action:** inspected the pinned Gemma 4 runtime's final-hidden-to-tied-head
  call and exact checkpoint geometry, materialized the admitted 1,536-row c32
  capture under `inputs/`, then implemented a contiguous 128-row block index.
  Each block stores its FP32 centroid and guarded maximum L2 residual radius;
  traversal evaluates blocks in upper-bound order and stops only when every
  skipped block is below a guarded exact-score lower bound. The measured set
  is one final-depth row from each of 32 requests in capture index 3.
- **Evidence:** `artifacts/CENTROID_BLOCK_DISCRIMINATOR_RESULT.json`
  (`5a7db872acc7fc2a303afbd8b22c4a7f08b085c8dcece937a59c07e5a9af1141`)
  binds the exact 49.78 GB shard hash, raw tied-tensor hash, and capture hash.
  Dense agreement is 32/32 and all skips certify, but mean vocabulary
  evaluation is 98.4619% (98.4375% minimum, 99.2188% maximum). The 45,105,152
  byte index built in 1.951 seconds; its bound pass is another 0.7818%
  dense-equivalent FLOPs. Mean total analytical work is therefore 99.2437%
  and the worst row is 100.0006%. More physically, index plus verified-weight
  traffic is 100.0616% of dense on average and 100.8187% at worst. Coordinator
  CPU p50 is 2.12997x dense; this is diagnostic, not target-hardware timing.
- **Interpretation:** typed mechanism rejection. High-dimensional within-block
  residual radii swamp the token margin, so certification removes too few
  rows. Even a deliberately ideal FLOP-only conversion saves at most
  0.00008220 seconds/request on the average observed row (0.01315% of the
  qualified 0.625149102 seconds/request), while the conservative worst-row
  saving is zero and byte traffic is already worse than dense. This component
  evidence is not endpoint performance.
- **Next:** close the contiguous centroid-L2 block mechanism. Any successor
  must use a materially tighter representation than one centroid and scalar
  radius per 128 tied rows; do not spend a target-GPU component on these bytes.

## 2026-07-28T11:42Z — rank-384 anisotropic certificate closes broader line

- **Question:** can a materially tighter low-rank residual certificate make
  exact sublinear head evaluation worthwhile on the same exact c32 states?
- **Action:** built a rank-384 FP64 SVD basis from all rows of disjoint capture
  index 2, projected every exact tied-weight row into that subspace, and stored
  per-token orthogonal-residual, residual-leakage, and full-weight norms. On
  one final-depth row for each of 32 requests from capture index 3, traversal
  aggregated per-token bounds into 128-row blocks and independently recomputed
  dense FP64 top-1.
- **Evidence:** `artifacts/LOWRANK_ANISOTROPIC_DISCRIMINATOR_RESULT.json`
  (`0ca156b4fca9dca10942d204488130ee0207bd709b093f3c78362046fcf4faf5`)
  reports 32/32 agreement and valid skip certificates. Held-out residual norm
  is 13.1984% on average. Mean exact evaluation falls to 78.0518%, including
  five rows below 10%, but 16/32 rows still evaluate the entire vocabulary;
  p50 is 97.6562% and p90 is 100%. The 828,112,896-byte index builds in
  27.004 seconds including the basis. Bound-plus-verification FLOPs are
  85.5713% of dense on average, while streamed index-plus-weight bytes are
  107.4323% on average and 129.3806% at worst. Exact traversal-only CPU p50 is
  already 1.1036x dense before bound evaluation; this is diagnostic only.
- **Interpretation:** close the broader certified-index line. The anisotropic
  basis fixes the centroid bound's isotropy and proves that high-margin rows
  can prune aggressively, but typical low-margin rows consume nearly all tied
  weights after also streaming the index. Even an ideal half-sized FP32 index
  leaves median traffic at 112.3465% of dense, so a precision-only index
  repair does not change the decision. Conservative worst-row whole-request
  saving is zero; this is component evidence, not endpoint performance.
- **Next:** no target-GPU component for certified exact-head pruning on this
  evidence. Any future head change must alter the scientific contract rather
  than iterate another exact certificate over these same weights and captures.
