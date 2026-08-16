# Research log

## 2026-07-16 — Cycle 103 execution: pair difference close

At `$0`, read all exact layer-24 gate-projection `(i,i+32)` pairs from the pinned checkpoint, dequantized compressed-tensors signed-INT4 W4 with BF16 group-32 scales, selected the maximum Frobenius-distance pair, and computed its rank-256 SVD tail. Artifact: [`LAYER24_GATE_PAIR_CERTIFICATE.json`](artifacts/LAYER24_GATE_PAIR_CERTIFICATE.json).

Pair `(14,46)` was selected: distance `121.26808`, norms `90.25561` and `83.57005`. The rank-256 tail is `90.25964` against tolerance `17.38257`, margin `+72.87708`, ratio `5.19254x`. Decision: `PAIR_DIFFERENCE_CLOSE`. Because two rank-128 deltas differ by rank at most 256 and the common trunk cancels, this necessary-condition violation closes the global rank-128 route. Weight-space evidence only; no quality, runtime, routing, or provider claim.

Opened from the 2026-07-16 user-directed architecture/kernel pivot. Use the actual expert tensors and hardware geometry.

## 2026-07-16 — Director decomposition screen

Keep this independent from the exact-weight persistent executor. At `$0`, screen real gate/up/down expert tensors on five spread layers, ranks 64/128/256, with one global trunk primary and 4/8 clusters diagnostic. Charge multi-cluster execution for as many as four trunks/token absent router traces. A survivor must simultaneously retain at least 99% weight energy, save `2,343.7 MiB`, and support at least a `1.397x` fused-MoE component path; otherwise close without training, GPU work, or a provider endpoint.

## 2026-07-16 — Cycle 102 fail-fast layer-24 screen

The line is queued, not stuck, but a full sweep is unnecessary. Start with analytical payload/work gates and a deterministic expert-pair rank-tail certificate: if the best rank-256 residual difference already violates the 0.10 per-expert bound, global rank-128 is impossible and the project closes. Only a survivor proceeds to fixed-seed layer-24 rank-128 fitting and the exact SwiGLU/down fixture, then conditionally to four more layers and rank 64. Rank 256 is payload-inadmissible; clustered routes remain diagnostic and cannot nominate without router traces.

## 2026-07-16 — Cycle 103 certificate only

Narrow the turn to one necessary-condition proof. Deterministically choose the most separated `(i,i+32)` layer-24 gate pair, hash and dequantize its exact W4 tensors, and compute the best-rank-256 difference tail. A tail above `0.1 * (||We||F + ||Wf||F)` closes global rank-128 because the shared trunk cancels and two rank-128 deltas differ by rank at most 256. A pass means only `PAIR_SCREEN_SURVIVES`; do not begin the 64-expert, three-matrix factorization without a new admission.
