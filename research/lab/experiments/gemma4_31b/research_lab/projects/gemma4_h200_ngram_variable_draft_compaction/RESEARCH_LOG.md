# Research log

## 2026-07-24 — director admission

Opened one producer-to-consumer variable-draft compaction experiment after the
M16 and M32 attention-tile realizations produced the same sliding numerical
miss. The new mechanism retains stock M64 arithmetic and instead removes
officially proven padded tree nodes before target forward. Assigned the warm
verifier H200 under `$10` authority. No claim, guest command, CUDA call, or
provider mutation was performed by the director.

## 2026-07-24 — variable compaction terminal

Question: can one request-major variable representation remove official padded
NGRAM nodes while preserving exact target logits, KV ownership, acceptance,
and served output?

Action: traced the official `ngram::fillResult` contract and exported the token
count after BFS but before zero padding; token ID zero cannot prove padding.
Frozen and ran one packet that compacts draft tokens, positions, masks,
`qo_indptr`, KV slots, and target rows, then remaps logits and accepted KV
locations to the fixed consumer. Two pre-request CUDA-graph dummy defects were
preserved as invalid attempts and repaired under the same claim. The completed
control c1/c4/mixed producer stages were retained exactly once during the
second repair.

Measured evidence: coverage included valid lengths `{1,2,3,4,6,8,12}` and
mixed batches. Across 231 request-events, the candidate removed 332 of 2,772
target/KV allocations (11.98%) while retaining exactly 2,101 accepted KV
slots, equal to control. Request-local c1 and all four staggered mixed
consumers were exact. In the simultaneous c4 row, however, only one of four
requests had exact target top-2 logits and acceptance; two served response
texts diverged, with the first mismatch at the initial all-one target
verification despite identical request hashes. This localizes the failure to
multi-request compact row ownership/attention mapping rather than the
official validity premise.

Performance was also negative on the intended reduced shapes: the sum of
matched per-shape target-forward medians increased from `393.866 ms` to
`604.399 ms` (+53.45%). Full-width `[12]` and `[12,12,12,12]` shapes were
faster (1.277x and 1.268x), but they do not validate the compact path.

Decision: reject this realization and keep the preregistered c32 gate closed.
The bench was released ready at `13:59:43Z`. Measured cumulative provider
exposure was `$0.6104805944`, within the `$10` reservation. The raw aggregate
terminal's empty `return_token_ids` comparison was non-informative; the
request-ID-aligned exact stream and target consumer correction is preserved in
`CAUSAL_TERMINAL.json`.
