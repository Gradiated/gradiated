# Simulation fidelity

Inference Foundry promotes candidates through increasing fidelity. Results never silently mix fidelity levels. Calibration is an evidence property of a specific `(tool, model, workload, hardware, software, metric)` scope, not something conferred by a level name.

## Level 0: analytical screening

The roofline model derives arithmetic work, weight traffic, KV traffic, communication volume, memory capacity, service time, and energy from typed specifications. It exists to reject impossible and dominated candidates quickly.

## Level 1: action simulation

The model graph lowers into tensor tiles, memory transfers, collective operations, and synchronization events. The hardware simulator executes those actions across compute arrays, SRAM banks, HBM channels, on-die networks, and device links. Contention, overlap, utilization, latency, and component energy can be explicit while still remaining uncalibrated counterfactuals.

## Level 2: external detailed or calibrated simulation

Adapters invoke independent tools for shortlisted candidates:

- Timeloop and Accelergy for mappings, area, and energy.
- SCALE-Sim for systolic arrays and Ramulator2 for explicit memory-controller sensitivity.
- Chakra and ASTRA-Sim for device and rack communication.
- Accel-Sim for supported NVIDIA kernels.

The imported result records tool version, configuration identity, raw artifacts, source/build modifications, calibration status, scope, and uncertainty. An external native run is not automatically calibrated, and a compatibility-patched build must not be labeled pristine.

### Current external-evidence boundary

The checked [`Ramulator2 HBM3 report`](../validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json) is patched-native, fully drained, and deterministic. It contains 18 cases × two replays and 1,363,968 completed callbacks; accepted, served, callback, controller-tick, total-read-latency, and row-outcome counts reconcile. Ascending logical-token order changes drained controller cycles by **−27.744%** for the one-32-byte-transaction geometry but by **+59.194%** for the synthetic one-layer 1,152-byte geometry. Cluster-64 changes by **−50.569%** and **+2.709%**, respectively. These reversals establish within-geometry sensitivity to locality and bank parallelism.

They do not establish calibration, GLM trace fidelity or performance, GPU/kernel overhead, wall-clock latency, end-to-end serving, model quality, energy, cost per token, provider superiority, pristine-source execution, or tapeout readiness. The probe has one channel/controller, one injection attempt per tick, and no refresh. Logical-token order is not a physical-HBM-vector sort, and the cluster cases use different selected token sets.

The [`agentic token-geometry mapping screen`](../experiments/glm-5.2/agentic-mapping-screen-v1.json) is exact partial-residency and bounded full-capacity arithmetic, not serving simulation. Across 64 retargeted synthetic requests, partial-policy counts in coupled/overlap/decoupled order are `64/0/0` at C1, `63/0/1` at C8, `48/0/16` at C16, `24/0/40` at C32, and `8/8/48` at C64. Candidate full capacity is uncertain for all 64 requests at every concurrency. Tokenizer equivalence, outputs, arrivals, tool timing, dynamic prefix behavior, context-dependent compute, network timing, quality, SLO, energy, cost, and deployment performance remain outside scope.

### Proxy ladder

The [small-model proxy policy](SMALL_MODEL_PROXY_SELECTION.md) keeps Qwen3-0.6B as the current local quality-bearing model for stack plumbing, dense accounting, and model-edit rejection. NOSA-1B is a future single-CUDA-GPU proxy for sparse locality and KV offload after its pinned runtime is qualified. Neither proxy validates GLM-5.2 performance or cost; a proxy pass only admits a GLM-specific experiment.

## Level 3: implementation validation

Generated kernels run against reference implementations. Model transformations run a fixed quality suite. Serving changes replay the canonical trace on real hardware. Measurements include tails, power, memory, and numerical correctness.

The first prospective implementation-level kernel result is the checked [AArch64 NEON packed matvec](../experiments/qwen3-0.6b/int4-aarch64-neon-v1.json). It measures a 4.457× local speedup over scalar packed and 3.284× over scalar f32-QDQ across three exact tensors with correctness gates passing. The precommitted prediction was 1.75×, so 44.7% relative effect error fails predictive promotion. This validates only the local intrinsic component, not a tuned BF16 baseline, full model, serving, energy, or economics.

## Level 4: hardware validation

Differentiating blocks pass functional simulation, synthesis, place and route, and FPGA or emulation validation. Silicon conclusions require independent estimates for process, yield, package, memory, power delivery, thermals, server integration, and one downside scenario.

## Promotion rules

A candidate can advance only when it is feasible at its current level, satisfies the quality and SLO contract, improves the target economic metric beyond its uncertainty interval, and retains all input artifacts needed for reproduction. Simulation-only comparisons may prioritize measurements, but cannot promote cost or custom silicon without held-out measured pairs.

The fail-closed [predictive-validity machinery](../validation/predictive_validity/gate.py) requires exact scope identity, predictions locked before measurement, blinded non-overlapping holdouts, at least three interventions across two context regimes, at least one predicted regression, all directions correct, maximum relative effect-size error at most 15%, and Spearman rank correlation at least 0.8. The current [gate result](../validation/results/simulator-predictive-validity-gate-2026-07-12.json) is **NOT_MET** with one admitted prospective pair. Its direction is correct, but 44.7% effect-size error exceeds the threshold; intervention/regime counts, regression coverage, rank correlation, and quality/SLO cost evidence are also insufficient. Predictive validity, model-specific advantage, provider competitiveness, cost promotion, and custom-silicon underwriting remain false.
