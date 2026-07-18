# H100 actual paged FP8-KV live-program audit

## Decision question

Can the immutable local bytes launched by `h100_actual_paged_fp8_kv_component_falsifier` support the claimed exact-image actual paged producer/backend sentinel and later interpretation?

This is a `$0` read-only audit concurrent with the durable owner. It must not poll, edit, wait for, signal, restart, or mutate the owner/project/service/provider. It cannot authorize spend, repair, retention, or a successor. Its only output is an interpretation verdict for later reconciliation.

## Scope

Read the paid brief, selection/mechanism, director assertion, behavioral pre-create artifact, `kv_paged_actual.py`, `remote_stage.sh`, owner/launcher, and any immutable staged manifests available locally. Check behaviorally—not by token inventory—that:

- the first remote CUDA atom invokes installed `unified_kv_cache_update` and then an actual selected paged backend, not only an import/source probe or dense/direct stand-in;
- local/global c8 geometry, block table, slot mapping, sequence lengths, cache shapes/dtypes/scales, and output oracle are valid for the actual installed signatures;
- BF16/FP8 arms are matched and timing excludes allocation/setup;
- named counters measure the same NVTX interval and missing counter support fails closed;
- sentinel retrieval occurs before any conditional rows;
- continuation thresholds, aggregation, setup-dominance trigger, direct-linear arm, transitive hashes, exposure/accounting, watchdog, and cleanup match the brief.

Return `pass_interpret`, `fail_quarantine_science`, or `limited_interpretation` with exact findings and hashes. Do not propose a repair in the live project.

## Budgets

- Wall clock: 15 minutes.
- Compute: 1 local CPU-hour; no GPU.
- Storage: 256 MiB retained plus 128 MiB temporary.
- Spend: `$0`; no provider or external mutation.

Write `AUDIT.json`, update log/status, terminalize.
