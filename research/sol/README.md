# Inference Foundry

A Rust-first environment for model-specific inference co-design across model representation, kernels, serving, hardware, and economics.

The current local quality-bearing target is pinned Qwen3-0.6B; Qwen3-8B remains an analytical scale-up study, and GLM-5.2 is the model-specific target architecture. The optimization objective is the lowest sustainable input and output token price subject to fixed quality and latency constraints.

This repository is independent of vLLM. vLLM, SGLang, TensorRT-LLM, kernel toolchains, and hardware simulators are benchmark targets or external backends.

## Current status

The environment runs a complete Level 0 analytical study: model and kernel transformations lower into phase work, model-specific hardware is sized and feasibility-checked, an event-driven serving simulator evaluates class SLOs, capacity planning selects a fleet, and activity-based economics produces separate input/output token costs. Exact factorial Shapley attribution, TCO sensitivity, measured-serving ingestion, external-simulator replay, and a measured-vs-predicted calibration protocol are implemented. Predictive calibration itself is **not** established.

A fail-closed claim-composition gate prevents marginal or cross-scope results from being multiplied into a business claim. The current GLM request spans six interventions and seven evidence records but admits zero joint measured output-cost claims.

The first Qwen3-8B result is still an analytical hypothesis, not evidence of a measured provider advantage. On Qwen3-0.6B, blanket INT4 fails the declared proxy contract; a tensor-selective group-8 variant passes 4,096 teacher-forced targets and its frozen exact-source PIQA-256 point gate, although the paired interval leaves confirmatory non-inferiority inconclusive. Its exact packed scalar and matched batch paths regress despite retaining 37.5% of BF16 tensor bytes. A prospectively locked explicit AArch64-NEON path then measures 4.457× over scalar packed and 3.284× over scalar f32-QDQ on the same tensors, showing that architecture-specific code can erase this component tax. The locked 1.75× prediction misses magnitude by 44.7%, so this is not predictor calibration, tuned BF16, full-model, serving, or cost evidence. One-shot KV-head sharing passes only at 1.786% lower cache bytes. A separately sourced 2,048-target recovery run for material 50% sharing restores only 3.80% of the NLL gap and fails all five gates, so that exact small-budget recipe is stopped.

A frozen 20-pair vLLM CPU repeatability campaign accepted one earlier c8 cold/warm pair, then terminated `host_contamination_blocked` after 355 admission samples produced no clean streak; it launched no resumed server and permits no calibration claim. The validation harness now treats environmental admission and resumability as first-class evidence.

The next serving stage has a content-addressed public-agentic workload proxy rather than eight identical short prompts: 64 synthetic requests across eight overlapping sessions, exact public 5K–131K input bounds and 27K mean, dynamic prefixes, tool delays, and three class SLO tiers. It is explicitly not AA-AgentPerf's private test set and carries no borrowed benchmark or performance claim.

For GLM-5.2, exact storage, whole-decode work, sparse-attention/indexing, expert routing, tiered cache, independent parallel mapping, prefill/decode disaggregation, hardware rooflines, capacity, and economic controls are executable. They currently identify conditional policy boundaries and reject several attractive shortcuts; none establishes lower delivered dollars per token than Fireworks, Baseten, or a tuned open-source stack. NVIDIA DynoSim/AIConfigurator, FireOptimizer, existing hardware/serving simulators, NVIDIA model-co-design guidance, and Etched's claimed chip-to-rack program also show that simulator breadth and generic full-stack tuning are not unique moats. The current decision is to continue only toward validated non-obvious model/hardware discovery, keep tapeout at NO-GO, and require measured intervention deltas before any provider or 5–10× claim.

The checked predictive-validity gate inventories 61 JSON artifacts across ten candidate audit families and now admits one exact prospective pair. Its direction is correct but magnitude error is 44.7%; the campaign still lacks three interventions, two regimes, and a predicted regression, so predictive validity remains `NOT_MET`. A fully drained patched-native Ramulator2 experiment also demonstrates why the gate matters: logical-token sorting improves synthetic HBM3 cycles by 27.744% in a one-line model but regresses 59.194% when each token expands to a 1,152-byte BF16 record. These are useful falsifications, not GLM performance or calibration.

The expanded 30-source competitive review finds active work on cross-layer, temporal, hierarchical, routed, page-aware, offloaded, and accelerator-specific sparse attention. The proxy ladder therefore keeps Qwen3-0.6B for local work, selects NOSA-1B for a future single-CUDA-GPU offload experiment, and requires every surviving small-model mechanism to pass a fresh GLM-scale test.

- [Current Qwen3-8B study and decision gates](experiments/qwen3-8b/README.md)
- [Inference co-design learning library](learning/README.md)
- [Measured small-model validation](validation/README.md)
- [Small-model proxy selection](docs/SMALL_MODEL_PROXY_SELECTION.md)
- [Wake-up decision brief](docs/WAKEUP_BRIEF_2026-07-12.md)
- [Overnight business decision report](docs/OVERNIGHT_REPORT_2026-07-12.md)
- [Model-specific optimization register](docs/OPTIMIZATION_DECISIONS.md)
- [Architecture](ARCHITECTURE.md)
- [Fidelity ladder](docs/FIDELITY.md)
- [Comparative validation contract](docs/VALIDATION.md)
- [Predictive-validity gate](validation/results/simulator-predictive-validity-gate-2026-07-12.json)
- [Prospective ARM-NEON result](experiments/qwen3-0.6b/int4-aarch64-neon-v1.json)
- [Synthetic HBM3 sensitivity](validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json)
- [Live findings page](https://slackhog.ngrok.dev/codex) while the shared localhost tunnel is running

## Verification

```sh
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
source /Users/js/dev/vllm-study/.venv/bin/activate
python -m unittest discover -s validation/tests -v
```

Generated reports and model weights are ignored. Checked-in summaries retain the evidence label, hashes, assumptions, and blockers needed to reproduce or reject a claim.
