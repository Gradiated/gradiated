# Research log

## 2026-07-24 — director admission

Admitted one exact fixed-tree target-verification attention/dataflow
realization from the completed repaired c32 trace. The measured target is 900
resource-heavy `_fwd_kernel` launches totaling 1.488 seconds across 15
verification steps, not host bookkeeping or the consumed LM-head
materialization. Assigned the already-warm independent H200 under `$6`
cumulative authority and a `14:20Z` release deadline. No claim, guest command,
CUDA invocation, or provider mutation was performed by the director.

## 2026-07-24 — exact H200 component rejects BLOCK_M=16 semantics

Question: can the exact c32, 12-draft-token tree-verification call replace
the stock Hopper 64-row query tile with one 16-row tile, removing its 81.25%
inactive query rows while preserving the tree mask, page-1 E5M2 KV path, and
BF16 output?

Action: materialized the pinned runtime, NGRAM producer, tree-mask/paged-index
consumer, endpoint harness, and 62,578,655,208-byte checkpoint under this
project; froze `IMMUTABLE_PACKET.json`; and atomically claimed
`h200-ngram-critical-e00bwcwgsxawx1jmgw`. The retained detached owner ran one
alternating 25-sample exact component over an adversarial full-length tree mask
and randomized real page-1 indices for one sliding-window-1024 and one
full-attention layer. A pre-claim inventory list/dict adapter defect was
preserved and repaired before any claim, remote command, or CUDA invocation.

Evidence: the sliding control/candidate medians were `1.377088/0.584736 ms`
(`57.538%` reduction); full attention was `4.105184/1.747424 ms` (`57.434%`
reduction). The unchanged grid was `[32,32,1]`, launch count remained 60 per
verification step, and no new synchronization or compulsory KV bytes were
introduced. Full attention passed the `atol=rtol=0.005` oracle
(`max_abs=0.004883`), but the sliding row failed it
(`max_abs=0.010742`, `mean_abs=0.000181`, relative L2 `0.007245`) despite all
finite, consumed, nonzero outputs. The weighted component implies a positive
`36.03%` trace-window bound, but correctness gates performance. The conditional
counter capture and c32 endpoint pair were therefore not started. Exact
terminal: `artifacts/tree-verify-20260724t125045Z/FINAL_TERMINAL.json`.

Decision: reject this single `fixed_tree_block_m16` realization as a complete,
interpretable semantic mismatch; do not replay it. The owner released the warm,
unoccupied bench ready with the image, checkpoint snapshot, Triton cache, and
artifacts retained. Conservative claim exposure was `$0.117322`, within the
`$6` cumulative reservation.
