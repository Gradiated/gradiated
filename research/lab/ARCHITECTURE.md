# Inference Foundry

Inference Foundry is a model-specific inference co-design system. It searches model representations, kernels, serving policies, and hardware configurations while preserving a fixed model-quality contract.

The first implementation uses a multi-fidelity funnel:

1. A deterministic analytical performance oracle rejects dominated candidates quickly.
2. A serving simulator measures latency, goodput, memory pressure, and phase activity under a canonical agentic workload.
3. Activity-based economics produces separate input-token and output-token cost floors.
4. Constrained search ranks candidates that satisfy quality, memory, and latency requirements.
5. External oracles can replace analytical estimates with kernel measurements, accelerator simulation, RTL, or silicon results without changing the serving and economics layers.
6. Measured-serving and calibration contracts compare request-level and phase-level evidence against the same immutable identities before any fidelity promotion.

The research environment remains modular. A winning deployment can be generated as a specialized runtime with unnecessary abstractions removed.

## Stable boundaries

`ExperimentSpec` is the immutable input contract. `PerformanceOracle` turns scheduled phase work into time, energy, and memory estimates. `SimulationReport` records observable serving behavior. `EconomicReport` converts phase activity into provider cost and price floors. `SearchReport` retains feasible candidates and their provenance.

Artifacts use content-derived identities. Reports include the experiment identity, simulator version, assumptions, and source of every non-analytical measurement.

Measured campaigns have an admission layer before the workload runner. The Qwen vLLM repeatability harness freezes schedule, host/process thresholds, cold/warm semantics, provenance, retries, and terminal behavior; contamination is retained as evidence and can block execution without producing a performance sample. Environmental control is therefore part of measurement validity, not an informal operator step.

Public workload geometry is lowered into the same `CanonicalTraceV2` and `WorkloadContractV2` types as measured traces. The AA-AgentPerf public proxy adds session, turn, prefix, and tool-delay metadata while keeping all project-chosen distributions and SLOs labeled synthetic. Private benchmark data and vendor performance never enter through that boundary.

Claim composition is exact-set and fail-closed. Component, marginal, analytical, vendor, cross-model, cross-workload, or claim-locked effects cannot be multiplied into latency, throughput, energy, or token-cost claims. Those objectives require one exact scope-matched measured end-to-end artifact covering the full intervention set.

Predictive validity is a separate promotion boundary. A prediction must be locked before a blinded measurement, bind exact model/workload/hardware/software/intervention/metric identities, use globally disjoint calibration and holdout cases, and verify the actual prediction, measurement, quality, and SLO artifact bytes plus in-file identities. The current inventory admits one prospective component pair, but its magnitude error fails and the multi-intervention gate remains `NOT_MET`; simulator execution does not imply calibration.

Prospective kernel experiments freeze the implementation, request, tensor identities, scope, prediction, and prediction commit before the timed binary starts. The measurement report exposes the exact same scope and aggregate metric paths, allowing the gate to distinguish a real component improvement from prediction accuracy. A correct direction with inaccurate magnitude may advance implementation work while still failing simulator promotion.

External hardware oracles retain their own fidelity contracts. The Ramulator2 adapter injects explicit HBM address vectors, applies backpressure, and continues ticking until every callback completes; its current evidence is synthetic within-geometry controller-cycle sensitivity. SCALE-Sim contributes uncalibrated dense-array mapping comparisons, while Timeloop currently contributes a frontend contract only. None automatically becomes GPU time, energy, or economics.

Model identity includes a pinned revision and quality-suite identity. Passing measured quality is scoped to the exact model, revision, model fingerprint, variant, change fingerprint, and suite; evidence from a smaller model or a subset of changes cannot unlock an economic conclusion.

Hardware synthesis may emit infeasible diagnostic points, but the co-design study rejects them before serving simulation, capacity planning, attribution, or costing. Rejected points remain visible with their violated physical constraints.

The live dashboard is a read-only presentation boundary over checked-in summaries and validation documents. Its prompt inbox is isolated, access-code protected, gitignored, and has no authority to change evidence or bypass a gate.
