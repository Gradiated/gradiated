# Model research operating system

## Objective

For each target model, discover and validate model-specific changes that lower quality- and SLO-adjusted inference cost faster than a capable inference team using a generic stack. The durable advantage is the closed loop of measurement, causal history, simulators, candidate search, and deployment feedback—not the volume of patches produced.

The loop should be creative and data-rich. Intuition and first-principles ideas are encouraged, but every idea is recorded with its evidence anchor, uncertainty, cheapest discriminating measurement, and falsifier.

## Per-model state

Every model campaign maintains:

- a pinned model/checkpoint/runtime/hardware/workload identity;
- a tuned stock control and quality/SLO contract;
- a phase- and concurrency-scoped resource map;
- a machine-readable observation-to-opportunity register;
- prospective predictions and measured effect-error history;
- increasingly faithful simulators calibrated to held-out hardware measurements;
- retained-session plans with conditional arms;
- append-only spend, artifact, cleanup, and decision ledgers;
- a current residual-bottleneck map and terminal decision.

## Closed loop

1. Measure the tuned control across workload classes, concurrency, and arrival-rate frontiers.
2. Decompose setup, prefill, steady decode, cache/network movement, queueing, and failures on the critical path.
3. Record candidate mechanisms across architecture, representation, kernels, runtime/graphs, serving, memory hierarchy, parallelism/network, hardware, and workload specialization.
4. Rank candidates by decision resolution per dollar, including negative controls and likely regressions.
5. Falsify at the cheapest faithful rung.
6. Promote only through correctness, quality, resource, predicted end-to-end ceiling, and SLO gates.
7. Run same-session randomized or A/B/A end-to-end validation with uncertainty.
8. Score prediction direction and magnitude, recalibrate the model, and measure the new residual bottleneck.
9. Re-rank and continue until PROMOTE, CONTINUE_NARROWLY, STOP_OR_PIVOT, or the authorized cap.

## Observability standard

Capture all low-cost signals that can separate competing explanations. At minimum where supported:

- requests: exact tokens, arrivals, TTFT, TPOT/ITL, end-to-end latency, queue time, failures, retries, finish reason, prefix/cache reuse, and per-class SLO;
- scheduler: iteration time, active/waiting/swapped requests, batch composition, scheduled prefill/decode tokens, KV occupancy/fragmentation, preemption, and graph bucket;
- GPU: utilization, active cycles, clocks, power, temperature, VRAM, kernel grids/blocks, registers, shared memory, spills, occupancy, launch gaps, HBM bandwidth/bytes, L2 hit rate, arithmetic intensity, tensor-core use, and stall reasons;
- host/fabric: CPU/runtime gaps, memory copies, storage transfer, PCIe/NVLink/fabric bytes and time, collectives, and retransmits;
- model: module/layer phase, attention/MoE/routing/MTP work, expert imbalance, accepted draft length, precision/layout, tensor shapes, sparsity, and quality deltas;
- economics: setup and steady-state exposure, total allocation cost, useful-load/availability assumptions, and denominator identity.

Store missing counters as explicit `unavailable` fields. Never substitute allocation-wide averages for steady-state measurements, or summed overlapping kernel durations for wall-time share.

## Fidelity and simulation ladder

Use lower fidelity to reject, not to approve transfer:

1. conservation, capacity, bandwidth, latency, Amdahl, and queue-stability bounds;
2. roofline and best/expected/worst analytical models;
3. deterministic scheduler, cache, memory, network, or hardware simulation with sensitivity sweeps;
4. independent CPU/reference numerical oracle;
5. reduced-model or trace replay for mechanism/tooling validity;
6. exact production-shape component harness with real strides/layouts and cold/hot cache conditions;
7. target-GPU microbenchmark with compile metadata, hardware counters, raw paired samples, and uncertainty;
8. matched server A/B/A or randomized interleaving on one retained allocation;
9. workload frontier and provider-matched end-to-end comparison.

Calibrate each rung against the next using blinded or held-out cases. A simulator that predicts sign but not magnitude is useful for falsification, not trusted search. Preserve reversals and prediction misses as training data for the next campaign.

## Parallel execution

One coordinator owns provider mutation, spend, resident state, and teardown. Parallel workers prepare the next decisions without racing mutable state:

- trace parsing and profiler-semantics validation;
- prior-art and source-pinned mechanism research;
- analytical bounds and simulator construction;
- legal candidate generation/autotuning plans;
- local correctness oracles and dry-run tests;
- statistics, artifact, manifest, and claim-scope audit;
- conditional preregistrations for likely outcomes.

Parallel GPU arms are justified only when independent ownership and wall-clock decision value exceed the added setup/spend. When weights and compilation dominate, queue likely arms and execute sequentially on one retained GPU, updating observer code live and restarting only the narrowest required layer.

Treat repeated image pulls as a harness defect once their cost is material. Prefer a source-pinned prebuilt runtime in an authenticated registry or a content-addressed provider image/snapshot, with explicit storage cost and lifecycle cleanup. Separate the reusable runtime cache from mutable experiment state; revalidate its digest, driver compatibility, and checkpoint manifest at session start. Do not rebuild or redownload an unchanged runtime for each arm when a cheaper identity-preserving cache is available.

## Tool-building rule

Every repeated manual step is a harness candidate. Prefer reusable tools for:

- environment/checkpoint completeness and source identity;
- workload materialization and exact geometry validation;
- profiler capture, phase attribution, counter extraction, and overhead checks;
- telemetry summaries separated by experiment phase;
- opportunity validation/ranking and conditional-arm generation;
- paired/randomized statistics and confidence intervals;
- prediction scoring and residual-bottleneck updates;
- artifact packaging, hashing, spend reconciliation, and verified cleanup.

Add a failing behavioral test before changing these tools. Reuse recorded API fixtures and no-GPU dry runs so paid hardware measures the scientific question rather than harness plumbing.

The harness itself has an optimization objective: reduce median wall-clock and paid-GPU time from a new observation to a falsifying measurement. Record setup, transfer, verification, load, compile, science, analysis, and teardown durations separately; after every session, automate the largest repeated non-scientific interval. Generate conditional arm contracts before allocation, keep immutable state content-addressed, and make result ingestion update prediction error, opportunity status, residual bottleneck, and the next ranked measurement without hand transcription.

## Search and attribution patterns from prior art

These are methods to adapt and calibrate, not evidence that an intervention works for the current model:

- [Coz causal profiling](https://arxiv.org/abs/1608.03676) motivates counterfactual phase sensitivity. Virtually reduce each measured phase or dependency by 0/25/50/75/100% in a replay model and rank by change in TTFT, TPOT, SLO-goodput, or cost—not by summed hot-kernel duration.
- [Mystique execution-graph replay](https://people.csail.mit.edu/delimitrou/papers/2023.isca.mystique.pdf) motivates normalized dependency traces and reduced subtrace replayers. A replay is admitted only after it reproduces held-out timing, utilization, bandwidth, and power within a prospective error gate.
- [Ansor](https://www.usenix.org/conference/osdi20/presentation/zheng) motivates legality filtering, diverse measured seed configurations, an uncertainty-aware ranker, and cost-aware allocation across active subgraphs rather than a fixed exhaustive grid. Preserve exploratory samples so an early local model cannot collapse the search.
- [Vidur](https://proceedings.mlsys.org/paper_files/paper/2024/hash/b74a8de47d2b3c928360e0a011f48351-Abstract-Conference.html) motivates an event-driven serving simulator fitted to operator surfaces over batch, context, decode position, dtype, and hardware. Trust it only in regimes where held-out sign and magnitude errors pass calibration.
- [Hyperband](https://www.jmlr.org/beta/papers/v18/16-558.html) and [BOHB](https://proceedings.mlr.press/v80/falkner18a.html) motivate broad cheap screening followed by larger budgets for survivors. Use successive elimination only after adjacent fidelity rungs show adequate rank correlation.
- [Duet](https://arxiv.org/abs/2001.05811) and [Kalibera and Jones](https://www.cs.kent.ac.uk/pubs/2012/3233/) motivate common-mode pairing and hierarchical uncertainty. Treat an allocation/session—not requests within one run—as the replication level for hardware effects.

The practical funnel is: low-overhead request/phase timeline, counterfactual sensitivity, selected hardware counters, exact-shape replay or microbenchmark, then same-session end-to-end bracketing. Observer overhead is itself a candidate effect and must be measured against an observer-off control.

## Claim boundary

Component, synthetic, simulated, proxy-model, and provider-reported results remain labeled at their measured scope. A cost improvement requires the same workload, valid quality, service level, availability/load assumptions, and total-cost denominator for stock and candidate. A successful intervention is not complete until the residual bottleneck and prediction error are measured.

The current GLM-4.7-Flash application and prior-art basis are in [`RESEARCH_HARNESS_REVIEW_2026-07-14.md`](../experiments/glm47flash/campaign_100/analysis/RESEARCH_HARNESS_REVIEW_2026-07-14.md) and its linked opportunity register.
