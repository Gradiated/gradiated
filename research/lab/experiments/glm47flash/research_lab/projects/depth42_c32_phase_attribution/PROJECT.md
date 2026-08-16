# Depth42 c32 measured phase attribution

## Question

What measured L40S mechanism explains depth42's `616.602` c16 to `686.910` c32 gain, and does the terminal telemetry identify one materially different non-depth intervention with a conservative path to `606.355`?

## Why this matters

Depth reduction now has two measured candidates, but the portfolio should not turn into a serial layer-count sweep. The new depth42 archive is the first clean near-original c16/c32 pair with complete request, telemetry, histogram, and memory evidence. A fast attribution can distinguish batch reuse from prefill, queue, MLA, MoE, memory, power, or synchronization effects and either nominate a focused next mechanism or close the available observability without another paid profiler run.

## Fixed evidence and scope

- Primary archive: `../minimal_depth42_v2_l40s_direct/artifacts/nebius_l40s_minimal_depth42_v2_c16c32_2026-07-16-r2/summary.json` and `vllm-awq-batch.tar.gz`, archive SHA-256 `ee0f3f3b3d3abfa2f9610320a5be44934be8493a61f52a0d339e83ca4b3d8541`.
- Profiles: c16 `616.602087` tok/s in `53.142863` seconds; c32 `686.910494` in `95.406899`; all 96 measured requests complete; c32 peak `43,871 MiB`; exact cache-off 8K/1K geometry.
- Comparators may include content-bound full47 r3 and student39 c16/c24/c32 only where runtime/workload fields match. Label model-depth, max-sequence, request-count, and quality differences; do not transfer throughput.
- Campaign gate is `594.466`, robustness marker `606.355`, planning `$1.10/hour`, and 300-second background envelope. The runner's stricter c32 SLO flag is not the campaign boundary.

Work offline for at most 900 seconds, 6 GiB RSS, 24 MiB new artifacts, and `$0`. Reconstruct exact phase intervals and aggregate telemetry within each c16/c32 arm; quantify GPU utilization, power, clocks, memory, TTFT, TPOT, queue, prefill/decode proxies, batch efficiency, and request-tail structure with uncertainty. Do not treat the degenerate fixed-output histograms as target-usage evidence. Attribute only what the retained counters identify.

Return exactly one terminal result:

- `NOMINATE_MECHANISM`: one non-depth mechanism is source/runtime-bound, acts on an identified measured critical path, and has a conservative endpoint path to `606.355` plus one bounded falsifier;
- `ATTRIBUTION_CLOSE`: telemetry cannot separate mechanisms or every identified lever misses the gate.

Do not use CUDA, network/provider resources, mutate checkpoints or shared code, build a controller, prepare a paid invocation, revisit c40+, or propose another layer-count candidate. Produce one compact machine-readable attribution artifact, an optional calculator, and a concise research-log update. No successor.

## Available resources

Use the fixed local projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
