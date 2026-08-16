# Research log

## 2026-07-23 — director admission

Admitted one prefix-compatible local E5M2 block-paging hypothesis. The circular ring is closed and may not be repaired or replayed. Immediate evidence is one 16-token actual-producer/consumer component followed by at most one conditional exact c32 pair.

## 2026-07-23 — exact H200 component closes the fixed-page lane

- **Question:** Does one canonical radix-owned 16-token physical page improve the exact local E5M2 producer/consumer enough to admit the frozen c32 pair while retaining the 1,024-token window and ten page-one global paths?
- **Action:** Materialized the frozen component bytes locally, claimed `h200-sync-linear-e00vhh6h29fj68x91g` under one heartbeat owner, and ran the pinned SGLang `SWAKVPool.set_kv_buffer` producer against the page-one Triton control and a block-plus-in-page Triton consumer. The component exercised all 16 first/last offsets, shared-prefix refcounts, eviction/reuse, negative padded graph rows, and 50-local/10-global routing. No circular request state, prefix copy, page sweep, or c32 endpoint invocation occurred.
- **Measured evidence:** Candidate/control outputs were bit-identical (`max_abs_error=0`, `relative_l2=0`). The candidate consumer improved median latency by `13.3703487%` with an `11.7218318%` lower-95% reduction; the decode producer/consumer boundary improved by `11.0200545%` with a `9.5285096%` lower-95% reduction. The official prefill producer was neutral: `0.3211070%` median improvement but a `-0.4104971%` lower-95% bound. Candidate compilation used 168 registers, two spills, and 25,728 bytes shared memory. The all-negative padded block row produced nonfinite output, so the CUDA-graph padding semantic gate failed. Exact E5M2 materialization, page refcount/eviction/reuse, partial-page coverage, and untouched global page-one state passed.
- **Interpretation:** Physical block locality is real in the decode consumer and survives the actual decode producer boundary, but it is insufficient under the frozen whole-component bound and the candidate is not graph-safe for padded rows. The padding failure is a preregistered semantic stop after candidate execution, not a pre-invocation integration defect; the arm is consumed and must not be repaired or replayed.
- **Decision / next:** Close the lane and skip the conditional c32 pair. Cumulative provider exposure is `$0.03155062191486358`; the bench was released healthy and available. Canonical artifacts are `artifacts/FINAL_TERMINAL.json` and `artifacts/remote-component/artifacts__component__COMPONENT_TERMINAL.json`.
