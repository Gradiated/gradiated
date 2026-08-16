# Research log

## 2026-07-26 — bounded latency-relaxed pooling discriminator

Question: can admission-controlled c32 batching and replica pooling close the
locked 20% all-in cost gap with the qualified `0.625149101968745 s/request`
service evidence unchanged?

Action: implemented and ran `run_latency_relaxed_pooling_screen.py`, a seeded
central-pool discrete-event simulation. It tests wait-to-fill c32 and 5/15/30/
60-second admission deadlines under Poisson and explicitly synthetic bursty
arrivals at the locked 90% offered load, plus a three-replica configuration
with two active replicas and one 60-second-loss reserve. Partial batches are
charged the full measured c32 wave duration, so no smaller-batch speed is
assumed. The qualified source digest was verified as
`b02d02c2283f5a018384cacf6522e123ce8e603ad0cfa2cd2c61ed6cb9eda363`.

Evidence: the executable terminal is
`LATENCY_RELAXED_POOLING_SCREEN.json` (`typed_none`). The decisive derived
bound is independent of the synthetic arrivals: the planning mapping's
`$0.109725/M` at 90% utilization has an ideal 100%-utilization GPU-only floor
of `$0.0987525/M`, above the `$0.08778/M` target. Reaching the target without
a service change requires 112.5% utilization; equivalently, service must fall
to at most `0.500119281574996 s/request` (20% faster). All-in/reliability
factors and loss reserve worsen that floor. In the synthetic sensitivity,
deadline policies do not meet their p95 queue-delay budgets and the loss-reserve
pool costs `$0.371974–$0.380532/M` all-in at the modeled offered load.

Interpretation / next move: scheduling can be retained as an executable
background policy shape, but is not an economic candidate. Do not promote a
GPU or provider experiment for pooling alone; require a measured physical
service-time gain first. Provider spend and contact were zero.
