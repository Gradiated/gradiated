# Measurement-driven research loop

Use this loop for broad optimization campaigns where discovering the bottleneck is as important as testing a known intervention.

## 1. Map the system before changing it

Partition observations by workload class, concurrency, and phase: setup, model load, prefill, steady decode, queueing, cache transfer, tool wait, and teardown. Build a critical-path timeline and resource ledger rather than ranking kernels by summed duration alone. Overlapping CPU/GPU work, CUDA graphs, asynchronous collectives, and profiler aggregation can make totals exceed wall time.

Collect every low-cost signal that can distinguish competing explanations:

- request: arrivals, prompt/output tokens, TTFT, inter-token/TPOT, end-to-end latency, queue time, failures, retries, finish reason, cache reuse, and per-class SLO;
- scheduler: iteration time, running/waiting/swapped requests, scheduled prefill/decode tokens, batch composition, KV occupancy/fragmentation, preemptions, and graph bucket;
- accelerator: utilization, active cycles, clocks, power, temperature, VRAM, allocation peaks, OOM/resource failures, kernel grid/block, registers, shared memory, occupancy, launch gaps, HBM bytes/bandwidth, L2 hit rate, arithmetic intensity, tensor-core use, and stalls;
- host/network: CPU saturation, Python/runtime gaps, launch latency, memory copies, PCIe/NVLink/fabric traffic, collective time, retransmits, and storage/input transfer;
- model: layer/module phase, attention/MoE/routing/MTP work, expert load skew, accepted draft length, precision/layout, tensor shapes, sparsity, and quality deltas.

Record unsupported counters as unavailable; do not silently substitute telemetry averages that include setup for steady-state behavior.

## 2. Maintain a typed opportunity register

Each candidate must contain:

- observation and evidence class;
- exact scope: model, revision, workload, phase, concurrency, software, and hardware;
- measured resource signature and uncertainty;
- competing explanations and the measurement that separates them;
- controllable mechanism and changed variable;
- theoretical or measured upper bound and modifiable fraction;
- predicted effect with units and confidence interval or explicit unknown;
- quality, correctness, SLO, implementation, and transfer risks;
- cheapest falsifier, expected information gain, cost, duration, and cleanup;
- promotion, kill, and residual-bottleneck rules.

For `scripts/opportunity_register.py`, use the compact canonical fields `id`, `observation`, `evidence_scope`, `competing_explanations[]`, `mechanism`, `falsifier`, `next_measurement`, `cost_usd`, and normalized judgment fields `decision_impact`, `uncertainty`, `discrimination_power`, `readiness`, and `transfer_penalty` in `[0,1]`. The complete machine contract is [opportunity-register.schema.json](opportunity-register.schema.json). Include units in every measurement name or value object. Use `unknown`, not a guessed number, for unavailable effect size or resource share. The ranking score is a triage heuristic, never a performance prediction.

Rank by decision value per dollar, not expected speedup alone. Include negative controls and candidates predicted to regress so the harness is tested for sign discrimination.

Intuition is an asset when the search space is novel. Record the intuition, the data pattern or first-principles argument that suggested it, and what observation would make it wrong. A speculative idea may be admitted when its falsifier is cheap and discriminating; uncertainty is a reason to measure, not a reason to suppress creative candidates.

## 3. Climb a fidelity ladder

Use increasingly accurate models and stop at the cheapest failing rung:

1. Conservation law or impossible upper bound: bytes, FLOPs, capacity, bandwidth, latency, Amdahl ceiling, or queue stability.
2. Analytical/roofline model with best-, expected-, and worst-case assumptions.
3. Deterministic event, memory, network, or scheduling simulation with sensitivity sweeps and negative controls.
4. Independent CPU/reference oracle for functional correctness and numerical error.
5. Reduced-model or trace replay for mechanism and tooling validity; never transfer magnitude to a different architecture.
6. Exact-shape component harness using production dtypes, strides, layouts, length distribution, resource limits, and cold/hot cache conditions.
7. Target-hardware microbenchmark with compile metadata, counters, paired samples, and uncertainty.
8. Same-session matched server A/B/A or randomized interleaving with identical model, workload, quality, SLO, and allocation.
9. Representative arrival/concurrency frontier and provider-matched comparison.

Calibrate each rung against the next. Score prediction direction and magnitude. A model that cannot predict held-out measurements is a falsification tool, not an optimizer.

## 4. Explore broadly, then narrow causally

Start with a cross-stack opportunity map: architecture, representation, kernels, runtime/graphs, scheduler, cache/memory hierarchy, parallel mapping/network, hardware, workload specialization, and provider economics. Use screening designs, bounded autotuning, or sensitivity sweeps to identify active factors. Follow with one-variable or small-factorial matched experiments that separate confounded layers.

After every arm:

1. Compare prediction with measurement and record effect error.
2. Update the causal bottleneck model and uncertainty.
3. Measure the residual critical path; a successful optimization may move the bottleneck.
4. Re-rank the opportunity register.
5. Execute the highest-information admissible next arm while budget and decision remain open.

Do not repeatedly optimize a component after its end-to-end ceiling falls below the campaign gate.

## 5. Parallelize without losing causality

Use one coordinator for mutable provider state, spend, resident sessions, and cleanup. In parallel, assign independent workers to:

- parse traces and validate profiler semantics;
- build analytical bounds and simulators;
- search prior art and source-pin candidate mechanisms;
- generate legal candidate configurations;
- add local tests and correctness oracles;
- audit artifacts, manifests, statistics, and claim scope;
- prepare conditional preregistrations for likely outcomes.

Run concurrent hardware arms only when they do not share mutable state, each has an owner/watchdog/cap, and the increased spend buys wall-clock decision value. Prefer parallel offline preparation plus sequential arms on one retained GPU when image, weights, or compilation dominate setup.

## 6. Admit claims narrowly

A component result supports only its measured component. A simulation supports only its modeled geometry. A microbenchmark supports only its shapes and hardware. Claim quality- and SLO-adjusted cost improvement only after a matched end-to-end workload with valid quality, service level, availability, and total allocation economics.

## 7. Default diagnostic conventions

Use these defaults when the campaign has not justified stronger task-specific values:

- Treat observer instrumentation as the candidate and the lowest-overhead observer as stock. Measure profiler-off/on perturbation; shorten or sample traces when throughput or median service time changes by more than 3%, or tail latency by more than 5%.
- Define queue time separately from admission until first scheduling. Define prefill per request from first scheduled prefill work through its first generated token. Define steady decode only for iterations with no scheduled prefill tokens. Label mixed iterations separately. When asynchronous work crosses a boundary, attach it by dependency/request identity rather than timestamp containment alone.
- Attribute critical-path time with the union of non-overlapping dependency intervals inside the request/iteration scope. Report summed kernel duration separately and never use it as a wall-time share.
- For close decisions, collect at least three alternating control/candidate repetitions and retain per-request or per-launch raw samples. Default to a seeded 10,000-resample paired percentile bootstrap and report the two-sided 95% interval; bind the seed to the experiment identity. Increase repetitions when the confidence interval crosses the decision gate; stop when the preregistered precision, cap, or timeout is reached.
- If HBM/L2 counters are unavailable, a timing result may remain valid at its component scope, but a memory-bound diagnosis stays unproven. Use calibrated byte bounds, cache perturbations, clock sensitivity, or hardware contrasts only as discriminating follow-ups, not substitutes presented as counters.
- Place stock observational replay before implementation work on the fidelity ladder when the current bottleneck attribution is weak.
- Convert a session time cap into dollars before allocation using authenticated compute, disk, IP, storage, and other material rates when available. When ancillary rates are unavailable, reserve at least the greater of 10% of known exposure or $0.10 and prohibit a settled-cost claim; use a larger margin when transfer/storage volume makes that bound implausible.
- Require request-to-phase attribution coverage of at least 95% for a phase-share claim. Otherwise label the trace incomplete and use it only to generate candidates.
