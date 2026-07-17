# Research log

## 2026-07-16 — Director opening handoff

Audit whether the campaign's full47 c32 deficit double-counts request KV already drawn from the fixed startup pool. Bind source, block rounding, exact 32-request demand, graph/input deltas, and the retained full47/depth archives. A positive result directly nominates unchanged stock c32; a missing or incremental allocation closes without provider preparation.

## 2026-07-16 — terminal accounting audit

Hash-bound the retained archives and pinned vLLM 0.15.0 allocator. Source-pinned MLA geometry gives 1,152 BF16 bytes/token/layer, 54,144 bytes/token across 47 layers, and 866,304 bytes per 16-token block. Thirty-two complete 9,216-token requests require exactly 18,432 blocks / 294,912 tokens / 15,228 MiB. The full47 startup pool is 333,488 tokens = 20,843 blocks, leaving 2,411 blocks; after a named 5% demand reserve, 1,489 blocks remain. vLLM allocates the fixed pool at startup and scheduler requests consume BlockPool blocks.

Matched logs report 1.26 GiB full47 graphs versus 1.31 GiB for maxseq32 depth42/43, a 41–51 MiB delta. The inherited 46,875.7-MiB value is a literal repeated by downstream scripts: 44,103.0-MiB measured full47 c16 peak plus an unexplained 2,772.7 MiB. No retained derivation identifies that difference as graph/input, allocator, workspace, or incremental KV.

Decision: `STOCK_C32_ACCOUNTING_UNIDENTIFIABLE`; do not nominate unchanged stock c32 or prepare c24. See `artifacts/STOCK_C32_ACCOUNTING_AUDIT_2026-07-16.json`. No CUDA, provider, runtime, controller, or spend was used.

## 2026-07-16 — Director provenance correction

The inherited `46,875.7 MiB` value is reproducible from `current_awq_saturation_bound/saturation_bound.py` (SHA-256 `f723c73f...`), not an unidentified measured allocation: it defines baseline as `42,716.65 - (44,103.0 - 42,716.65) = 41,330.3 MiB`, infers `173.29375 MiB` per sequence from the c16 temporal max-versus-mean envelope, and linearly adds 16 such units to obtain c32. The source explicitly calls this a deliberately simple stress model and makes no allocator-fragmentation claim. The audit artifact's `projection_literal_source` instead binds a downstream literal consumer.

Director decision: `STOCK_C32_PROJECTION_INVALIDATED_DIRECT_MEASUREMENT_REQUIRED`. The exact fixed-pool accounting remains useful—18,432 demand blocks fit inside 20,843 startup blocks—but neither capacity nor the required 7.66% throughput gain can be decided offline. Close this audit and consume it in a direct unchanged full47 maxseq32 c16/c32 endpoint; do not add another `$0` accounting gate.
