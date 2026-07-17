# Research log

## 2026-07-16 — Director opening handoff

- The live depth42 project owns provider mutation and is already measuring c16/c32; this project must not inspect or affect it.
- New question: use fixed historical memory evidence to decide whether c40 or c48 is a robust background-cost successor, with an explicit trigger keyed to the future c32 endpoint.
- Stop at `$0` with one memory close, saturation close, or single conditional frontier. Fitting alone is not nomination evidence.

## 2026-07-16 — MEMORY_CLOSE at c40 from exact 8K KV reservation

**Question/action.** Reconstructed the depth42 c32 capacity projection under the fixed checksum-closed identity, pinned 8,192/1,024 cache-off geometry, BF16 KV, and `num_kv_splits=4`; projected c40/c48/c64 offline. The live owner was not inspected or used.

**Evidence.** The 42-layer geometry reserves `48,384` KV bytes/token, hence `396,361,728` bytes = `378 MiB` per full 8K sequence (512 16-token blocks). Starting with the fixed c32 projection of `43,666.023 MiB`, c40 adds eight such reservations = `3,024 MiB`, reaching `46,690.023 MiB`: already `622.023 MiB` above the `46,068-MiB` device envelope. c48 and c64 project to `49,714.023` and `55,762.023 MiB`. The `1,536-MiB` robust-admission limit is `44,532 MiB`, so even a hypothetical c40 fit would be inadmissible. The reconstructed c32 residual fixed term is `31,570.023 MiB`; it deliberately groups model/runtime, graph/capture, scheduler, allocator, and observed fragmentation because the fixed artifacts do not support splitting them further. The compact result is `DEPTH42_BACKGROUND_FRONTIER.json`.

**Decision.** `MEMORY_CLOSE`. No c40/c48/c64 arm survives, so no future-c32 throughput, marginal-efficiency, or 300-second trigger can make a later arm informative. Student39 c16/c24/c32 scaling is recorded only as non-transferable sensitivity. This is architecture-cost evidence; quality remains mandatory.
