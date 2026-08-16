# Research log

## 2026-07-17 — director admission

Activated read-only after the H100 owner reached SSH. It audits immutable local program semantics for later interpretation and cannot touch or delay the owner.

## 2026-07-17 — terminal immutable-byte audit

- Question: can the launched bytes support interpretation as an actual paged BF16-versus-FP8 KV experiment?
- Action: traced the immutable benchmark through the exact-image producer source and the staged owner/controller contracts without reading or touching live owner state or artifacts.
- Evidence: `kv_paged_actual.py` calls `unified_kv_cache_update` with an unregistered layer name, never calls the imported paged backend, and contains no page geometry, global row, FP8 arm, oracle, counters, sweep, aggregation, or direct-linear conditional. `h100_owner.py` supplies no conditional program. The shared lifecycle still provides a credible hashed retrieval and cleanup contract. Full findings and byte hashes are in `AUDIT.json`.
- Interpretation: `fail_quarantine_science`. A later terminal can establish lifecycle, exact harness failure, cost, and cleanup only; it cannot support any FP8 paged-KV mechanism or performance conclusion.
