# Research log

## 2026-07-29T17:26Z — admitted

Test one conservative low-rank residual certificate against the same exact
weights, hidden rows, stock sampler, and physical-union accounting that closed
the centroid/radius hierarchy. Stop before index implementation if the oracle
cannot avoid 10% of union weight bytes.

## 2026-07-29 — rank-32 query-span reference positive

- **Question:** Can one query-asymmetric low-rank residual certificate preserve the exact pinned greedy candidate set and reduce net physical output-head traffic on the same 32 rows?
- **Action:** Reused the exact tied BF16 tensor and 32 hidden rows through project-local hard links. Ran one numerical-spectrum/full-query-span oracle, then its only admitted rank-32 index. Charged float64 projected weights, basis, residual metadata, projected-score output, an unfused residual-bound read/write, survivor mask/IDs/logits, and the union of full BF16 rows read for exact verification. The consumed producer exposed a later persistence defect: its stock-error row norms were memory-only. Preserved that result, derived a conservative runtime norm from stored coefficients plus residual norms, and reran only the fresh-process persisted-index consumer.
- **Evidence:** The oracle gate passed with `99.971390%` gross exact-weight avoidance. The canonical persisted consumer retained the exact possible stock set and every dense winner; its physical union was `103/262144` rows and its feasible projected seed matched the dense-reference winner hash. Total declared traffic was `281,758,732` bytes versus `2,818,572,288` dense bytes, a `90.003495%` net avoidance. The index is `70,584,754` bytes; producer CPU time was `13.99 s`; provider/GPU spend was `$0`.
- **Interpretation:** Typed positive only for the same-row query-trained basis. The mechanism is physically distinct from the closed fixed-coordinate and cluster/radius bounds, but the near-zero query residual is in-sample. Promote to one disjoint-query CPU/reference gate, not directly to H200 or an endpoint.
