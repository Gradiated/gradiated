# Wake-up brief — 2026-07-12

Status as of 10:30 CEST. The live version is [slackhog.ngrok.dev/codex](https://slackhog.ngrok.dev/codex); the complete evidence is in the [overnight report](OVERNIGHT_REPORT_2026-07-12.md).

## Bottom line

**Continue the research engine, but do not launch an inference provider or authorize custom silicon on current evidence.**

The project now tests real model changes, executable packed representations, serving behavior, external hardware simulators, GLM-specific mapping/cache mechanisms, and strict business-claim composition. It has already rejected several attractive shortcuts. It has not yet measured any reduction in delivered dollars per token, and nothing supports 5–10×.

The business thesis also became materially narrower overnight. Fireworks and Baseten already implement most of the GLM software stack. NVIDIA now publishes a Rust full-stack serving twin, silicon-backed deployment search, and explicit hardware-friendly model-design rules. Etched says it already operates the simulator-to-chip-to-rack path with A0 silicon and substantial capital. A 30-source review also finds active work on cross-layer, temporal, hierarchical, routed, page-aware, offloaded, and accelerator-specific sparse attention. The category is real, but “full-stack simulation,” “remove abstraction tax,” and the obvious DSA/index/gather ideas are not unique moats.

The surviving opportunity is **validated non-obvious model/hardware discovery**: change model architecture or weights, generate the matching executable kernel/hardware contract, and correctly predict quality/SLO/cost effects that incumbent deployment optimizers cannot obtain from configuration search.

## What the experiments established

| Layer | Result | Decision |
|---|---|---|
| Selective Qwen INT4 quality | BF16-scale proxies pass at 512 and 4,096 targets. Exact-source PIQA-256 is 174/256 baseline versus 175/256 candidate; the point gate passes, but the 95% paired interval crosses the two-point margin | Promising representation, confirmatory task non-inferiority still inconclusive |
| Selective Qwen INT4 kernel | Exact packed tensors retain 37.5% of BF16 bytes, but scalar packed execution is 1.368× slower and matched B1/B4/B16/B64 execution is 1.7–6.6% slower | Reject the current safe-Rust kernel as a speed lever; compression is not performance |
| Prospective ARM packed kernel | After locking a 1.75× prediction in private commit `4b7b172e`, the explicit NEON path measures 4.457× over scalar packed and 3.284× over scalar f32-QDQ on the same three tensors; all correctness gates pass | Real local architecture-specific kernel win, but prediction magnitude error is 44.7%, so predictive accuracy fails and no full-model/serving/cost claim follows |
| Qwen KV architecture change | The largest one-shot quality pass removes only 1.786% of KV bytes, an ideal 1.018× ceiling. Full 8→4 sharing destroys quality | Reject one-shot merging as material |
| Trained Qwen 8→4 recovery | Rank-8 Q/O recovery restores only 3.80% of the NLL gap after 2,048 training targets; all gates fail | Stop this exact recipe; do not spend the projected 83 minutes on the same continuation |
| Local serving | Prior c1/c8 repeats differ 1.51×/3.08×. A frozen 20-pair campaign accepted one c8 pair, then 355 admission samples produced no clean streak and no resumed run | Host-contamination blocked; no calibration or performance conclusion |
| Public agentic workload proxy | 64 deterministic synthetic requests across eight sessions with exact 5K–131K input bounds, 27K mean, dynamic prefixes, tool delays, and class SLOs | Use for the next simulation stage; it is not private benchmark data or performance evidence |
| Dense hardware mapping | Twelve native SCALE-Sim cases show 2.8–2.9× mapping sensitivity, but Qwen and GLM rank all base architectures identically and larger SRAM gives no native benefit | No model-specific dense-array win in this slice; prioritize irregular DSA/gather/route/cache/fabric paths |
| Timeloop | Exact Qwen problem parses through the real pinned frontend; native mapper and six dependencies are absent | Useful contract boundary, no cycles/energy/area result |
| GLM independent mapping | Modeled hop bytes fall 85.86%, but residency preference depends sharply on context and concurrency | Strong search dimension and incumbent control, not a cost result |
| GLM P/D | Neutral P/D is 5.18% worse; it becomes 35.22% better only with explicit uncalibrated phase effects, and congestion can erase the gain | Measure the break-even inputs; never assume disaggregation is cheaper |
| Joint business claim | The Rust gate admits 0/7 current records for a combined GLM output-cost claim | No marginal effects may be multiplied into $/token |
| Predictive validity | The checked gate inventories 61 JSON artifacts and admits one prospective component pair; direction is correct but 44.7% effect error fails the 15% bound | The engine is not calibrated and no simulated saving may be promoted |
| Public-agentic GLM mapping | Across 64 synthetic token-geometry requests, partial-residency preference shifts from 64 coupled at C1 to 48 decoupled plus eight overlaps at C64; candidate full capacity remains uncertain for all requests at every concurrency | Useful search segmentation, no deployment winner, latency, SLO, or cost result |
| HBM3 irregular-memory oracle | A fully drained patched-native Ramulator2 sweep completes 1,363,968 callbacks. Logical-token sorting is 27.74% better at 32 B but 59.19% worse at a 1,152 B BF16 record geometry | Reject geometry-insensitive locality claims; preserve bank parallelism in the next candidate |
| Small-model proxy | Qwen3-0.6B remains the local quality-bearing proxy; NOSA-1B is the first future CUDA proxy; a tiny random DeepSeek fixture is rejected | Small models can reject mechanisms or promote GLM experiments, never validate GLM transfer |

## What this says about the company

The likely initial company is not “another vLLM” and not immediately “another Fireworks.” A more defensible sequence is:

1. Build the independent co-design and evidence engine until it predicts held-out real-hardware intervention ordering and magnitude.
2. Discover one model or hardware change that produces at least **1.5× lower measured fully loaded cost** under non-inferior quality and the same agentic SLO.
3. Reproduce the mechanism on a second model, or show enough model-specific contracted volume to amortize its lifetime.
4. Sell or use the validated discovery/IP before taking provider operating risk.
5. Advance to synthesis/PPA only if at least 30% residual benefit remains after the best commodity stack; tape out only against contracted demand and pessimistic yield, schedule, NRE, lifetime, and price decline.

The NEON result is the first direct support for the narrower “remove implementation tax through model-specific code” mechanism: an explicit architecture path erased the scalar packed regression in a controlled component. It is equally strong evidence against trusting the current predictor: the prospectively locked magnitude missed badly. The next burden is to retain the kernel advantage against a tuned BF16/Accelerate or production runtime baseline, extend it through a full packed model, and predict the next intervention before measurement.

This is a harder thesis than the starting idea, but it is now falsifiable. The main near-term company asset is the quality of prediction and evidence, not the number of simulator modules.

## The next decisive test

The machine-readable [business ledger](../validation/results/model-stack-business-decision-2026-07-12.json) defines the next real gate: compare an incumbent-grade GLM control with exactly one candidate intervention on the same frozen agent workload and fleet. Start with the 64-request public token-geometry proxy spanning 5K–131K input tokens, then replace it with a privacy-safe measured trajectory set before any product claim. Measure aggregate input/output throughput, TTFT/TPOT distributions, task and end-to-end agent success, cache/transfer behavior, power, failures, availability, and fully loaded cost. The separate 90K case remains a provider-inspired analytical anchor, not a representative-workload claim.

Pass only at ≥1.5× lower measured cost per billable token with non-inferior quality and every SLO met. Kill the tested lever when it exhausts its predeclared implementation/calibration budget without passing. Keep custom silicon killed unless the result holds on two models and retains a material advantage after the best commodity implementation.

## Primary artifacts

- [Full overnight evidence report](OVERNIGHT_REPORT_2026-07-12.md)
- [Business validation and competitor analysis](BUSINESS_VALIDATION.md)
- [Optimization decision register](OPTIMIZATION_DECISIONS.md)
- [Simulator landscape](SIMULATOR_LANDSCAPE.md)
- [Exact-source PIQA result](../validation/results/qwen3-0.6b-int4-o-gate-up-piqa256-bf16scale-v1.json)
- [Packed INT4 batch frontier](../experiments/qwen3-0.6b/int4-packed-batch-frontier-v1.json)
- [Locked ARM-NEON prediction](../validation/predictions/qwen3-0.6b-int4-aarch64-neon-v1.json)
- [Prospective ARM-NEON measurement](../experiments/qwen3-0.6b/int4-aarch64-neon-v1.json)
- [KV recovery result](../validation/results/qwen3-0.6b-kv-head-recovery-2k-v1.json)
- [SCALE-Sim external sweep](../validation/results/qwen3-glm-scalesim-v3-gemm-sweep-v1.json)
- [Controlled serving terminal](../validation/results/qwen3-0.6b-vllm-cpu-repeatability-v1.json)
- [Public-agentic workload proxy](../experiments/workloads/aa-agentperf-public-proxy-v1.json)
- [Fail-closed business ledger](../validation/results/model-stack-business-decision-2026-07-12.json)
- [Fail-closed competitive landscape](../validation/results/inference-codesign-competitive-simulation-landscape-2026-07-12.json)
- [Fail-closed predictive-validity gate](../validation/results/simulator-predictive-validity-gate-2026-07-12.json)
- [Public-agentic GLM mapping screen](../experiments/glm-5.2/agentic-mapping-screen-v1.json)
- [Fully drained synthetic HBM3 sensitivity](../validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json)
- [Small-model proxy decision](SMALL_MODEL_PROXY_SELECTION.md)
- [GLM joint-claim composition](../experiments/glm-5.2/current-cost-claim-composition-v1.json)
