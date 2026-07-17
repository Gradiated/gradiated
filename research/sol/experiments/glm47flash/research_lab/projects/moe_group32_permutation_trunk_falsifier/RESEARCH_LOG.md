# Research log

## 2026-07-16 — Director opening handoff

The prior additive-trunk and two-sided-basis closes assumed stored hidden-channel correspondence across experts. Test the exact coupled SwiGLU permutation symmetry without weakening the W4 contract: only 32-channel group permutations plus within-group permutations are allowed, coupled across gate/up rows and down columns. Fail fast on the existing layer-24 pair `(14,46)` rank-tail certificate; fit all 64 experts only if that necessary condition survives. One `$0` terminal turn, no kernel/training/provider/successor work.

## 2026-07-16 — Exact pair certificate: `PERMUTATION_CLOSE`

Question: Can the allowed coupled group-32 hidden permutation reduce the layer-24 `(14,46)` rank-256 difference tails enough for a common trunk plus rank-128 expert deltas?

Action: Ran the local CPU certificate over the exact pinned compressed-tensors signed-INT4/BF16-scale W4 gate/up/down payloads. It builds full normalized coupled signatures from gate rows, up rows, and down columns; solves deterministic minimum-cost assignments inside each 32-channel group, then across the 48 groups; applies the resulting bijection to expert 46; and recomputes exact SVD tails. Artifact: `artifacts/LAYER24_PAIR_GROUP32_PERMUTATION_CERTIFICATE.json` (`e497938c…6a13a4d`). No network, provider, GPU, checkpoint, or shared-code mutation; elapsed `24.537 s`.

Evidence: The permutation is bijective and the paired group-W4 payload/scale association remains intact. The complete expert-46 SwiGLU/down output agrees with its original form to relative L2 `3.9006e-07` (FP32 arithmetic). Nevertheless every necessary tail fails: gate `88.98585 / 17.38257 = 5.1193x`, up `94.16895 / 18.10981 = 5.1999x`, and down `63.48097 / 12.24387 = 5.1847x` (tail/tolerance).

Interpretation: This exact allowed symmetry reduces none of the pair certificate enough to make two rank-128 residuals plausible after the common trunk cancels. The fail margins are `+71.6033`, `+76.0591`, and `+51.2371` Frobenius respectively, so numerical tolerance or the tiny FP32 function-invariance residual cannot change the close. The 64-expert fit is therefore not admissible.

## 2026-07-16 — Director scope audit

Keep the close, but narrow the claim. The assignment optimizes normalized pointwise Frobenius signature cost, not the rank-256 tail itself, so the artifact is a strong negative for the preregistered deterministic alignment rather than an exhaustive optimum over every allowed coupled permutation. The epsilon term also cannot implement a true lexicographic assignment tie-break because its total is constant, although fixed traversal preserves determinism. This does not admit the all-expert fit or a successor under the project's one-certificate stop rule.
