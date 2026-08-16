# Research log

Opened by the 2026-07-16 user performance-discovery pivot. Preserve 47 layers and search for the smallest exact-tensor intervention that turns the 807.7 MiB stock c32 deficit into robust L40S admission with a credible throughput path. Training and full quality are intentionally deferred.

## 2026-07-16 — five-block physical-depth proxy closes the zero-cost screen

**Question.** Among the closed rank/residual bounds and the smallest physical-depth fallback, is there one exact, executable candidate that clears robust c32 capacity and the conservative 594.466 output tok/s gate?

**Action.** Consumed the fixed rank/MLA and residual-W4 artifacts, then compared rank-384, rank-448 plus head/shared residual W4, and the prior five-block `even_5` depth pattern. Materialized exactly one content-addressed proxy by reusing the proven student39 byte-preserving shard writer against `/root/.cache/glm47flash-awq-ab31d120`; skipped source layers `[6,15,24,33,42]`, renumbered the 42 retained serving layers, disabled MTP, and preserved all other tensor payloads and tokenizer files. Reran the materializer to verify idempotent content-addressed reuse.

**Evidence.** `CANDIDATE_COMPARISON.json` records the exact comparison. Rank-384 projects 1,273 MiB c32 headroom and fails the 1,536-MiB rule. Rank-448 plus head/shared residual W4 projects 3,085.667 MiB, but its mixed checkpoint/dispatch route and endpoint are unproven; the residual artifact is explicitly synthetic and not a loader or wall-time result. The five-block proxy removes 1,855,640,720 AWQ bytes and 1.40625 GiB c32 MLA state, projecting 43,666.023 MiB and 2,401.977 MiB headroom. Its inherited conservative work bound is 597.529 tok/s and `$0.511365/M`, only 0.515% above the 594.466 tok/s gate.

The proxy root is `/root/.cache/glm47flash-awq-minimal-depth-4c84badbce22` with contract `4c84badbce2290a95ebc83bbceb784fce28507e15038fc6a60105ed5350697cf`; it contains 24,615 exact keys, 16,658,558,680 shard bytes, layer IDs `0..41`, and no layer-47/MTP keys. The pinned `glm-vllm:0.15.0-transformers-1618d44` source probe passes the exact architecture registry, `AutoWeightsLoader`, and compressed-tensors W4A16 route (`minimal_depth_runtime_preflight.json`). Actual model instantiation and consumed/missing/unexpected loader sets remain **UNMEASURED_NO_MODEL_INSTANTIATION** because the zero-cost environment has no CUDA GPU; no provider mutation or spend occurred.

**Decision.** The five-block physical-depth proxy is the sole zero-cost winner and is the smallest screened candidate with robust headroom and a conservative economic path. Do **not** nominate a later L40S arm: the throughput number is a derived bound, not a measured endpoint, and the project requires a real GPU loader/kernel result before nomination. Close this project at `$0`; reopen only with an authorized GPU slot or if the measured 39-layer lineage fails for a mechanism-specific reason.
