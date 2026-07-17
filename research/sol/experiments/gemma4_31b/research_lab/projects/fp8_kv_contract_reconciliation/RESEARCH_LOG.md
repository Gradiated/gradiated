# Research log

## 2026-07-17 — director delegation

Delegated after the live owner reached CUDA, passed the primary linear gate by control flow, then OOMed in a monolithic all-layer KV tensor before buffered results were persisted. Resolve the 0.363423/0.558736 GiB contract disagreement and prepare a bounded per-layer/tiled corrected arm for the same paid project. This project is `$0`, may not touch or wait for the live owner, and cannot make a CUDA or endpoint claim.

## 2026-07-17 — source-bound byte reconciliation and corrected arm

Question: is the 0.363423 GiB or 0.558736 GiB FP8-per-token-head primary KV figure compatible with the pinned value/scale contract, and what geometry avoids the observed component-harness OOM?

Action and evidence: recomputed the pinned contract using the exact 50 local / 10 global geometry and content-bound source excerpt. One E4M3 byte per K/V scalar plus one FP32 scale for each K and V token-head produces 4,224 local and 4,128 global bytes per token/layer. `KV_CONTRACT.json` (SHA-256 `d495553dab98eac4d101802e668469fea3758ba378a8bd89641075a277a07802`) proves 0.363423228 GiB at 4,214 tokens, 0.377186537 GiB at 4,572, and 0.585865974 GiB at 10K. The earlier 0.558735728 GiB formula retained the 8,192-byte BF16 local payload rather than converting its 4,096 scalars to FP8 bytes; its global term and inline-scale allowance were otherwise correct. The retrieved live stderr confirms that the component harness instead allocated `33712 x 450560` BF16 scalars (28.292 GiB) before its `abs()` reduction, an all-layer transient unrelated to cache residency.

Interpretation: c8 prompt/peak derived totals are now 42.257386/42.367492 GiB under the inherited 39.350 GiB non-KV allowance, rather than 43.820/43.930 GiB. This removes the byte disagreement but remains a logical payload bound: block rounding, allocator behavior, framework workspace, vLLM consumer compatibility, numerical behavior, quality, and throughput are unmeasured.

Next move: after the exclusive owner is terminally reconciled, its one permitted in-place correction should first atomically persist primary rows, then use `CORRECTED_ARM.md` (SHA-256 `ef9c8710d005e94078ccba63cee3c7d3b250b4a5bae1f4f8c7f2a8ae424022fe`) for sequential per-layer 128-token local/global cache-write/readback tiles. No provider mutation, polling, or live-owner edit occurred here.
