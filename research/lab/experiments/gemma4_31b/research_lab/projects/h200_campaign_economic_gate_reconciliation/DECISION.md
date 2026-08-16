# H200 economic gate — typed correction

The corrected exact checkpoint identity is `google/gemma-4-31b-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`; it matches the active endpoint brief and passing checkpoint terminal. At the `$3.25/GPU-hour` H200 production planning rate, the campaign-mix market hurdle is **1.453–1.470 completed requests/s raw GPU-only** for the captured `$0.000621447–$0.000614287` request-cost frontier. After the explicit planning factors—85% utilization, 1.10 replica/headroom, 1.05 non-GPU, 1.03 reliability, and 1.03 storage/orchestration—the required range is **2.094–2.119 requests/s**. The conservative range is **3.383–3.422 requests/s**. The full per-provider and `$2.925–$3.60/hour` sensitivity surface is in [H200_ECONOMIC_GATE.json](H200_ECONOMIC_GATE.json).

The gate is computed as:

`required_rps = (GPU_rate / (3600 × market_request_cost)) × replica_headroom × non_gpu × reliability × storage_orchestration / utilization`.

The 10K-input single-stream arm is separate. It must report raw throughput, latency, and measured cost for `10,000 input / 358 output` at concurrency 1. The AA `$0.14/M` / `$0.00064008` value is a 7:2:1 methodology blend, not component pricing for that exact request; a fresh-input/no-cache sensitivity is recorded in the JSON and is not substituted for the campaign-mix gate.

The inherited `1.825 completed requests/s` value is corrected to **an independent H100-context promotion floor**, not an H200 market derivation. At the H200 planning rate it implies `$0.000494673` raw GPU cost/request, but `$0.000713108` after planning factors—above the current retail frontier. It is only 86.14% of the cheapest planning-base H200 market threshold. Retain it only as a separate packet/promotion requirement until its missing derate provenance is repaired.

The matched engine gate remains independent: candidate sustainable cost/request must be `<= 0.90 ×` contemporaneous matched vLLM cost/request on the same H200, identities, workload, valid saturation point, and quality/reliability boundary. Promotion requires both gates plus the required raw-output and quality checks. This project did not query or mutate the provider and does not delay the active owner.

Evidence labels: market capture and shared price inventory are measured/source-bound inputs; all thresholds are derived. No performance, quality, or provider claim follows.
