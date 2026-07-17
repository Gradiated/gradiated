# Decision — W4 background queue bound

The deterministic CPU sweep supports a conditional c16 endpoint load geometry and does not justify promoting c32 as the primary branch.

- The sweep contains 3,969 fixed-seed gamma-renewal queue cases over c8/c16/c32, smooth/moderate/bursty arrivals, seven pooling windows, seven offered-rate multipliers, and nine nonlinear-overhead values. It uses 8,000 requests per case, corrected W4 phase floors, explicit cache-adjusted attention/KV/head/scheduler/sampling terms, and $1.00/$1.10/$1.25 per GPU-hour.
- At c16, moderate burstiness and 1.0835 requests/s (0.55× the optimistic phase-rate input), 0.10–0.50 s pooling remains stable at nonlinear overhead 0.20 s/request at full batch: p50 14.7–16.1 s, p95 19.3–27.6 s, mean batch 10.4–10.9, and planning all-in cost $0.000193–$0.000198/request. At 1.379 requests/s (0.70×), the same overhead is unstable with p95 273–371 s.
- c32 can produce lower modeled cost, but only by filling roughly 29–31 of 32 slots. At the same 0.20 s overhead it is already unstable at 2.167 requests/s; its 10K logical total is 44.091 GiB with 0.613 GiB headroom, explicitly allocator-sensitive. This is not enough evidence to spend a later endpoint arm on c32 alone.
- Full-batch nonlinear-overhead ceilings against the WandB $0.000614925/request market target are derived as 0.850 s/request for c16 under planning factors and 0.318 s/request under conservative factors; c32 allows 1.103 s and 0.571 s respectively. These are optimistic service-bound ceilings, not endpoint claims. c8 has no positive conservative margin.

Conditional endpoint geometry: after an exact-revision W4 producer/checkpoint and actual consumer/quality route pass, run paired c16 and c32 arms on the primary 4,214-in/358-out mix with 12.7% cache reads, moderate burstiness, 1.08 requests/s offered load, and a 0.25 s batch-formation window. Compare complete-request p50/p95, realized batch, throughput, memory, and all-in cost. Keep c32 conditional on allocator telemetry; do not run the 10K c32 arm unless measured free headroom exceeds the required runtime reserve.

This artifact is synthetic/derived queue evidence. It transfers no quality, kernel, or endpoint claim from the live owner.
