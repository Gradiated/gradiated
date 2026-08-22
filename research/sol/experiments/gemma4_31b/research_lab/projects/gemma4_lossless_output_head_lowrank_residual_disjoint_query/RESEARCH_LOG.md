# Research log

## 2026-07-29T18:40Z — preregistered disjoint-query discriminator

- **Question:** Does the predecessor's frozen rank-32 output-head residual index preserve the complete stock candidate set and reduce fully charged physical traffic on 32 hidden rows excluded from fitting and prior evaluation?
- **Action:** Bound the predecessor terminal once and froze its persisted index, exact capture, and tied BF16 weight identities. Before observing logits or survivor results, fixed the held-out selection to the second capture-order row for each request; the predecessor fit/evaluation selection was the first row for each request.
- **Contract:** One deterministic CPU/reference invocation, `$0` provider/GPU spend, deadline `2026-07-29T19:24:47Z`, exact-stock-set containment plus positive fully charged net physical traffic required for promotion. No tuning or replay after observing the held-out result.

## 2026-07-29T18:45Z — frozen rank-32 transfer falsified

- **Action:** Ran the sole preregistered CPU/reference consumer against the frozen 32-rank index and exact tied BF16 weights. Recomputed the dense stock numeric envelope and candidate survivor set, then charged the full 32-query physical union, fixed index, basis, metadata, score/bound buffers, survivor materialization, exact weights, and exact logits.
- **Evidence:** The held-out provenance set is disjoint from the predecessor fit/evaluation set by storage index, global row, ownership tuple, and BF16 row hash. Complete stock candidate-set containment and exact dense-winner recovery both passed. However, maximum query residual grew from the predecessor's in-sample `~7.94e-10` to `226.371573`; the survivor union was `262143/262144` rows. Candidate traffic was `3,199,874,176` bytes versus `2,818,572,288` dense bytes, or `-13.528193%` bytes avoided.
- **Interpretation:** This is a typed transfer negative, not an integration failure. The basis memorized the prior query span closely enough for in-sample pruning but does not provide a selective conservative certificate on the preregistered adjacent hidden rows. Close the frozen rank-32 representation; do not promote it to H200 or tune it after holdout.
- **Resources:** `67.77 s` CPU/reference, zero GPU/provider/API calls, `$0` spend. Raw result: `artifacts/disjoint_query_result.json`.
