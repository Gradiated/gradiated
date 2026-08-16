# Full-47 rank-448 c40 capacity co-design rebase

## Question

Does reducing only full-47 MLA KV rank from 512 to 448 create a tile- and loader-coherent c40 operating point whose conservative exact-workload path clears `606.355` output tok/s on L40S?

## Why this matters

The old rank screen used a synthetic c32 memory projection and a c16-based endpoint transfer. Fresh unchanged-stock measurement instead shows c32 fits and reaches `596.851973` tok/s. Its startup KV pool contains `333,488` tokens at `54,144` BF16 KV bytes/token across 47 layers. Rank 448 reduces that state to `48,128` bytes/token; holding the measured KV-byte budget gives roughly 375K tokens, while exact c40 demand is `368,640`. This interaction may unlock a new background operating point rather than merely save memory at c32.

## Scope

Work offline at `$0` for at most 1,200 seconds, 8 GiB RSS, and 32 MiB of new artifacts. Keep the existing `full47_mla_rank_robust_falsifier` terminal; this is a new rank-plus-concurrency discontinuity question.

Independently verify exact rank-448 tensor rewrite shapes/bytes for KV-A/KV-B and all config/index references, the pinned loader consumption path, group-32 representation compatibility, and SM89 grouped-MLA tile/shared-memory implications. Recompute the measured KV-byte pool, block rounding, c40 request demand, mandatory reserve, graph/runtime allocations, and whether maxseq40 can preserve a safe startup envelope. Use the measured stock c16/c32 frontier to build a conservative saturation interval for c40; do not treat a curve fit as endpoint evidence or add unmeasured MLA speed credit.

Return `NOMINATE_RANK448_C40_PROXY` only if representation/loader closure, conservative capacity with explicit reserve, hardware legality, and a conservative endpoint lower bound all reach `606.355` tok/s. State exactly one later target-GPU proxy, but do not materialize a checkpoint or prepare a launch. Otherwise return `RANK448_C40_CLOSE` with the binding capacity, representation, tile, or endpoint reason.

Do not use provider/network/CUDA resources, write checkpoint payloads, edit shared runtime/controller code, train, evaluate quality, open other ranks/concurrencies, or resurrect the old rank project. Produce one compact decision artifact and a concise research-log update.

## Fixed evidence

- Stock archive and project: `../full47_stock_maxseq32_cuda_endpoint/`, archive SHA-256 `ff873b597b33775787eada26ded437d1da91f326a47a8beb3ab8c994cc27cb4c`.
- Exact checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Prior rank/tile evidence: `../full47_mla_rank_robust_falsifier/`, `../l40s_model_chip_codesign/`, and `hardware/L40S.md`.
- Campaign workload/gates: cache-off 8,192/1,024, 300-second background envelope, `594.466/606.355` tok/s at `$1.10/L40S-hour`.
