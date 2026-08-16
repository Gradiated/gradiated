# Research log

## 2026-07-17 — director delegation

Activated as independent `$0` evidence while the actual W4 owner runs. Produce a deterministic c8/c16/c32 queueing and all-in cost surface for the exact prompt-heavy mix, preserving the campaign's latency-for-cost trade and separating AA 10K single-stream. Return one conditional endpoint load geometry or a negative higher-batch result. Budgets are 45 wall minutes, 2 CPU-hours, 2 GiB storage, and `$0`.

## 2026-07-17 — deterministic queue sweep complete

Question: whether background pooling makes W4 c16/c32 economically usable, and which geometry should be measured later.

Action: ran `queue_bound.py` with seed `20260717`, 8,000 requests/case, gamma-renewal burst shapes (50/4/1.5), c8/c16/c32, seven windows, seven arrival multipliers, and nine explicit nonlinear overhead values. The first run exposed and corrected a finite-horizon stability-label bug; the corrected run was repeated from the same script and seed. Raw rows and inputs are in `QUEUE_BOUND.json`.

Evidence: c16 at moderate burst, 1.0835 req/s, 0.10–0.50 s pooling, and 0.20 s nonlinear full-batch overhead is stable with p50 14.7–16.1 s, p95 19.3–27.6 s, mean batch 10.4–10.9, and $0.000193–$0.000198/request at the $1.10 planning rate with all-in factors. At 1.379 req/s it becomes unstable (p95 273–371 s). c32 is cheaper in the optimistic model but requires ~29–31/32 batches and is unstable at 2.167 req/s under the same overhead; its separate 10K fit has just 0.613 GiB headroom and is allocator-sensitive.

Interpretation: c16 has the more credible conditional background region. Derived full-batch nonlinear ceilings against the $0.000614925 market target are c16 0.850 s/request planning and 0.318 s/request conservative; c32 1.103 s and 0.571 s. These are bounds, not measured endpoint performance. c8 has no positive conservative margin.

Next: if the live W4 owner later proves exact producer/revision/quality and actual consumer execution, measure paired c16/c32 at 1.08 req/s, 0.25 s pooling, moderate burstiness, primary 4214/358 mix, and 12.7% cache reads. Gate c32's 10K arm on measured allocator reserve; otherwise close the higher-batch branch.
