# Research log

## 2026-07-27T01:10Z — exact coordinate-envelope owner launched

- Question: can a rigorous blockwise bound certify the frozen Gemma tied-head
  top-1 while beating the 4.182976 ms dense H200 component?
- Action: implemented a coordinate-hyperrectangle upper bound
  (`h_pos·block_max + h_neg·block_min`) with a conservative FP32 reduction
  guard, exact rescoring, per-row skip certificates, complete-output
  checksums, a real dense CUDA baseline, warm event timing, and a retained
  repair owner. Materialized the 1,536-row capture and capture terminal under
  `inputs/` with their admitted hashes before the claim.
- Evidence: reservation `2.00 USD` is durable; later binding
  `DIRECTOR_EXACT_BLOCK_BOUND_H200_CLAIM_20260727T0100Z.json` opened only bench
  `h200-causal-head-e00b9qw8d6qd7wrjj1`. The controller-local detached owner
  is PID `2236177`, start ticks `123063995`; the pool records the continuous
  claim at `2026-07-27T01:10:22.676483Z`, and immutable remote staging crossed
  into `attempt-0.launch_attempted.json`. The atomic pool accepted that claim
  22.676 seconds after the binding's `01:10:00Z` claim cutoff; preserve this
  timing deviation when interpreting or adopting the result.
- Interpretation: the scientific sample is not yet classified. The durable
  owner now owns heartbeat, retrieval, repair, spend accounting, and release.
- Next: adopt `EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json` if emitted; otherwise
  respond only to the owner's hash-bound repair handshake without replaying a
  complete interpretable sample.

## 2026-07-27T01:12Z — retained pre-science index repair

- Evidence: attempt 0 failed before `science_started.json` and before either
  CUDA arm marker. The preserved traceback localized an envelope-validation
  broadcasting error: `[2048,5376]` extrema were compared directly with
  `[2048,128,5376]` blocks.
- Amendment: added the required singleton block-row dimension to both
  comparisons. Patched scorer SHA-256 is
  `9bb9b28cc7b25d30d7ee884685660005cae71fe552aa7938d7f53cb568d0235a`.
  Requested only `exact_block_bound_component_consumer_only` through repair
  generation 0; the same PID and original claim have entered attempt 1.
- Interpretation: attempt 0 is an invalid pre-science integration attempt, not
  a consumed scientific sample. No frozen producer or settled measurement was
  replayed.

## 2026-07-27T01:20Z — attempt 1 terminal recovered and mechanism closed

- Question: did the single exact block-bound vocabulary-head component sample
  satisfy the frozen exactness and timing contract?
- Action: under the original live claim, normalized readability only for the
  four existing attempt-1 terminal/marker files, retrieved and hash-validated
  them, adopted the canonical terminal, then stopped PID 2236177 (matching
  start ticks 123063995) and released the original claim at 01:20:18Z. No
  Docker, CUDA, scorer, capture, retrieval, or endpoint work was replayed.
- Evidence: the recovered terminal hash before adoption is
  `17ff0975f3d91cc1b1033ca0c418b18b8574ce4ea85ba3170497522e3cd82083`;
  its source identities, one CUDA submission, both arm markers, and all 1,536
  consumed rows validated. It reports `exact_top1_match=false`, 0.822194%
  pruned blocks, 99.177808% evaluated rows, 9.943840 ms candidate median, and
  0.860144 ms dense median. The continuous 595.873443-second claim cost is
  $0.407134204483 with no checkpoint transfer.
- Interpretation: this is a consumed, typed negative—not a retrieval or
  integration failure. The exact coordinate-hyperrectangle block-bound path
  is both non-identical and substantially slower than its measured dense
  comparator, so endpoint promotion is closed.
- Next: preserve the terminal and move the campaign to a materially distinct
  mechanism.
