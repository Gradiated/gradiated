# Research log

## 2026-07-19 — director admission after spend-authority expansion

The durable spend cap increased from `$100` to `$200`, reopening the terminal portfolio with `$100.05` available. Activate one checkpoint-free deep H200 discriminator for the previously nominated local-KV-head 16→8 intervention. It must conservatively save at least `0.0181651588906249` seconds/request across the 50 sliding layers before any GQA checkpoint conversion, endpoint, or quality work. Reserve `$6.00`; researchers may claim/release the director bench but may not create or destroy provider resources.

## 2026-07-19 — exact-shape H200 discriminator passes

Question: does 16→8 local KV heads clear the preregistered fused-QKV plus page-1 FP8 paged-KV gate before any checkpoint or quality spend?

Action: re-hashed and project-locally snapshotted the admitted co-design/comparator bytes, claimed the director H200, inspected and bound pinned grouped-GQA source `1040f43a…`, and ran one randomized 80-pair exact `[32,5376,16384]` versus `[32,5376,12288]` program at 32 query heads, dimension 256, context 1,024, page size 1. Two FP8 write-adapter errors occurred before `SCIENTIFIC_STARTED`; the retained trace proves no candidate invocation. The repaired owner staged executed benchmark `24dd8351…`, retrieved the terminal atomically, and released the warm image/caches ready without checkpoint or server.

Evidence: `artifacts/local-kv8-discriminator-20260719t1244z/component/TERMINAL.json` (`1a3e4d5d…`) passes at `0.0321317027 s/request` conservative saving versus `0.0181651589` required (1.77×; 8.84% of the measured endpoint anchor and a derived 3.49% of the later exact-mix reference). Baseline/candidate total medians were `0.267936/0.194704 ms` per batched layer-step. Median paired savings split into QKV `0.006720 ms`, KV write `0.000240 ms`, and grouped paged attention `0.065936 ms`. Both outputs were finite and nontrivial; live and peak allocation deltas were zero; native FP8 cache bytes halved from 268,435,456 to 134,217,728 with no repeated cache. Torch profiler captured the actual `nvjet_sm90` QKV kernels, grouped Triton attention stages, BF16→FP8 copies, and FP8 index-put writes. `RECONCILIATION.json` corrects one raw descriptive identity label without changing evidence.

Interpretation and next move: measured attention time fell 33.92% and dominates the win, while QKV fell only 11.51% for a 25% output-width reduction, consistent with the 128→96 block SM-wave underfill risk. Promote only to director-authorized checkpoint conversion plus retrieval/coherence gates; this semantics-changing component result is not a quality or endpoint claim. Conservative full bench exposure was 1,498.787 seconds at `$2.46/hour`, or `$1.02417` before separately unmetered disk pennies, within the `$6` reservation.
