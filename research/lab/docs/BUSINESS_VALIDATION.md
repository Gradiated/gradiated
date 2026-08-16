# Business validation: model-specific inference foundry

Evidence snapshot: 2026-07-12. Public prices and product behavior can change without notice. The checked-in machine-readable companion is [`provider-economics-2026-07-12.json`](../validation/results/provider-economics-2026-07-12.json).

The fail-closed cross-artifact [`business decision ledger`](../validation/results/model-stack-business-decision-2026-07-12.json) now binds 31 sources, 27 internal content identities, 100 exact fact checks, 30 arithmetic checks, and 20 lever decisions. The separate [`current cost-claim composition`](../experiments/glm-5.2/current-cost-claim-composition-v1.json) evaluates seven candidate evidence records and permits zero joint GLM output-cost claims. The checked [predictive-validity gate](../validation/results/simulator-predictive-validity-gate-2026-07-12.json) inventories 61 JSON artifacts across ten candidate audit families and admits one exact prospective component pair, whose 44.7% magnitude error fails the 15% accuracy bound. All measured $/token, provider-superiority, 5–10×, calibrated-simulator, full-E2E, buildable-hardware, and tapeout claims remain false.

## Executive conclusion

The opportunity is real, but the easy version of the thesis is already occupied.

- **Fact:** Baseten publicly describes a production GLM-5.2 stack with custom shared-DSA runtime support, an in-house agent-calibrated NVFP4 conversion, Blackwell execution, KV-aware routing, prefill/decode disaggregation, and MTP. It reports more than 280 streaming tokens/s per user through Artificial Analysis and a 2× throughput gain from disaggregation on its observed workload shapes. This is nearly the full software-side thesis already deployed by a target competitor. [Baseten GLM-5.2 stack](https://www.baseten.co/blog/how-we-built-the-worlds-fastest-api-for-glm-52/) (accessed 2026-07-12).
- **Fact:** Fireworks' GLM-5.2 Fast report goes further: independent expert and attention sharding, data-parallel attention to avoid MLA-KV replication, multi-tier prefix caching, quality-gated low precision, tuned speculation, and prefill/decode separation. It reports a 446 token/s Artificial Analysis peak and about 2× its own Standard path on the same workload. FireOptimizer already automates tuning across hardware mapping, model quantization/tuning, and serving behavior from representative workload data. [Fireworks GLM-5.2 Fast](https://fireworks.ai/blog/glm-5p2-fast), [FireOptimizer](https://fireworks.ai/blog/fireoptimizer) (accessed 2026-07-12).
- **Fact:** Fireworks explicitly markets custom kernels and an engine optimized through memory management; Baseten says its Model APIs are optimized from the bottom up. Both market caching, scaling, model optimization, and dedicated deployments. Merely replacing a general serving abstraction is therefore not a differentiated business. [Fireworks inference](https://fireworks.ai/inference), [Baseten Model APIs](https://www.baseten.co/products/model-apis/) (accessed 2026-07-12).
- **Fact:** Fireworks, Baseten, and model owner Z.AI all list GLM 5.2 at **$1.40/M input tokens and $4.40/M output tokens**. Cached input is **$0.14/M at Fireworks** and **$0.26/M at Baseten and Z.AI**. Fireworks also exposes higher-priced Priority and Fast paths. [Fireworks serverless pricing](https://docs.fireworks.ai/serverless/pricing), [Baseten pricing](https://www.baseten.co/pricing/), [Z.AI pricing](https://docs.z.ai/guides/overview/pricing) (accessed 2026-07-12).
- **Inference:** A credible wedge must be something incumbents cannot copy by ordinary kernel work: model-architecture changes co-trained for a serving target, hardware shaped around those changes, or a simulation and search loop that finds such combinations faster than model and inference teams can do manually.
- **Inference:** Custom silicon is a scale-stage consequence, not the first proof. Software and model co-design on rented hardware should first demonstrate a quality-controlled, SLO-compliant gain. Otherwise silicon multiplies uncertainty by adding NRE, yield, inventory, supply-chain, reliability, and model-obsolescence risk.
- **Modeled threshold:** To price GLM 5.2 at 20% below Fireworks Standard and retain 60% gross margin, maximum infrastructure COGS are **$0.448/M uncached input, $0.0448/M cached input, and $1.408/M output**. On the repository's synthetic cache-heavy agent mix, the combined ceiling is only **$0.1810/M total billable tokens**.
- **Modeled threshold:** At 65% useful load and 98% availability, each $1/hour of fully loaded serving-system cost requires **2,410 billable total tokens/s** on that mix. A $56/hour eight-H200 deployment therefore needs about **134,935 billable total tokens/s** to meet the 20%-discount, 60%-margin case. That is a test requirement, not a prediction that GLM 5.2 achieves it.
- **Modeled robustness result:** The 4,374-point economic frontier finds no workload/price/work region that clears required margin across the complete cost, load, availability, and margin sweep. The prior optimistic BF16 point reaches only 1.0805× headroom with free input and 100% of source peak; 75% of peak falls to 0.8104×, and modest input work at full peak falls to 0.8244×. This source is not the incumbent combined stack and all viability claims remain locked.
- **Conditional capacity result:** Public NVFP4 plus ideal one-byte FP8 semantic KV reduces modeled 64×32K total residency by 108.35 GB, but four modeled B200s still miss by 5.268 GB under the lower cache bound and 104.05 GB under the upper bound. Sixty 32K sequences fit and 61 fail in the lower case. This exposes a possible device-count discontinuity, not TP4, serving, or cost support.
- **Measured model-change result:** A nine-point Qwen3-0.6B KV-sharing frontier finds that the largest one-shot change passing both 512- and 4,096-target proxy gates removes only 1.786% of KV bytes, an ideal 1.018× ceiling. The next point fails; full 50% sharing catastrophically fails. This rejects untrained head merging as a material lever while leaving trained architecture conversion open.
- **Measured task-quality result:** After withdrawing a PIQA loader that lost official trailing whitespace in 30/512 choices, the frozen exact-source Qwen selective-INT4 rerun scores 174/256 baseline versus 175/256 candidate. The declared two-point point gate passes, but the paired-bootstrap 95% delta interval [−2.34,+3.13] points crosses the non-inferiority margin. This is useful provisional subset evidence, not confirmatory task equivalence or a full benchmark.
- **Measured kernel result:** A correct Rust group-8 packed-INT4 smoke retains 37.5% of source BF16 bytes for three selected Qwen tensors, but its simple scalar matvec is 1.368× slower. A corrected identical-loop frontier at batch 1/4/16/64 remains 1.7–6.6% slower at every point. This rejects “bytes saved implies cost saved”; a fair tuned baseline remains mandatory.
- **Prospective architecture-kernel result:** A 1.75× AArch64-NEON prediction was privately committed with the exact implementation before timing. The holdout measures 4.457× over scalar packed and 3.284× over scalar f32-QDQ across the same three tensors, with all correctness and work gates passing. This is direct evidence that architecture-specific code can remove the local packed-decode tax. It is not a tuned BF16/full-model/serving comparison, and the 44.7% prediction-magnitude error fails the 15% predictive gate.
- **External hardware-simulator result:** Twelve pinned native SCALE-Sim cases show 2.8–2.9× same-oracle mapping sensitivity, but Qwen and GLM produce the same five-architecture ranking and larger SRAM provides no native read/core-cycle benefit. This slice does not support model-specific hardware differentiation or cost.
- **Competitive category result:** The expanded 30-source landscape records 19 entries and 12 occupied layers. NVIDIA publishes a Rust full-stack serving twin and explicit co-design rules; Etched claims the chip-to-rack path; and active research already covers cross-layer, temporal, hierarchical, routed, page-aware, offloaded, and accelerator-specific sparse attention. Generic simulation, deployment search, “hardware-friendly models,” and obvious DSA/index/gather ideas are therefore not unique moats.
- **Inference:** If a GLM-specific hardware wedge exists, it is more likely in DSA scan/top-k/gather, expert-route locality, cache capacity/movement, fabric, or control-plane coupling than in a differently sized generic dense array. Those irregular paths now outrank dense GEMM customization for fidelity investment.
- **Conditional serving result:** Independent GLM attention/expert mapping removes 85.86% of modeled hop bytes, but its residency advantage depends on context and concurrency. On the 64-request public token-geometry proxy, the partial policy shifts from 64 coupled requests at C1 to 48 decoupled plus eight overlaps at C64, while candidate full capacity remains uncertain for all requests at every concurrency. Neutral P/D is 5.18% more expensive than aggregate; a 35.22% advantage appears only after explicit, uncalibrated phase-interference and specialization effects. These mechanisms are search variables and incumbent controls, not achieved savings.
- **External memory-oracle result:** A patched-native Ramulator2 HBM3 sweep drains all 1,363,968 callbacks and replays exactly. Sorting the same selected logical tokens is 27.744% better in a one-line abstraction but 59.194% worse when each token expands to a synthetic 1,152-byte BF16 record. This kills a geometry-insensitive locality claim and demonstrates the value of multi-fidelity falsification; it is not calibrated GLM, GPU, energy, or cost evidence.
- **Proxy decision:** Keep pinned Qwen3-0.6B as the current local quality-bearing proxy. Qualify NOSA-1B first on a future CUDA GPU, with Idiap's 1.4B NSA checkpoint as a secondary mechanism control. Reject the tiny random DeepSeek-V3.2 fixture for quality, performance, and cost work. No small model can approve transfer to GLM-5.2.
- **Modeled threshold:** If infrastructure reaches $0.10/M total tokens, only $0.0810/M remains for amortized model-specific engineering and silicon NRE. Amortizing $100M then requires **1.23 quadrillion lifetime tokens**, averaging **13.1M tokens/s continuously for three years**. The current simulator's $300M NRE assumption requires 3.70 quadrillion tokens under the same case.

The company should be built in three falsifiable stages:

1. Prove that the simulator predicts measured intervention deltas and candidate ordering.
2. Prove a quality- and SLO-controlled cost advantage on commodity accelerators for one model, then a second model.
3. Tape out only when contracted demand can amortize a model-specific device under a pessimistic model lifetime and incumbent price decline.

## Competitive reality: both target providers already co-design GLM-5.2

Baseten's 2026-06-22 GLM-5.2 engineering report materially raises the baseline. The public article attributes its API result to the following combined stack:

| Layer | Baseten's reported GLM-5.2 implementation | Consequence for this study |
|---|---|---|
| Model architecture | Custom engine support for shared DSA | Shared IndexShare/DSA is incumbent work, not our advantage |
| Model representation | In-house NVFP4 quantization from FP8, calibrated on agent behavior | Public NVFP4 or equivalent quality is the minimum precision baseline |
| Hardware | NVIDIA Blackwell | H200 BF16 is not the decisive launch-date incumbent |
| Cache and routing | KV-aware replica routing with NVIDIA Dynamo | Cache-unaware comparisons are invalid |
| Serving | Prefill/decode disaggregation with NIXL transfer | Aggregated-only serving is an invalid straw baseline |
| Speculation | GLM-5.2 MTP support | MTP-disabled decode is an invalid straw baseline |
| Production tuning | Workload-specific parallelism and batching | A single average-shape roofline is not product evidence |

Baseten reports more than 280 streaming tokens/s per user, approximately 800 ms TTFT, and 2× higher throughput for disaggregated versus aggregated inference on observed workload shapes. These are **vendor-reported measurements**, not reproduced results. The article does not disclose aggregate capacity, topology cost, utilization, errors, gross margin, or enough workload detail to convert the numbers into COGS. The result therefore cannot calibrate our $/token model directly, but it does establish the stack features that a fair baseline must contain. [Baseten GLM-5.2 stack](https://www.baseten.co/blog/how-we-built-the-worlds-fastest-api-for-glm-52/) (accessed 2026-07-12).

The distinction between streaming speed and capacity is economically decisive. At the public $80/hour cost of eight B200s, the current working commercial gate requires 192,765 billable total tokens/s. Dividing by the synthetic mix's 15.472 billable tokens per committed output token gives 12,459 output-token-equivalent/s if input work were free. That is 44.5 simultaneous 280-token/s user streams under impossible perfect scaling. This arithmetic does **not** estimate Baseten's topology or cost; it demonstrates why a per-user TPS result cannot establish $/token economics without the concurrency-throughput curve, batching, input work, cache behavior, failures, and SLO tails.

Fireworks' 2026-06-30 GLM-5.2 Fast report removes any remaining ambiguity about the competitive control. It reports a 446 token/s peak on Artificial Analysis, a 2–3× range over Standard, and about 2× on the same-workload comparison Fireworks considers durable. More important than the headline number, the implementation independently maps the expert and attention paths: expert sharding trades residency against all-to-all traffic and narrow GEMMs, while data-parallel attention keeps compressed MLA KV local instead of replicating it across tensor-parallel ranks. Fireworks also reports a multi-tier agent-prefix cache, quality-gated lower precision, GLM-tuned speculation, and separate prefill/decode. Its public endpoints average roughly 90K prompt tokens, so these are production agent-serving decisions rather than a generic short-prompt benchmark. [Fireworks GLM-5.2 Fast](https://fireworks.ai/blog/glm-5p2-fast) (accessed 2026-07-12).

FireOptimizer is an even more direct overlap with the proposed experimentation company. Fireworks says it searches or adapts across hardware mapping, model quantization/tuning, and software request/cache/prefill-decode behavior. It reports that volume versus single-request configurations on the same eight GPUs can differ 4× in cost/token, and that a mismatched 29%-acceptance speculator made latency 1.5× worse while a workload-tuned 76%-acceptance speculator produced a 2× speedup. These are vendor examples rather than independently reproduced experiments, but they establish that automated cross-layer tuning from representative traces is already a product capability. [FireOptimizer](https://fireworks.ai/blog/fireoptimizer) (accessed 2026-07-12).

NVIDIA independently publishes a GLM-5.2 NVFP4 checkpoint for B200/B300 with SGLang and vLLM launch paths. Its card says routed-expert linear weights and activations are quantized while the shared expert remains higher precision. Against FP8, NVIDIA reports benchmark deltas from −0.81 to +0.86 points across GPQA Diamond, SciCode, IFBench, AA-LCR, and tau2-Bench Telecom. This is vendor evidence that selective expert quantization can preserve selected task scores; it is not our quality result or a measured serving-cost result. [NVIDIA GLM-5.2 NVFP4 card](https://huggingface.co/nvidia/GLM-5.2-NVFP4) (accessed 2026-07-12).

The machine-readable capture is [`glm-5.2-incumbent-stack-2026-07-12.json`](../validation/results/glm-5.2-incumbent-stack-2026-07-12.json).

**Thesis update:** full-stack per-model optimization and ordinary automatic deployment search are validated as important but falsified as unique moats. The surviving wedge is a co-design and validation system that reaches model-architecture or hardware changes beyond the already-custom incumbent stacks, or finds and validates useful changes materially faster than their internal systems before the model generation changes. A candidate must beat shared DSA + qualified NVFP4 + independent expert/attention mapping + FP8 KV + tiered prefix cache + KV-aware routing + P/D disaggregation + MTP under the same trace, quality, SLO, and fully loaded cost contract.

## The simulation and co-design category is already crowded

The fail-closed machine-readable [`competitive landscape`](../validation/results/inference-codesign-competitive-simulation-landscape-2026-07-12.json) binds 30 primary sources, 19 competitive entries, 32 source-scoped claims, 12 occupied layers, and five promotion/kill gates. All nine business claim permissions remain false; absence from public sources is not treated as proof that a competitor lacks a capability.

NVIDIA's May 2026 DynoSim release is the closest public match to the serving half of this project. It is a full-stack Rust discrete-event twin of Dynamo that composes backend-specific vLLM and SGLang scheduler behavior, measured or AIConfigurator-backed forward-pass timing, routing, planning, KV cache/offload, and workload replay on one clock. NVIDIA reports replaying a 23,608-request agent trace in 2.41 seconds on an Apple M4 MacBook Air, roughly 1,500× faster than real time. The public workflow explicitly supports configuration sweeps and autoresearch-style source changes to router, planner, and cache policies, with real-cluster validation as the outer loop. AIConfigurator separately searches aggregated/disaggregated layouts across TensorRT-LLM, vLLM, and SGLang using collected silicon data where available. These are incumbent claims and tools, but the code and documented surfaces are public enough to conclude that a fast Rust serving simulator is not a standalone moat. [NVIDIA DynoSim](https://developer.nvidia.com/blog/dynosim-simulating-the-pareto-frontier/), [DynoSim run documentation](https://github.com/ai-dynamo/dynamo/blob/main/docs/dynosim/runs.md), and [AIConfigurator](https://github.com/ai-dynamo/aiconfigurator) (accessed 2026-07-12).

The overlap extends below serving. NVIDIA's July 10 model-co-design guide tells model builders to change width/depth, align dimensions to 128/256/512 tiles, design layers for NVFP4, keep pipeline stages regular, and decouple attention from FFN parallelism. This is almost exactly the proposed “small architecture changes remove hardware inefficiency” thesis, published by the dominant hardware vendor. The novelty burden is therefore a measured discovery beyond those rules, not the observation that model shape affects inference. [NVIDIA hardware-friendly LLM design](https://developer.nvidia.com/blog/ai-model-co-design-hardware-friendly-llm-design/) (accessed 2026-07-12).

Etched is the direct capital-intensive comparison for the hardware half. Its current site says it co-designs chips, racks, software, packaging, cooling, interconnect, and manufacturing; has N4P A0 silicon; has run terabytes of production traffic patterns through its simulator; employs more than 400 engineers; has raised $800M; and is building against more than $1B in demand or contracts. Those are unverified company statements, not independent performance or economic evidence. They nevertheless show that the “simulator first, vertically integrated inference hardware later” category already has a heavily funded team with silicon and supply-chain execution. [Etched frontier inference clusters](https://www.etched.com/) (accessed 2026-07-12).

Open research infrastructure also covers much of the proposed breadth. ASTRA-sim describes plug-in end-to-end distributed-AI simulation across scheduling, collectives, compute, memory, and networks. Timeloop/Accelergy jointly explore workload mapping and accelerator architecture, energy, and area. LLMServingSim2.0 reports a trace-driven serving/hardware simulator with extensible accelerator profiles and sub-2% validation error on its tested GPU deployments. That reported error is a paper result, not reproduced here, and cannot be transferred to GLM or hypothetical hardware. Its existence still means “heterogeneous hardware plus serving simulation” is an established research category rather than empty space. [ASTRA-sim](https://github.com/astra-sim/astra-sim), [Timeloop/Accelergy](https://timeloop.csail.mit.edu/), and [LLMServingSim2.0 paper](https://arxiv.org/abs/2511.07229) (accessed 2026-07-12).

This changes the recommended company shape. Competing immediately as another serving provider or generic simulator is weak. The strongest surviving wedge is an independent, evidence-first co-design laboratory that can mutate model architecture and weights, generate the required executable kernel/hardware contract, and predict the *ranking and magnitude* of real quality/SLO/cost deltas across vendors. The first saleable asset would be validated discovery or IP, not silicon. Provider operation and tapeout become later consequences only if one intervention clears all of these gates:

1. A frozen task and safety suite establishes non-inferiority with adequate statistical power.
2. The simulator predicts the ordering and effect size of at least three unseen real-hardware interventions within a predeclared error bound.
3. One non-incumbent model or hardware change delivers at least 1.5× measured fully loaded cost improvement against the best same-hardware stack under the same agentic trace and SLO.
4. The result transfers to a second model or is large enough that model-specific revenue amortizes engineering before the checkpoint becomes obsolete.
5. Only then does a hardware design advance to synthesis/PPA; tapeout still requires contracted volume under pessimistic yield, schedule, lifetime, and price-decline assumptions.

MLPerf's open division provides one eventual independent path for retrained or substituted models, and its power protocol measures the complete system at the wall. AA-AgentPerf is a more workload-relevant public target for coding agents: it uses prerecorded trajectories with 5K–131K request lengths, tool-call delays, dynamic prefixes, and explicit TTFT/output-speed tiers, reporting concurrent agents per accelerator and per megawatt. Its test set is private and NVIDIA's results are vendor-reported, so this project may adopt only the public workload geometry and measurement principles. The checked [`public-agentic proxy`](../experiments/workloads/aa-agentperf-public-proxy-v1.json) now does exactly that: 64 synthetic requests across eight overlapping sessions with exact 5K/131K bounds, 27K mean input, 56 tool delays at a one-second median, dynamic prefixes, and synthetic class SLOs. It contains no private prompts, outputs, scoring, or performance and permits no AA, NVIDIA, provider, or cost claim. [MLPerf Inference submission guide](https://docs.mlcommons.org/inference/submission/), [MLPerf full-system power policy](https://mlcommons.org/benchmarks/inference-datacenter/), and [AA-AgentPerf methodology](https://developer.nvidia.com/blog/nvidia-achieves-leading-agentic-coding-performance-on-first-agentic-ai-benchmark/) (accessed 2026-07-12).

## First direct architecture-change verdict: technically valid is not economically material

The checked [`qwen3-0.6b-kv-head-dedup-quality-frontier-v1.json`](../validation/results/qwen3-0.6b-kv-head-dedup-quality-frontier-v1.json) is the first local experiment aimed squarely at the proposed moat rather than deployment tuning. It uses Qwen tensor values to choose K/V head pairs, replaces each selected pair with a shared mean, and exposes an exact alias table a custom kernel could use. Four pairs across four selected layers pass every declared teacher-forced gate on both 512 and 4,096 held-out targets. That candidate saves only 1.786% of semantic KV bytes and 0.176% of deployed weight bytes. If all decode time were KV traffic and aliasing were free, the impossible speed ceiling is 1.018×.

The frontier fails immediately beyond that point: five layer-pairs save 2.232% of KV bytes but fail logit RMSE and cosine; full per-layer 8→4 sharing saves 50% but raises mean NLL by 8.148 and leaves 0.78% top-1 agreement. The correct business decision is not to build the alias kernel. The primary literature treats head averaging as an initializer followed by training, not as a finished conversion; the source and recovery-budget dossier is [`qwen-kv-head-reduction-literature-2026-07-12.json`](../validation/results/qwen-kv-head-reduction-literature-2026-07-12.json).

The first separately sourced recovery test is also negative. [`qwen3-0.6b-kv-head-recovery-2k-v1.json`](../validation/results/qwen3-0.6b-kv-head-recovery-2k-v1.json) keeps the hard 8→4 pair means exact, freezes K/V, and trains 1.376M rank-8 Q/O adapter parameters. After 2,048 targets it recovers only 3.80% of the NLL gap; perplexity is still 2,535× baseline, cosine slightly worsens, and all five gates fail by wide margins. The projected 83-minute 8K continuation was therefore stopped. This rejects the exact hard-pair-mean plus frozen-K/V plus small-budget Q/O-only recipe, not all trained conversion. Activation-aware initialization, trainable shared K/V, gradual fusion, or literature-scale uptraining need a new early-promotion contract. Until one passes task quality and a real kernel measures bytes, the $/token claim remains false.

The selective-INT4 path now demonstrates the complementary kernel failure mode. The checked [`int4-packed-kernel-smoke-v1.json`](../experiments/qwen3-0.6b/int4-packed-kernel-smoke-v1.json) stores three exact layer-zero tensors in 6.29 MB instead of 16.78 MB and reproduces an independent QDQ reference exactly. Yet its single-thread scalar packed loop takes 5.300 ms versus 3.875 ms for the matched scalar f32-QDQ loop. The representation crosses a real storage boundary but not a performance boundary: group scales and nibble decode consume the apparent benefit.

The corrected [`int4-packed-batch-frontier-v1.json`](../experiments/qwen3-0.6b/int4-packed-batch-frontier-v1.json) closes the obvious amortization escape hatch. With identical row/tile/group/pair/lane traversal and equal work, packed remains 6.60%, 1.73%, 3.05%, and 2.04% slower at B=1, 4, 16, and 64. All 12 tensor×batch outputs match exactly. A provisional positive was discarded because its f32 control traversed weights differently; the corrected result is the only admissible frontier.

The next bounded experiment then tests architecture-specific code prospectively. The checked [`AArch64 NEON result`](../experiments/qwen3-0.6b/int4-aarch64-neon-v1.json) uses preallocated buffers, 31 alternating-order release samples, identical packed matrices and inputs, and an independent f32-QDQ control. It measures 1.064 ms NEON versus 4.741 ms scalar packed and 3.493 ms scalar f32-QDQ in summed medians: 4.457× and 3.284× local speedups. Maximum error is 5.25e−6 against the immutable 1e−3 gate. This reopens architecture-specific kernels as a technical lever, but not yet a business result: the comparison is one-thread batch-one scalar control work, no tuned BF16/Accelerate/vLLM, full model, energy, serving, or cost. The [locked 1.75× prediction](../validation/predictions/qwen3-0.6b-int4-aarch64-neon-v1.json) underestimates the measured time reduction badly, producing 44.7% relative effect error. The business implication is dual: abstraction removal can matter at a component boundary, while current performance prediction is still unreliable.

The quality bridge has now crossed one real task boundary without closing it. The checked [`exact-source PIQA-256 result`](../validation/results/qwen3-0.6b-int4-o-gate-up-piqa256-bf16scale-v1.json) materializes the runtime representation's BF16-stored scales into BF16 model weights and preserves the pinned official source strings exactly. Accuracy changes from 67.97% to 68.36%, passing the predeclared maximum two-point loss gate. Seven examples move candidate-only correct and six baseline-only correct; exact McNemar is 1.0. The 95% paired-bootstrap interval nevertheless permits a 2.34-point loss, beyond the two-point margin, so confirmatory non-inferiority is inconclusive. Full PIQA, decontamination, agent tasks, safety, packed full-model execution, serving, energy, and cost remain open. The preceding task artifact is withdrawn and must not be cited: source fidelity is now an explicit validation requirement.

The GLM controls make the same business lesson at the serving layer. At exact 16K context, independent DP-attention/local-EP8 mapping cuts modeled hop bytes 85.86%, yet coupled TP16 robustly wins partial residency through concurrency 32. The checked context frontier moves the strict decoupled threshold from C43 at 16K to C22, C11, C9, C6, C4, C3, and C2 at 32K, 65K, 90K, 131K, 262K, 524K, and 1M. Full candidate capacity remains uncertain through 262K because the public checkpoint’s non-routed layout is opaque, so this is a search filter rather than a deployable policy. Likewise, neutral P/D costs 5.18% more than aggregate in the fixed-budget event model; the 35.22% upside requires explicit interference/specialization inputs and can disappear under full congested KV transfer. This is evidence that the engine is finding policy boundaries. It is not evidence that the company is cheaper than a provider.

## Robustness frontier: the optimistic BF16 pass does not survive modest realism

The checked [`economic-robustness-frontier-v1.json`](../experiments/glm-5.2/economic-robustness-frontier-v1.json) evaluates 4,374 deterministic points across two public price surfaces, three workload mixes, three useful-load factors, three availability factors, three accelerator prices, three required margins, three source-throughput haircuts, and three input-work bounds. It produces 54 grouped regions and keeps provider, cost, and viability claims false.

| Frontier result | Count |
|---|---:|
| Below required margin | 3,104 / 4,374 |
| Clears margin but not the configured 1.25× headroom | 354 / 4,374 |
| Clears the configured headroom at an individual point | 916 / 4,374 |
| Regions robust across the full cost/load/availability/margin sweep | **0 / 54** |

The working Fireworks-price, cache-heavy mix, $7/device-hour, 60%-margin, 65%-load, 98%-availability case exposes the fragility directly:

| Source capacity and work case | Headroom | Result |
|---|---:|---|
| 100% of optimistic peak, input work free | 1.0805× | Clears required margin but misses 1.25× robustness threshold |
| 75% of optimistic peak, input work free | 0.8104× | Fails required margin |
| 100% of optimistic peak, modest input work | 0.8244× | Fails required margin |
| 75% of optimistic peak, modest input work | 0.6183× | Fails required margin |

At the single optimistic/free-input point, the system needs at least 92.55% of the modeled source peak, a maximum public accelerator price of $7.56/device-hour, and average work no higher than 0.06984 output-equivalent units per billable token. The free-input mix already consumes 0.06463, leaving little room for actual prefill. This is a sensitivity result over an uncalibrated BF16 20-H200 source with perfect rank scaling; it does not compare against Fireworks Fast, Baseten's stack, or public NVFP4. Its valid conclusion is narrower: the earlier non-rejection is too fragile to underwrite the business.

## Strategic wedge options after the incumbent-stack finding

| Business path | Buyer and value | Evidence required before selling | Principal risk | Current decision |
|---|---|---|---|---|
| Head-on token API | Agent companies buy a cheaper/faster GLM-compatible endpoint | Same-trace quality, tails, failures, aggregate goodput, and fully loaded cost below the best provider quote | Baseten and Fireworks already have optimized fleets, distribution, reliability, and price parity | Do not lead here until a robust frontier clears |
| Managed model optimization | Model owners and large dedicated customers pay for a qualified per-model stack | Reproducible intervention deltas, task non-inferiority, deployment handoff, and savings on their traffic | Services can become non-repeatable consulting | Best initial commercial wedge if experiments become predictive |
| Co-design research platform | Model labs, inference providers, and accelerator teams buy faster architecture/kernel/hardware search | Simulator ranks real candidates correctly across at least two models and exposes uncertainty honestly | Long enterprise sales and customers may build internally | Best candidate for durable company IP |
| Optimization IP/runtime licensing | Providers license a model patch, kernel set, or serving policy | A beyond-incumbent intervention with portable measured value and maintainable integration | Incumbents can copy uncopyrightable mechanisms or negotiate away margin | Pursue only for measured discontinuities |
| Model-family accelerator | Large contracted buyers purchase capacity optimized for an architecture family | PPA, package, yield, compiler, reliability, volume, model lifetime, and a launch-date residual advantage | NRE, schedule, supply chain, and model obsolescence | Deferred; current tapeout decision is NO-GO |

The recommended sequence is:

1. Build the simulator as an evidence product and use managed optimization engagements to obtain real, privacy-safe workload distributions and hardware calibration.
2. Require the engine to predict measured deltas and regressions before trusting its economic frontier.
3. Deploy an owned API only for model/workload regions where the same engine shows a robust cost advantage after incumbent-stack, utilization, SLO, and failure stress.
4. Reuse successful mechanisms across a second architecture. A one-model win may be consulting or temporary arbitrage; a repeatable search loop is a company.
5. Consider hardware only after contracted demand and a pessimistic model-lifetime case repay NRE.

**Moat hypothesis:** software generation cost falling toward zero makes implementation faster for everyone, including incumbents. The defensible asset is therefore the closed loop of representative traces, quality contracts, calibrated measurements, causal intervention history, search policy, and deployment feedback. This loop must find valuable changes faster than a Baseten, Fireworks, NVIDIA, or model-owner team can reproduce them. Code volume is not evidence of that moat.

The engine now enforces one consequence mechanically: a Qwen weight-byte estimate, Qwen component-kernel timing, GLM network-byte reduction, synthetic P/D cost delta, and analytical hardware/economic frontier cannot be multiplied into a “full-stack” saving. A cost claim requires an exact joint measured end-to-end artifact under the same model revision, workload, quality contract, SLO, baseline stack, candidate stack, and intervention set. The current request finds none. This guardrail is part of the product value: it prevents search throughput from becoming claim inflation.

### Near-term business falsification gates

These thresholds apply at different promotion stages. A small-proxy mechanism needs at least 20% paired cost reduction to justify a larger-model test. Joint commodity co-design requires at least 30% lower output cost and 20% lower input cost on two model families. The provider-launch proof uses at least 1.5× lower fully loaded cost under the full SLO contract. Silicon authorization is later and retains the stricter 4× base/2× pessimistic launch hurdle.

| Gate | Pass condition | Failure meaning |
|---|---|---|
| Predictive validity | At least three measured intervention deltas across two context regimes within 15%, rank correlation at least 0.8, and one predicted regression | The simulator is a storytelling tool, not a research engine |
| Beyond-incumbent GLM result | A quality- and SLO-controlled gain beyond qualified NVFP4, FP8 KV, KV routing, P/D, and MTP | The GLM provider wedge is already captured by incumbents |
| Economic robustness | At least 1.25× headroom at 20% below the best real quote and 60% gross margin under downside utilization, failure, and work assumptions | The apparent saving is too fragile to finance a provider |
| Cross-model transfer | At least 1.5× measured fully loaded cost reduction on two materially different architectures | The process is a one-off optimization service, not a scalable platform |
| Customer pull | Paid design partner or credible LOI provides a frozen workload/eval contract and accepts the measurement method | The technical result lacks a buyer or usable data loop |
| Silicon authorization | Contracted volume plus independent PPA/cost evidence clears at least 4× base and 2× joint-pessimistic launch advantage | Do not tape out |

Current predictive-validity status is **`NOT_MET`**: one prospective component pair is admissible, its direction is correct, and its effect-size error is 44.7%. Rank correlation is unavailable; three interventions, two regimes, and one predicted regression remain missing. A real pair is progress, not evidence that the simulator passes.

## Evidence labels

This document uses four labels deliberately:

- **Fact:** directly stated in a cited primary source or read from a checked-in artifact.
- **Derived:** arithmetic from facts and explicitly listed assumptions.
- **Modeled assumption:** a value chosen for sensitivity analysis, not observed data.
- **Inference:** a business conclusion that could be wrong and has a proposed falsification test.

Public API price is not provider cost. No public source below reveals Fireworks or Baseten COGS, negotiated enterprise discounts, fleet utilization, hardware purchase price, or gross margin. The calculations therefore determine what this business must achieve; they do not estimate a competitor's profit.

## Current competitive price surface

### GLM 5.2 token pricing

All values are public list prices in USD per million tokens as displayed on 2026-07-12.

| Provider and path | Input | Cached input | Output | Availability evidence |
|---|---:|---:|---:|---|
| Fireworks Standard | $1.40 | $0.14 | $4.40 | Model page says Serverless, On-demand, and fine-tuning are supported |
| Fireworks Priority | $1.75 | $0.18 | $5.50 | Pricing table lists Priority for this model |
| Fireworks Fast | $2.10 | $0.21 | $6.60 | Separate Fast model path |
| Baseten Model API | $1.40 | $0.26 | $4.40 | Listed Model API; product page advertises transition to dedicated deployment |
| Z.AI pay-as-you-go API | $1.40 | $0.26 | $4.40 | Model-owner API; cached-input storage is marked limited-time free |

Sources: [Fireworks serverless price table](https://docs.fireworks.ai/serverless/pricing), [Fireworks GLM 5.2 model page](https://fireworks.ai/models/fireworks/glm-5p2), [Baseten price table](https://www.baseten.co/pricing/), [Baseten Model APIs](https://www.baseten.co/products/model-apis/), and [Z.AI price table](https://docs.z.ai/guides/overview/pricing) (accessed 2026-07-12).

Important caveats:

- **Fact:** Fireworks bills input, cached input, and generated tokens separately. Batch inference is 50% of Standard Serverless input and output rates. Spend tier affects Serverless capacity caps. [Fireworks Serverless overview](https://docs.fireworks.ai/serverless/overview) and [pricing](https://docs.fireworks.ai/serverless/pricing) (accessed 2026-07-12).
- **Fact:** Fireworks' GLM 5.2 cached-input price is 10% of uncached input, lower than its general statement that cached input defaults to 50% unless specified otherwise. The model-specific row is the relevant benchmark.
- **Fact:** Baseten introduced discounted cached-input pricing for Model APIs in April 2026 and says it is automatic except for GPT-OSS. [Baseten cache-token pricing announcement](https://www.baseten.co/resources/changelog/cache-token-pricing-for-model-apis/) (accessed 2026-07-12).
- **Fact:** Baseten advertises volume discounts on dedicated compute. Fireworks invites enterprise customers to contact sales for lower costs and offers reserved capacity. Neither publishes the resulting contract price. [Baseten pricing](https://www.baseten.co/pricing/), [Fireworks pricing](https://fireworks.ai/pricing), [Fireworks inference](https://fireworks.ai/inference) (accessed 2026-07-12).
- **Inference:** Baseten and Z.AI's exact price parity may reflect channel positioning, but public evidence does not reveal a commercial agreement, transfer price, or either provider's cost. It must not be used to infer margin.
- **Derived:** Fireworks charges 25% above Standard for GLM 5.2 Priority and 50% above Standard for Fast on uncached input and output. Even though this study optimizes cost, the public price surface shows that speed and reliability can carry a premium; cost search must remain constrained by a saleable SLO.
- **Inference:** Public list price is an optimistic competitive benchmark for the entrant, not a conservative one. Procurement tests must also sweep incumbent discounts and the 50%-priced Fireworks batch path where latency permits.

### Dedicated deployment pricing

| Provider | Device | Public billing | Derived hourly price |
|---|---|---:|---:|
| Fireworks | H100 80 GB | $7.00/GPU-hour | $7.00 |
| Fireworks | H200 141 GB | $7.00/GPU-hour | $7.00 |
| Fireworks | B200 180 GB | $10.00/GPU-hour | $10.00 |
| Fireworks | B300 288 GB | $12.00/GPU-hour | $12.00 |
| Baseten | L4 24 GB | $0.01414/min | $0.8484 |
| Baseten | A100 80 GB | $0.06667/min | $4.0002 |
| Baseten | H100 MIG 40 GB | $0.06250/min | $3.7500 |
| Baseten | H100 80 GB | $0.10833/min | $6.4998 |
| Baseten | B200 180 GB | $0.16633/min | $9.9798 |

Sources: [Fireworks pricing](https://fireworks.ai/pricing) and [Baseten pricing](https://www.baseten.co/pricing/) (accessed 2026-07-12). Baseten hourly values are minute price multiplied by 60.

**Derived:** Fireworks' H100 list rate is only 7.7% above Baseten's converted rate, and their B200 rates differ by about 0.2%. There is little public-rate hardware resale arbitrage; a new provider needs higher useful goodput, lower owned cost, differentiated service, or negotiated supply.

Billing behavior matters as much as the nominal hourly rate:

- **Fact:** Fireworks says On-demand is billed per GPU second with no extra startup charge.
- **Fact:** Baseten bills by the minute while a replica is deploying, scaling, or serving. Scale-to-zero incurs no replica charge while at zero, but wake-up is billed and can take minutes for large models. Baseten recommends at least two warm replicas for production redundancy. [Baseten autoscaling](https://docs.baseten.co/deployment/autoscaling/overview) and [cold starts](https://docs.baseten.co/deployment/autoscaling/cold-starts) (accessed 2026-07-12).
- **Fact:** Baseten's default target utilization is 70%; it recommends initial LLM concurrency targets of 32–128 for vLLM and 32 for SGLang. Higher concurrency reduces replica cost but raises queueing latency. [Baseten autoscaling](https://docs.baseten.co/deployment/autoscaling/overview) (accessed 2026-07-12).
- **Inference:** An entrant must compare against each provider's best economic mode for the customer's traffic: serverless for intermittent demand, warm dedicated replicas for latency-sensitive steady demand, reserved capacity for contracted volume, and batch for delay-tolerant work.

### Model availability and the small-model baseline

- **Fact:** Fireworks' GLM 5.2 page lists Serverless, On-demand, function calling, and LoRA fine-tuning, with 1,040K context. [Fireworks GLM 5.2](https://fireworks.ai/models/fireworks/glm-5p2) (accessed 2026-07-12).
- **Fact:** Baseten lists GLM 5.2 as a Model API and says Model APIs can be moved to dedicated deployments. Its general platform supports open and custom models through Truss. [Baseten Model APIs](https://www.baseten.co/products/model-apis/) and [pricing FAQ](https://www.baseten.co/pricing/) (accessed 2026-07-12).
- **Fact:** Model owner Z.AI lists GLM 5.2 on its pay-as-you-go API at the same uncached input, cached input, and output price as Baseten. This direct channel is an additional price and quality baseline even though the target competitors are Fireworks and Baseten. [Z.AI pricing](https://docs.z.ai/guides/overview/pricing) (accessed 2026-07-12).
- **Fact:** Fireworks lists Qwen3 8B as ready for On-demand and fine-tuning but explicitly marks Serverless unsupported. This means the current Qwen3-8B study should compare to a dedicated hourly deployment, not invent a Fireworks per-token baseline. [Fireworks Qwen3 8B](https://fireworks.ai/models/fireworks/qwen3-8b) (accessed 2026-07-12).
- **Fact:** Baseten's public Model API price table does not list Qwen3 8B text generation on the captured date, while its general dedicated product can deploy custom open models. Absence from a public table is not evidence that sales cannot offer it.

## What customers are buying beyond tokens

The business cannot win a durable provider contract on arithmetic cost alone.

| Requirement | Public incumbent position | Evidence status |
|---|---|---|
| API compatibility | Fireworks states OpenAI and Anthropic compatibility | Product claim |
| Performance | Fireworks claims up to 4x higher throughput; Baseten calls its pre-optimized Model APIs ultra-fast | Marketing claims without a reproducible workload in the cited pages |
| Dedicated and reserved capacity | Fireworks offers On-demand and Reserved Capacity; Baseten offers dedicated and reserved-capacity contact paths | Product fact |
| Autoscaling | Both expose scaling products; Baseten documents scale-to-zero and control behavior | Documented behavior |
| Cold-start behavior | Fireworks advertises no cold starts for shared Serverless; Baseten documents scale-to-zero wake-up and warm-replica controls | Product claim and documented control behavior |
| Cache economics | Both discount cached input; Fireworks supports session affinity | Documented behavior |
| Reliability | Baseten claims four nines for Model APIs; Fireworks describes dedicated reliability, while its general model docs call shared Serverless best-effort without an SLA | Vendor claims, not independently measured here |
| Custom models | Both support dedicated custom/open models | Product fact |
| Tool use and structured output | Both market production support | Product claim requiring conformance tests |
| Operations | Routing, observability, rollout, quota management, security, support, and failure recovery are bundled into provider price | Scope inference |

Sources: [Fireworks inference](https://fireworks.ai/inference), [Fireworks model overview](https://docs.fireworks.ai/models/overview), [Fireworks Serverless overview](https://docs.fireworks.ai/serverless/overview), [Baseten Model APIs](https://www.baseten.co/products/model-apis/), [Baseten deployment concepts](https://docs.baseten.co/deployment/concepts), and [Baseten environments](https://docs.baseten.co/deployment/environments) (accessed 2026-07-12).

**Inference:** A benchmark that excludes routing, failed requests, warm capacity, rollout overlap, spare capacity, observability, abuse controls, and support is comparing a kernel to a product. The simulation must account for the product envelope before its result is business evidence.

## The agentic workload changes the price floor

The repository's canonical workload is explicitly synthetic, not observed Claude Agent SDK or customer traffic. Its class-weighted average request is:

| Quantity | Tokens/request |
|---|---:|
| Input | 16,486.4 |
| Assumed cached input | 14,385.152 |
| Uncached input | 2,101.248 |
| Output | 1,139.2 |
| Total billable | 17,625.6 |

The implied input:output ratio is 14.47:1 and the input-token cache hit ratio is 87.25%.

At public GLM 5.2 prices:

| Case | USD/request | USD/M total billable tokens |
|---|---:|---:|
| No input cache discount, $1.40 input and $4.40 output | $0.02809 | $1.59390 |
| Fireworks Standard with modeled cache hits | $0.009968 | $0.56555 |
| Baseten Model API with modeled cache hits | $0.011694 | $0.66349 |

These are **derived** from list price and the synthetic mix. They are not measured customer bills.

The modeled Fireworks bill is 64.5% lower than the no-cache case. This creates two business consequences:

1. Cache behavior is a first-order economic variable. An inaccurate hit-rate or eviction model can overwhelm a kernel-level gain.
2. Cached-input economics are harsh. Fireworks charges $0.14/M cached input on GLM 5.2, so an entrant discounting list price while keeping margin has only cents per million cached tokens to pay for cache memory, transfer, routing, misses, and failures.

The immediate evidence task is to replace the synthetic mix with privacy-safe measured distributions for prefix identity, cacheable spans, inter-turn delay, context length, output length, concurrency, tool latency, cancellation, retry, and failure. Average tokens alone are not sufficient.

Fireworks' GLM-5.2 report says its public endpoint prompts average roughly 90K tokens, 5.46× the older synthetic mix's 16,486-token average input. That vendor aggregate is not a distribution and cannot replace a trace. The new public-agentic proxy instead spans 5K–131K tokens with a 27K mean and maps every exact token geometry through the residency model, while deliberately excluding tokenizer equivalence, output work, arrivals, prefix behavior, tool timing, SLOs, and performance. A privacy-safe measured trace with prefix reuse is still required; otherwise DSA scan, cache capacity, prefill, transfer, and TTFT remain structurally uncalibrated.

## Break-even model

For a serving system with fully loaded cost `H` dollars/hour, active full-load SLO-compliant capacity `Q` billable tokens/s, useful load factor `U`, and availability `A`:

```text
COGS_per_million = 1,000,000 × H / (3,600 × Q × U × A)
Q_required = 1,000,000 × H / (3,600 × U × A × COGS_ceiling_per_million)
```

`H` must include annualized accelerator, HBM, package, board, host, storage, rack, networking, power delivery, cooling, facilities, spares, failed hardware, operations, and support. Model-specific engineering and silicon NRE are shown separately so accounting gross margin is not confused with fully loaded economic return.

`Q` must count only successfully billed tokens that meet the fixed SLO and quality contract. It must not count rejected requests, retries, speculative tokens that are discarded, warm-up work, cache-transfer bytes, or output generated after client cancellation.

### Price and gross-margin ceiling

Using the cache-aware Fireworks mix price of $0.56555/M total tokens:

| Customer discount from list | Target gross margin | Maximum infrastructure COGS/M total tokens |
|---:|---:|---:|
| 0% | 50% | $0.2828 |
| 0% | 60% | $0.2262 |
| 0% | 70% | $0.1697 |
| 20% | 50% | $0.2262 |
| 20% | 60% | $0.1810 |
| 20% | 70% | $0.1357 |

The working business gate is 20% below list at 60% gross margin. At that gate:

| Billing dimension | Entrant price/M | Maximum COGS/M | Required token/s per $1/hour system cost |
|---|---:|---:|---:|
| Uncached input | $1.12 | $0.4480 | 973 |
| Cached input | $0.112 | $0.0448 | 9,734 |
| Output | $3.52 | $1.4080 | 310 |
| Canonical combined mix | $0.4524 total-token equivalent | $0.1810 | 2,410 |

Assumptions: 65% useful load and 98% availability. The dimension rows are independent allocation views; they cannot be added. The combined row is the relevant system gate when the exact mix is replayed.

### Throughput required by serving-system hourly cost

| Fully loaded serving-system cost | Required billable total token/s |
|---:|---:|
| $10/hour | 24,096 |
| $20/hour | 48,191 |
| $25/hour | 60,239 |
| $50/hour | 120,478 |
| $56/hour | 134,935 |
| $80/hour | 192,765 |
| $100/hour | 240,956 |

The $56/hour row is an illustrative eight-H200 Fireworks On-demand replica at public list price. The $80/hour row is eight Fireworks B200s and is close to Baseten's derived $79.84/hour for eight B200s. [NVIDIA's NVFP4 card](https://huggingface.co/nvidia/GLM-5.2-NVFP4/tree/aec724e8c7b8ee9db3b48c01c320f63f9cdaf8aa) uses an eight-way launch path on Blackwell, but none of these rows claims a measured GLM topology or what Fireworks uses for its Serverless endpoint.

For comparison, the same $56/hour system needs:

| Commercial target | Required billable total token/s |
|---|---:|
| Price parity, zero margin | 43,179 |
| Price parity, 50% margin | 86,359 |
| Price parity, 60% margin | 107,948 |
| 20% discount, 60% margin | 134,935 |
| 40% discount, 60% margin | 179,914 |

**Inference:** A rented-hardware result that merely breaks even at public list price is not enough. It must survive margin, useful-load, private-discount, and batch-price stress.

Useful load and failures are multiplicative. For the $56/hour case at the working commercial gate:

| Useful load | Availability | Required billable total token/s |
|---:|---:|---:|
| 40% | 95.0% | 226,194 |
| 50% | 98.0% | 175,416 |
| 65% | 98.0% | 134,935 |
| 80% | 99.5% | 107,982 |

The useful-load factor must be measured after SLO headroom, diurnal idleness, fragmentation between prefill and decode, and model-specific stranded capacity. Availability must include failed requests and recovery time, not only machine uptime.

### An illustrative owned/custom lane

This scenario is deliberately transparent and should be replaced with quotes. It is not a silicon cost estimate.

| Assumption per accelerator lane | Value |
|---|---:|
| Installed accelerator, HBM, package, board, host, network, and rack capex | $60,000 |
| Economic life | 3 years |
| Cost of capital | 10% |
| Annualized capex | $2.754/hour |
| Spare and failure reserve | 10% of annualized capex, $0.275/hour |
| Average IT power | 0.6 kW |
| PUE and electricity | 1.2 and $0.12/kWh |
| Power | $0.086/hour |
| Facility and colocation | $0.20/hour |
| Network fabric and transit | $0.15/hour |
| Operations and support | $0.15/hour |
| Fully loaded lane before NRE | $3.616/hour |

This produces:

| Topology | Cost before NRE | Required canonical billable token/s |
|---|---:|---:|
| 8 lanes | $28.93/hour | 69,704 |
| 16 lanes | $57.86/hour | 139,409 |

Every input in this table must be swept. A design that wins only with $60K installed cost, three full years, or 65% useful load is not validated.

### Power is not the main dollar lever at current rental prices

**Fact:** NVIDIA specifies H200 SXM at up to 700W, 141GB HBM3e, and 4.8TB/s HBM bandwidth. [NVIDIA H200](https://www.nvidia.com/en-us/data-center/h200/) (accessed 2026-07-12).

**Derived:** Eight H200 GPUs at maximum TDP consume 5.6kW before hosts and networking. At 1.2 PUE and $0.12/kWh that is $0.806/hour. Against $56/hour of public Fireworks GPU rental, GPU energy is about 1.4% of rental price. Even halving GPU energy saves only $0.403/hour before any cooling or host effect.

**Fact:** EIA's preliminary 2026 year-to-April national average was 13.85 cents/kWh for commercial customers and 8.87 cents/kWh for industrial customers. Location and negotiated supply can differ materially. [EIA Electric Power Monthly table 5.3](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=table_5_03) (accessed 2026-07-12).

**Inference:** Energy efficiency is operationally important, but the economic thesis cannot rest on watts alone. The larger levers are fewer devices, cheaper HBM/package/server capital, higher SLO-compliant useful throughput, and less stranded capacity.

## Engineering and silicon amortization

Accounting gross margin normally excludes R&D. Investment return does not. The business should report both infrastructure COGS and fully loaded cost after allocated model, compiler, kernel, simulator, validation, and silicon engineering.

At the 20%-discount, 60%-margin gate, total infrastructure COGS may not exceed $0.1810/M on the canonical mix. If measured infrastructure consumes $0.10/M, only $0.08098/M remains for model-specific NRE.

| Model-specific NRE | Required lifetime tokens | Average token/s | Average request/s | Annual revenue |
|---:|---:|---:|---:|---:|
| $25M | 0.309 quadrillion | 3.26M | 185 | $46.6M |
| $100M | 1.235 quadrillion | 13.05M | 741 | $186.2M |
| $300M | 3.705 quadrillion | 39.16M | 2,222 | $558.7M |

Requests use the synthetic 17,625.6-token average and revenue uses the 20%-discounted list price. These volumes assume every token earns that modeled mix price, all three years are saleable, infrastructure remains at $0.10/M, and no additional corporate operating expense is allocated. They are therefore optimistic.

The current hardware-sizing configuration contains a **$300M NRE assumption amortized over 100,000 devices**. That is $3,000 NRE per device, but it silently requires 100,000 useful device sales or deployments for one model-specific design. At 16 devices per serving replica, that represents 6,250 replicas. The simulator must replace unit amortization with dated demand, deployment, and token-volume scenarios before its silicon economics can support an investment claim.

Required NRE analysis:

- 12-, 24-, and 36-month model life.
- 10%, 30%, and 50% incumbent price decline per year.
- Pre-production engineering, masks, EDA/IP, verification, emulation, prototype, package, qualification, respins, and production software.
- Yield distribution rather than one point estimate.
- Committed versus forecast device volume.
- Financing and working capital from tape-out to revenue.
- Inventory write-down if a model revision invalidates the mapping.
- Reuse credit only for blocks demonstrably reusable on the next model.

**Inference:** Per-model silicon is only rational with contracted volume or a reusable substrate whose model-specific portion is cheap to change. Otherwise a rapidly improving commodity accelerator and software stack can erase the advantage before NRE is recovered.

## GLM 5.2-specific opportunity and warning

### Architecture facts

- **Fact:** The official Hugging Face repository reports 753B parameters for GLM 5.2 and provides an FP8 checkpoint under an MIT license. Its configuration identifies 78 layers, hidden size 6,144, 256 routed experts, and eight experts selected per token. [Pinned GLM-5.2-FP8 checkpoint](https://huggingface.co/zai-org/GLM-5.2-FP8/tree/ba978f7d347eaf65d22f1a86833408afdb953541) and [pinned configuration](https://huggingface.co/zai-org/GLM-5.2-FP8/blob/ba978f7d347eaf65d22f1a86833408afdb953541/config.json) (accessed 2026-07-12).
- **Fact:** Fireworks' model metadata says 743B parameters. The 10B discrepancy is unresolved and must not be papered over; exact checkpoint files and config hashes must define any experiment. [Fireworks GLM 5.2](https://fireworks.ai/models/fireworks/glm-5p2) (accessed 2026-07-12).
- **Fact:** Z.AI says IndexShare reuses one sparse-attention indexer across four layers. Its FP8 model card claims 2.9x lower indexer-related per-token FLOPs at 1M context, and its improved multi-token-prediction layer increased measured acceptance length by up to 20% in the reported ablation. [Z.AI GLM 5.2 article](https://z.ai/blog/glm-5.2) and [pinned model card](https://huggingface.co/zai-org/GLM-5.2-FP8/blob/ba978f7d347eaf65d22f1a86833408afdb953541/README.md) (accessed 2026-07-12).
- **Fact:** Z.AI explicitly says the lower per-token FLOPs do not proportionally reduce KV-cache size. It identifies KV capacity, context-dependent kernel overhead, cache transfer, CPU cache management, scheduling, and GPU bubbles as central 1M-context serving problems. [Z.AI GLM 5.2 article](https://z.ai/blog/glm-5.2) (accessed 2026-07-12).
- **Fact:** NVIDIA publishes a model-specific NVFP4 checkpoint occupying 464,865,454,030 repository bytes. Its card says only linear weights and activations inside routed MoE experts are converted to NVFP4, leaving the shared expert unquantized. It provides eight-way vLLM and SGLang launch paths and reports close FP8/NVFP4 scores on five selected evaluations. Those are vendor measurements, not this project's agent-task quality proof. [Pinned NVIDIA GLM-5.2-NVFP4](https://huggingface.co/nvidia/GLM-5.2-NVFP4/tree/aec724e8c7b8ee9db3b48c01c320f63f9cdaf8aa) (accessed 2026-07-12).

### Capacity arithmetic

The FP8 checkpoint's raw parameter payload is approximately 753GB before scales, metadata, non-parameter buffers, KV, activations, fragmentation, and runtime headroom.

- Eight H100 80GB devices provide 640GB aggregate HBM, so the raw FP8 weights alone do not fit.
- Eight H200 141GB devices provide 1,128GB aggregate HBM, leaving roughly 375GB before runtime overhead.
- A BF16 copy is roughly 1.506TB before overhead and does not fit in eight H200s.
- NVIDIA's 464.9GB NVFP4 repository payload is smaller than eight H100s' aggregate 640GB, but the model card lists Blackwell as the supported microarchitecture. Repository bytes are also not resident bytes. The arithmetic neither establishes H100 execution nor proves that runtime state, workspaces, and target KV concurrency fit.

This is **derived capacity arithmetic**, not a validated deployment topology. Expert offload, quantization, disaggregation, replicated layers, and parallelism change both capacity and throughput. NVIDIA device capacities come from [H100](https://www.nvidia.com/en-in/data-center/h100/) and [H200](https://www.nvidia.com/en-us/data-center/h200/) product specifications (accessed 2026-07-12).

### Highest-value hypotheses

GLM 5.2 is a stronger co-design target than a generic dense 8B model because its producer has already named the cross-layer bottlenecks. It is also a harder target because the producer, framework teams, NVIDIA, and incumbent providers are already optimizing them. The competitive baseline must include selective expert NVFP4; whole-model FP8 versus an invented INT4 candidate is no longer sufficient.

The first GLM-specific simulation campaign should rank:

1. **KV and index-cache hierarchy:** HBM, host DRAM, local SSD, and remote cache placement with real reuse distance, transfer contention, and miss penalties.
2. **IndexShare mapping:** persistent indices, four-layer reuse, SRAM sizing, index transfer, and sparse-attention kernel scheduling.
3. **Prefill/decode disaggregation:** compute/HBM asymmetry, cache transfer, network topology, admission, and failure recovery under the canonical trace.
4. **MTP hardware balance:** seven-step draft execution, workload-specific acceptance distribution, verification cost, rejected-token energy, and quality equivalence.
5. **Expert placement:** hot-expert replication, expert-parallel links, routing skew, topology congestion, and failover.
6. **Quantization by tensor role:** expert weights, shared/dense layers, attention projections, KV, and index state must each have independent quality evidence and storage metadata.
7. **CPU control plane:** scheduling, cache bookkeeping, tokenization, request parking, and launch bubbles must be simulated or measured rather than treated as free.
8. **Model changes:** KV representation, sparse-index architecture, MTP training target, and expert structure should be changed only with a trained checkpoint and fixed agent-task non-inferiority gate.

**Inference:** The most defensible hardware is likely memory-, interconnect-, and control-plane shaped, not simply a larger matrix engine. Z.AI's own description makes that falsifiable: action-level simulation should show whether HBM capacity/bandwidth, cache-transfer network, or compute dominates each workload region.

## First capacity-timing business screen

The checked [`h200-optimistic-deployment-screen-v1.json`](../experiments/glm-5.2/h200-optimistic-deployment-screen-v1.json) connects three previously separate artifacts: BF16 residency on 20 public-price H200s, the whole-decode lower-work ledger, and the commercial hurdle above. It is deliberately biased toward passing:

- It uses the lower work bound, including only exact FFN work and minimum routed-expert reads.
- It uses published peak H200 component rates rather than sustained measurements.
- It multiplies one modeled component's throughput linearly across all 20 ranks.
- It converts each output token into 15.472 total billable tokens while treating every input-prefill token as free work.
- It ignores contention, queueing, failures inside a request, and SLO loss.

Even under those assumptions, the peak bound is **364,505 billable token/s** against a required **337,338 token/s**, only **1.0805× headroom**. A 7.45% loss from the impossible bound erases the margin. The screen therefore cannot reject the candidate, but it also cannot support viability: every business, cost, and provider-comparison claim remains false in the artifact.

This is a useful decision boundary. BF16 on public-price H200s is too fragile to be the business case. Input-prefill work alone is likely to consume more than the remaining margin, before irregular gather efficiency, expert imbalance, communication, or tails. The next admissible screen must quantify whether public expert-selective NVFP4 or another quality-qualified representation reduces per-rank active bytes enough to create robust headroom. Because NVIDIA already publishes NVFP4, that becomes the incumbent rather than proprietary evidence.

## Business proof plan

### Gate 1: simulator credibility

Current state: **one admitted pair, predictive gate still failed**. The checked evaluator requires a blinded prediction to be locked before measurement, globally disjoint calibration and holdout cases, exact model/workload/hardware/software/intervention/metric identity, real artifact-byte plus in-file scope/value/content verification, and exact quality/SLO evidence before cost promotion.

Pass only if:

- Predicted intervention deltas are within 15% of measured deltas on at least three mechanisms and two context regimes.
- Candidate rank correlation is at least 0.8 against measured ordering.
- Confidence intervals cover measurement across repeat runs.
- The simulator predicts a known regression, not only wins.
- Every result is reproducible from checkpoint, engine, hardware, trace, and artifact hashes.

Until this passes, use the system to prioritize experiments, not to make cost claims.

### Gate 2: commodity-hardware product advantage

Replay the same request arrivals and tokenized prompts against tuned current vLLM, SGLang, TensorRT-LLM where supported, Fireworks, Baseten, and the candidate.

Pass only if the candidate:

- Preserves the fixed task-quality and safety contract.
- Delivers at least 1.5x measured fully loaded cost reduction against the best same-hardware software baseline.
- Meets p95 and p99 TTFT/TPOT plus goodput under failures and bursts.
- Supports the same cache accounting and bills only successful, SLO-compliant work.
- Reaches 20% below the best available provider quote at 60% target gross margin in the base case.
- Remains viable at 40% incumbent discount, 20% lower utilization, 2x failure reserve, and 30% annual incumbent improvement.

### Gate 3: transfer

Retain at least 1.5x measured gain on a second architecture. Otherwise this is a one-model optimization project, not a platform.

### Gate 4: silicon authorization

Do not authorize tape-out until:

- A cycle- and traffic-aware hardware model has been calibrated against FPGA/emulation or a sufficiently close implementation.
- A pessimistic independent cost estimate includes all NRE, package, HBM, board, host, network, rack, yield, respin, operations, and financing.
- Contracted token volume amortizes NRE within the downside model lifetime.
- Base-case launch advantage is at least 4x and remains at least 2x under joint pessimistic cost, utilization, yield, performance, volume, and incumbent-improvement assumptions.
- The device has an explicit salvage path for the next model revision.

## Kill criteria and pivots

Stop the custom-silicon thesis if any of these persist after calibrated measurement:

- Best quality-controlled gain is below 1.5x on commodity hardware.
- Gains disappear under realistic cache misses, failures, or p99 SLOs.
- The optimized model loses task success or requires retraining cost larger than serving savings.
- The same gain transfers poorly to a second model and projected per-model NRE cannot be contracted.
- Incumbent private pricing leaves insufficient gross-margin budget.
- The model's commercial lifetime is shorter than NRE recovery.

Possible business outcomes remain valuable even if silicon fails:

- A model-specific managed inference provider on commodity hardware.
- A co-design optimizer licensed to model labs, clouds, and chip vendors.
- A simulation and procurement product that predicts the cheapest deployment and validates provider quotes.
- A reusable accelerator substrate with model-specific firmware, memory mapping, and kernels rather than a unique tape-out per model.

## Evidence still missing

The current dossier does not contain:

- A negotiated Fireworks, Baseten, or other provider quote.
- A measured GLM 5.2 endpoint replay with latency, failures, cache hits, and billed tokens.
- A measured GLM 5.2 dedicated topology or throughput result.
- Customer-derived agent traffic distributions or willingness to trade latency for price.
- Accelerator, HBM, package, server, network, or colocation quotes for custom hardware.
- A bottoms-up engineering schedule and staffing budget.
- An externally reviewed silicon NRE, yield, or model-lifetime estimate.
- A measured quality-preserving architecture modification.

These omissions are blockers for a provider or silicon investment claim, not reasons to stop the simulator work. They define the next evidence to acquire.

## Source registry

All sources are primary vendor, model-owner, or government pages and were accessed 2026-07-12.

- [Fireworks Serverless pricing](https://docs.fireworks.ai/serverless/pricing)
- [Fireworks pricing, including On-demand](https://fireworks.ai/pricing)
- [Fireworks Serverless overview](https://docs.fireworks.ai/serverless/overview)
- [Fireworks model overview](https://docs.fireworks.ai/models/overview)
- [Fireworks inference product](https://fireworks.ai/inference)
- [Fireworks GLM 5.2](https://fireworks.ai/models/fireworks/glm-5p2)
- [Fireworks Qwen3 8B](https://fireworks.ai/models/fireworks/qwen3-8b)
- [Baseten pricing](https://www.baseten.co/pricing/)
- [Baseten Model APIs](https://www.baseten.co/products/model-apis/)
- [Baseten cache-token pricing announcement](https://www.baseten.co/resources/changelog/cache-token-pricing-for-model-apis/)
- [Baseten autoscaling](https://docs.baseten.co/deployment/autoscaling/overview)
- [Baseten cold starts](https://docs.baseten.co/deployment/autoscaling/cold-starts)
- [Baseten deployment concepts](https://docs.baseten.co/deployment/concepts)
- [Baseten environments](https://docs.baseten.co/deployment/environments)
- [Z.AI GLM 5.2 architecture and serving article](https://z.ai/blog/glm-5.2)
- [Z.AI pay-as-you-go pricing](https://docs.z.ai/guides/overview/pricing)
- [Z.AI GLM-5.2-FP8 pinned checkpoint](https://huggingface.co/zai-org/GLM-5.2-FP8/tree/ba978f7d347eaf65d22f1a86833408afdb953541)
- [Z.AI GLM-5.2-FP8 pinned configuration](https://huggingface.co/zai-org/GLM-5.2-FP8/blob/ba978f7d347eaf65d22f1a86833408afdb953541/config.json)
- [NVIDIA GLM-5.2-NVFP4 pinned checkpoint](https://huggingface.co/nvidia/GLM-5.2-NVFP4/tree/aec724e8c7b8ee9db3b48c01c320f63f9cdaf8aa)
- [NVIDIA H100 specifications](https://www.nvidia.com/en-in/data-center/h100/)
- [NVIDIA H200 specifications](https://www.nvidia.com/en-us/data-center/h200/)
- [U.S. EIA Electric Power Monthly table 5.3](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=table_5_03)
