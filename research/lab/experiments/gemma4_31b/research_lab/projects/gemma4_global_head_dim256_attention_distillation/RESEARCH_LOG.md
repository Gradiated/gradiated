# Research log

## 2026-07-18 — director start

The head-256 endpoint retains measured `9.13858%` service-time headroom, but exact restoration of the original 128-coordinate rotary subspace left the same 0/3 repetitive coherence failure. This closes untrained slicing and opens one bounded modest-post-training falsifier: use the immutable 24/8 split of the 32 frozen workload prompts, supervise only the 50 compressed tensors against original-model full-attention outputs, and require held-out block improvement plus 3/3 coherence before any exact endpoint invocation. No second schedule or width/coordinate sweep is authorized.

The director started and verified replacement watchdog `gemma-head256-distill-h200-202607182305z-watchdog.service` (PID `2650329`) through `00:40Z`, atomically updated the shared pool, then stopped and verified the prior watchdog inactive. Maximum incremental exposure beyond `23:45Z` is `$2.255`; instance, disk, checkpoint, and image are unchanged.

## 2026-07-18 — single frozen distillation candidate terminal

**Question.** Can one 24-prompt pass over only the 50 compressed full-attention tensors recover enough of the teacher's block behavior to restore basic coherence?

**Action.** Materialized all 32 canonical request bodies project-locally; every body hash matched frozen `WORKLOAD.json`, and the copied request records reproduced aggregate digest `e73a44…01aa`. Froze contract `d18dbe…a4e`, captured original BF16 attention inputs plus eight sampled outputs at all ten global layers for the immutable 24/8 split, and trained one AdamW pass (24 updates/layer) from the RoPE-preserving slice. Two pre-forward wiring defects (deadline epoch and optional `accelerate`) were repaired without changing the scientific contract. A post-result tar exclusion defect was repaired by retrieving the overlay separately; no model call was repeated.

**Measured evidence.** The 32-request, ten-layer capture was 14,595,651,232 bytes and completed in 61.59 seconds. The 50-tensor overlay is 1,871,724,560 bytes, SHA-256 `2a534e2733ee04cf65555544d4d85f86124b3c76bf294d2bb5a2173b3464f656`. On the eight held-out prompts, aggregate NRMSE improved `0.635181 -> 0.490201` and cosine improved `0.825799 -> 0.907926`; every layer improved both metrics. In the exact patched SGLang consumer, all three coherence rules failed with the prior repetitive `la/L/de` pattern. Exact c32 invocation count is zero. Checkpoint metadata matched before/after. Derived claim exposure was 1,137.887 seconds, `$0.777556` at `$2.46/hour`.

**Interpretation and next move.** The teacher-target instrument and modest layerwise pass can improve its sampled block objective, but that improvement does not recover end-to-end language behavior. This falsifies the admitted modest-post-training recovery line under its one-schedule rule. Close it; do not run c32, another schedule, or GPQA/TauBench. The healthy distilled server, image, checkpoint, caches, and retrieved overlay remain available for director disposition. Terminal: `artifacts/head256-distill-20260718t2311z-r1/head256-distill-20260718t2311z-r1/OWNER_TERMINAL.json`.
