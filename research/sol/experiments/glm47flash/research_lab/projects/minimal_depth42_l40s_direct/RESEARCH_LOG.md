# Research log

Opened after the zero-cost co-design screen materialized the 42-layer five-block proxy. The next result must be the exact L40S c16/c24/c32 cost measurement or a typed terminal with cleanup, not another readiness-only artifact.

## 2026-07-16 — terminal integrity rejection before provider creation

Action: extended the shared local and remote derived-AWQ allowlists with the exact student42 manifest/config/index/weight identities, then ran the narrow validator tests and the execution-equivalent full local-manifest check without modifying the candidate.

Evidence: the map cross-rejects student39, student42, and one-field drift; its post-edit source hashes are `6600bd8a...` (local) and `49f340c8...` (remote). The candidate's admitted manifest and checksum-list hashes are present, and all four 16,658,558,680-byte weight shards match. However, `minimal_depth_checkpoint_manifest.json` is 4,232 bytes but hashes to `cb075aad...`, whereas both embedded contracts require `42940771...`; the full validation therefore fails with 12/13 rows matching. `IDENTITY_PREFLIGHT.json` preserves the exact mismatch.

Interpretation: this is a typed pre-GPU checkpoint-integrity failure, not an L40S load/OOM/performance result. The required no-mutation rule prohibits repairing or re-manifesting it in place, and provider mutation/exposure remained zero. The candidate is terminal under the stated no-successor rule.
