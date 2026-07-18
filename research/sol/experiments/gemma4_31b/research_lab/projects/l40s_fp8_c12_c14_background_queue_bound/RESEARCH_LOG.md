# Research log

## 2026-07-17 — director admission

Activated while the actual component owner runs. It tests whether the c12/c14 cost geometry is compatible with usable background completion times rather than inheriting an interactive SLO or assuming instantaneous full batches.

## 2026-07-17 — typed offline terminal

- **Question:** What traffic, decode residence, pooling, stability, capacity, and replica conditions can realize c12/c14 without treating a synchronized benchmark batch as a continuous endpoint?
- **Action:** Bound the exact campaign, strict DeepInfra-FP8 target, all-in factors, corrected FP8-KV capacity, c12/c14 attention residual, and the prior queue model by hash. Derived deterministic Little's-Law, Poisson/Erlang pooling, whole-service/decode-share, stable-utilization, replica, and 10K-c1 sensitivities. No live-owner state or provider was accessed.
- **Evidence:** At `0.717061438` req/s, natural average decode M=12/14 requires mean decode residence `16.734968/19.524129` s. At the strict conservative `1.158355134` req/s it requires `10.359517/12.086103` s, and at 2x planning `8.367484/9.762064` s. At planning traffic, synchronized Poisson batches pay `7.670194/9.064774` s mean request pooling wait and `23.655183/27.114231` s p95 first-to-fill delay before service. Corrected FP8-KV logical peak totals are `43.876238/44.630612` GiB, leaving `0.827762/0.073388` GiB in the 44.704-GiB envelope; c14 is allocator-sensitive. Extra balanced replicas dilute traffic and multiply required residence/pooling at fixed total demand; cost-correct demand must scale with replica count.
- **Interpretation:** `background_batching_credible_region`, conditional rather than endpoint-proven. The campaign permits background latency trades and supplies no hard SLO, so these durations are not declared unusable. Natural resident concurrency and synchronized active batches are separate claims. Any row with `lambda*S>=1`, any failed allocator bound, or any externally rejected completion/reliability distribution is unusable.
- **Next:** A later endpoint merges the exact telemetry contract in `QUEUE_BOUND.json`: time/token/step-weighted decode-batch distributions, overlap-aware prefill/decode intervals, per-request timestamps, arrivals/completions/failures/reloads, queue drift, memory peaks, and Little's-Law reconciliation. The separate 10K c1 view remains methodology-only.
- **Artifacts:** `QUEUE_BOUND.json` SHA-256 `14f9254098e14c95272863e8b4119fdaaf6d833f4c01a531b9fbd204b506d965`; `SOURCE_MANIFEST.json` `a82e064d4fdb20eb0704727e7d8c0fa7981d53f2420a41bb5074d52c617a0463`; calculator `918376f9929e7c6188507ceb0215a4c3bfc13f3571da9e38efc96f202232fed2`.
