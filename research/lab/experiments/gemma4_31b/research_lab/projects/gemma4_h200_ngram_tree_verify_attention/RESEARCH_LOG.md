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

## 2026-07-24 — director admits one BLOCK_M=32 numerical repair

The M16 result closes that realization but leaves a high-value, localized
numerical question: both layer types were about 57.5% faster, full attention
passed, and only the sliding row missed the fixed oracle. Reactivated this same
project as priority 6796 `execution` under `$4` cumulative authority for
exactly one M32/N64 packet. It must rerun the unchanged exact component and may
run one fresh matched c32 pair only if every row is correct and the component
remains positive. No alternate tile, tolerance relaxation, quality replay, or
provider mutation is authorized.

## 2026-07-24 — M32 numerical repair closes with the same sliding-oracle miss

Question: does the one admitted `BLOCK_M=32`, `BLOCK_N=64` repair preserve the
unchanged exact tree-mask/paged-FP8 component while retaining the predicted
attention reduction?

Action: froze a new immutable M32 packet with the producer, consumer, masks,
positions, page-1 indices, FP8 E5M2 KV, BF16 query/output, launch grid, and
`BLOCK_N=64` unchanged. The first detached owner had an ordinary stale-terminal
defect: it observed the prior M16 terminal before entering CUDA and released;
that invalid attempt is preserved under
`artifacts/tree-verify-20260724t130710Z/repair/`. The same claimed H200 was
reclaimed, the stale terminal moved aside, and the unchanged M32 component was
run once.

Measured evidence: candidate hash
`fa8d7939b4bd26b86a8a30ff24c0986e2ad054773eefdda87b9b27d734e23531`; both rows
completed with 60 launches/layer and grid `[32,32,1]`. The M32 sliding row
reduced control latency by `44.313%` and full attention by `47.953%`; weighted
attention reduction was `45.671%`, giving a positive `28.616%` whole-request
bound. Sliding nevertheless failed the fixed `atol=rtol=0.005` oracle at
`max_abs=0.010742`; full passed at `0.004883`. All outputs were finite.
Counters and the c32 endpoint pair were correctly not started because the
component correctness gate failed.

Decision: close `fixed_tree_block_m32` as a valid semantic reject. Do not replay
M16/M32 or admit another tile in this project; retain the warm image,
checkpoint, and Triton cache. Conservative cumulative project exposure is
recorded as `$0.20`, including the failed owner attempt and repair claim.
