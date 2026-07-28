# Research log

## 2026-07-18 — delegate one geometry-informed Triton split candidate

Question: does reducing flash-decode KV splits from 8 to 4 improve canonical c32 service by cutting partial-result reduction overhead in Gemma 4's 50 local-window layers without underfilling H200?

Contract: reuse the released H200 and resident exact checkpoint/image. Restore the canonical retained endpoint, change only the Triton KV split count, run the frozen exact-mix consumer once after an idle HTTP-200 flush boundary, require exact output/cache accounting, retrieve a typed terminal, and release without teardown. This is one candidate, not a split or tile-size sweep.

## 2026-07-18 — pre-invocation identity boundary

Action: claimed `h200-attention-endpoint-e00vbbb709tzxscaan`, stopped only `gemma-mixed-chunk-c32`, and started the bounded split-4 owner. Its immutable gate observed `exact_mix_runner.py` SHA-256 `235f5de7a5ae66aa9732742c2fef65e49fe13bffcfae5299823c5c1e9837622d`, not the admitted `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.

Evidence: [typed terminal](artifacts/triton-kv-split4-c32-20260718t2018z/TERMINAL.json), local input hash, and owner journal. The exact runner was invoked zero times; no request rows, cache flush, or timing evidence exists. The split-4 container was left resident and the bench is released without teardown. Conservative claim-to-release exposure is `$0.17`, below the `$1.30` reservation.

Interpretation and next move: this is not a performance result. The director must supply the immutable admitted runner bytes or revise the source identity before a new execution contract can be admitted; this project may not patch or substitute the runner.

## 2026-07-18 — one consumer-only identity repair admitted

Director reconciliation: the canonical source path now hashes to the required `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`, the first owner's retained `local-input-sha256.txt` records the same bytes, and the earlier fused endpoint independently consumed that identity. The journal's transient `235f5de7...` value therefore reflects a shared-path mutation race before transfer, not missing canonical bytes.

The intended split-4 server is already healthy and zero candidate requests or cache flushes have occurred. Admit one same-project execution repair: take an immutable project-local snapshot only if its hash is canonical, transfer and verify that snapshot, then perform the original idle/flush/single-consumer/retrieval contract without restarting the server. A second mismatch or any server/request failure closes the line.

## 2026-07-18 — split-4 exact consumer terminal negative

Action: snapshotted the restored canonical runner (`143709fd...184d7`) before the claim, verified the same hash after the sole remote workspace overwrite, and reused the resident server without restart. The preflight recorded HTTP health, image/checkpoint/container arguments, split count 4, both Triton phases, frozen runtime flags, and zero running/queued requests. The first candidate cache flush returned HTTP 200, then the frozen runner executed exactly once.

Evidence: all 32 rows are finite and nonempty with exact `4214/358` usage; cache accounting is exactly `17,120` cached and `117,728` fresh. Service time was `0.934844753 s/request`, versus `0.919457394 s/request` for the frozen comparator: `-1.6735%` reduction (a regression). See [terminal](artifacts/triton-kv-split4-c32-repair-20260718t2026z/TERMINAL.json).

Interpretation: the hypothesized reduction in local-layer split/reduction overhead did not offset lost parallelism at this c32 endpoint geometry. Close the split-4 line without retention or a split/tile/scheduler follow-up. The healthy server remains resident; cumulative conservative exposure is `$0.26` under the `$1.30` cap.
