# Overnight decision report — 2026-07-12

Status: evidence synthesis updated through 10:30 CEST. Later-result sections supersede earlier counts or scope language where they differ.

## 10:30 evidence addendum

Six results materially sharpen the overnight decision without changing the no-cost-claim verdict.

First, the checked [competitive landscape](../validation/results/inference-codesign-competitive-simulation-landscape-2026-07-12.json) now binds 30 primary sources, 19 entries, 32 source-scoped claims, and 12 occupied layers. The added evidence covers IndexCache, TISA, HISA, MISA, UNIQUE, SPIN, INTRA, Salca, and NOSA. Cross-layer index reuse, temporal/hierarchical DSA, head routing, page-aware selection, locality-trained offload, sparse gathers, and sparse-attention accelerators are all active categories. The surviving wedge is therefore not an obvious GLM sparse-attention mechanism; it is an independently validated discovery loop that beats these public baselines.

Second, the [predictive-validity gate](../validation/results/simulator-predictive-validity-gate-2026-07-12.json) audits 61 workspace JSON artifacts across ten candidate audit families and admits one exact prospective pair. Its direction is correct but 44.7% effect error fails the 15% bound; only one intervention/regime exists, rank correlation is unavailable, no regression was predicted, and exact quality/SLO cost evidence is absent. Predictive validity remains `NOT_MET`; no simulated performance or cost result may be promoted. The evaluator verifies real artifact bytes plus in-file scope, value, and content identities rather than accepting labels.

Third, the [public-agentic GLM mapping screen](../experiments/glm-5.2/agentic-mapping-screen-v1.json) maps all 64 synthetic proxy requests at exact 5K–131K token geometries and five concurrency points. Coupled/overlap/decoupled partial-residency counts are `64/0/0`, `63/0/1`, `48/0/16`, `24/0/40`, and `8/8/48` at C1/C8/C16/C32/C64. This establishes context/concurrency segmentation, but candidate full capacity remains uncertain for all 64 requests at every concurrency. Tokenizer equivalence, output work, arrivals, tool delays, prefix behavior, network timing, quality, SLOs, and cost are excluded. The 90K case elsewhere in this report is only a token-geometry control.

Fourth, the fully drained [Ramulator2 HBM3 sensitivity sweep](../validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json) executes 18 cases twice and completes all 1,363,968 callbacks with exact replay and conservation accounting. It finds a valuable cross-fidelity sign reversal: sorting the same logical selected-token set lowers controller cycles by 27.744% for a one-32-byte-line probe but raises them by 59.194% for a 36-burst, 1,152-byte BF16 one-layer record. Cluster64 similarly changes from −50.569% to +2.709%. This kills a geometry-insensitive locality claim and shows why bank parallelism must be modeled alongside row locality. The patched-native run is synthetic, single-channel, one-controller, one-attempt-per-tick, and `NoRefresh`; it is not a real GLM trace, GPU timing, calibration, energy, cost, or provider result.

The [small-model proxy decision](SMALL_MODEL_PROXY_SELECTION.md) keeps pinned Qwen3-0.6B as the current local quality-bearing proxy, selects NOSA-1B for a future single-CUDA-GPU sparse/offload experiment, retains Idiap's 1.4B NSA model as a secondary mechanism control, and rejects the tiny random DeepSeek-V3.2 fixture for quality, performance, or cost work. No small model can authorize transfer to GLM-5.2.

Finally, the first prospective local kernel prediction is now measured. The [locked prediction](../validation/predictions/qwen3-0.6b-int4-aarch64-neon-v1.json) forecast a 1.75× explicit-NEON speedup and was committed with the exact implementation and config before timing. The [holdout result](../experiments/qwen3-0.6b/int4-aarch64-neon-v1.json) measures 4.457× over the scalar packed path and 3.284× over the scalar f32-QDQ control on the same three exact tensors. All work, preallocated-buffer, and correctness gates pass; maximum output error is 5.25e−6. This is a positive component result showing that architecture-specific code can erase the local packed-decode tax. It is also a failed magnitude prediction: the predicted 42.857% time reduction versus measured 77.565% gives 44.747% relative effect error, above the 15% predictive gate. The result is one-thread, batch-one, layer-zero, uncontrolled-host microbenchmark evidence—not tuned BF16/Accelerate, full-model execution, vLLM, quality transfer, serving, energy, or cost.

## Decision

**Continue the research program; do not claim a provider cost advantage or authorize custom silicon.**

The thesis has moved from an untested story to a plausible, falsifiable research program:

- A measured Qwen3-0.6B tensor-selective INT4 variant passed the declared teacher-forced numerical gates on its 155-target selection corpus and independent 512/4,096-target WikiText-2 subsets. The exact BF16-stored-scale runtime representation also passes both proxy sizes. After withdrawing a source-fidelity-broken PIQA artifact, the frozen exact-source rerun scores 174/256 baseline versus 175/256 candidate and passes the declared two-point gate; its 95% paired-bootstrap interval still crosses the non-inferiority margin, so confirmatory non-inferiority remains inconclusive.
- A first real Rust packed-INT4 smoke stores three exact selected tensors in 37.5% of their BF16 bytes and matches an independent QDQ reference exactly. Its simple scalar decode/matvec is 1.368× slower than the matched scalar f32-QDQ control. A corrected identical-loop batch frontier then finds no crossover at B=1, 4, 16, or 64: packed remains 1.7–6.6% slower.
- A new tensor-derived KV-head sharing frontier directly tests the proposed “small weight change for lower bandwidth” mechanism. The largest one-shot candidate that passes both 512- and 4,096-target teacher-forced gates removes only 1.786% of KV bytes; the next point fails, and full 50% sharing catastrophically fails.
- A separate-data 2,048-target recovery run then tests the material full 8→4 candidate with frozen shared K/V and rank-8 Q/O adapters. It recovers only 3.80% of the zero-token NLL gap, fails every gate by wide margins, and stops rather than spending a projected additional 83 minutes on the same recipe.
- Four request-level vLLM CPU measurements passed the strict Rust provenance importer and exposed a real concurrency tradeoff. A new frozen repeatability harness then made host admission fail closed: after 355 five-second samples over 30 minutes produced no three-sample clean streak, it launched no resumed server and classified the campaign as host-contamination blocked.
- The analytical Qwen3-8B study identifies a coherent KV-bandwidth and fleet-sizing mechanism.
- Released GLM-5.2 architecture and vendor deployment evidence provide concrete model-specific co-design targets.
- A strict GLM-5.2 storage/residency engine now exposes checkpoint, cache, device-count, and commercial throughput thresholds for BF16, native FP8, and expert-selective NVFP4 without inventing latency or cost results.
- A canonical cross-backend action ledger and a GLM compound tiered-cache event model now make compute, memory, cache, collective, scheduler, and prefix-lifecycle hypotheses explicit and fail closed on uncalibrated totals.
- A Rust claim-composition gate now refuses to multiply marginal, cross-model, cross-workload, component, simulated, or claim-locked effects into dollars per token. The current seven-artifact GLM request has zero admissible exact joint cost claims.
- A whole-decode GLM lowerer now replaces the tiny mechanism fixture with exact active FFN work and explicit bounds for every remaining model-specific phase.
- An absorbed-MLA DSA/IndexShare sweep finds a real incumbent architecture benefit but rejects selected-index HBM bypass as a meaningful standalone cost lever.
- Exact GLM parallel-mapping arithmetic finds an 85.86% network-byte opportunity from independent attention/expert placement, but coupled placement still wins partial residency at low concurrency and the full decoupled capacity bound is uncertain.
- A deterministic fixed-budget P/D control shows that disaggregation is not intrinsically cheaper: neutral P/D is 5.18% worse, an explicit interference/specialization upside is 35.22% better, and transfer congestion can erase the gain. All timing and cost claims remain locked.
- A physical-feasibility audit gives a conditional go for software/model research and a no-go for tapeout: the original fixture's 5.38× ratio is invalid as a performance claim, and a throughput-only counterfactual yields just 1.054×.
- Current public pricing now gives the simulator explicit commercial break-even thresholds.
- A deterministic public-agentic proxy now replaces short identical prompts for the next simulation stage: 64 synthetic requests, eight overlapping sessions, exact 5K–131K input bounds and 27K mean, dynamic prefixes, tool delays, and class SLOs. It uses no private benchmark data and carries no performance or cost claim.

The evidence also falsifies the easy version of the pitch:

- Blanket naive INT4 is not quality-qualified, even on the small model and tiny corpus.
- Correct scalar and matched batch/tiled packed-INT4 paths are slower, not faster, than their controls. An executable representation is necessary but insufficient; only a genuinely tuned architecture-specific kernel and fair production baseline can reopen performance, and no byte-only speed or cost claim survives.
- The passing selective change can provide at most a derived 1.327× ideal speedup through weight-byte reduction alone, even under the impossible assumption that 100% of time is weight reads.
- The quality-passing one-shot KV-sharing candidate is capped at 1.018× even if KV bytes are the entire decode time and a custom alias kernel is free. Full sharing has a 2× cache-only ceiling but fails every quality gate by a wide margin.
- Small-budget Q/O-only recovery does not rescue full sharing: after 2,048 training targets, perplexity remains 2,535× baseline, RMSE is 8.83× the allowed limit, and cosine slightly worsens. Other conversion methods remain open, but this exact recipe is rejected.
- No measured CPU concurrency point passed all class SLOs.
- The first and second c1/c8 serving runs diverged by 1.51× and 3.08× in output throughput. A strict randomized five-repeat campaign could not proceed because Spotlight exceeded the fixed 20% co-tenant threshold for all 355 admission samples; one earlier c8 pair is insufficient, so local serving remains uncalibrated.
- The Qwen3-8B cost advantage remains analytical and depends on simultaneous unvalidated model, kernel, and hardware changes.
- Baseten already reports custom shared DSA, agent-calibrated NVFP4, Blackwell, KV routing, P/D, and MTP at 280+ streaming token/s per user. Fireworks already reports independent expert/attention sharding, DP attention, tiered cache, low precision, P/D, and tuned speculation at a 446 token/s peak and about 2× its Standard path. FireOptimizer automates choices across hardware, model, and software. NVIDIA now publishes a Rust full-stack serving twin, an open silicon-backed configurator, and explicit hardware-friendly model-design rules. Etched says it already co-designs chips through racks around production-traffic simulation. Removing a generic abstraction layer, building a serving simulator, combining known serving techniques, or stating that model shape matters is therefore not a moat by itself.
- Model-specific silicon requires much more volume than an early company can safely assume, and the current nominal compute, HBM, and fabric rates do not exceed relevant commodity roadmaps.
- The first capacity-coupled BF16 H200 business screen clears the hurdle by only 8.05% under lower-work, free-prefill, peak-rate, perfectly linear scaling; any 7.45% loss erases it.

The current verdict is therefore:

| Thesis layer | Verdict | Evidence |
|---|---|---|
| Model-specific optimization exists | **Plausible** | Selective INT4 passes held-out proxies and its frozen PIQA-256 point gate, but confirmatory non-inferiority is inconclusive and current kernels regress |
| Simulation can find economically useful changes | **Unproven** | No calibrated intervention-delta or ranking evidence yet |
| Qwen3-8B paired design is cheaper | **Analytical hypothesis** | 34.67% modeled workload-weighted reduction; quality and hardware unvalidated |
| We can beat current inference providers | **Unproven** | No identical provider trace, quote, quality, and SLO comparison |
| Per-model custom silicon is justified | **No; tapeout NO-GO** | Physical audit finds plausible headline rates but no residual moat, full workload, PPA, package/yield proof, quotes, contracted volume, or pessimistic NRE case |
| A 5–10× gain is achievable | **Unsupported** | No measured result near this claim; selective weight compression alone is ideally capped at 1.327× |

The checked machine-readable [`model-stack-business-decision-2026-07-12.json`](../validation/results/model-stack-business-decision-2026-07-12.json) now binds 31 exact source files, 27 internal content identities, 100 source facts, and 30 arithmetic checks into 20 explicit pursue/measure/kill decisions. Its fail-closed result is stricter than the prose: no measured $/token reduction, material improvement, provider superiority, 5×/10× result, calibrated-simulation claim, full end-to-end simulation claim, buildable-hardware claim, or tapeout authorization is permitted. The strongest conditional opportunities are the four-B200 residency discontinuity, context-sensitive independent GLM mapping, and architecture-specific local kernel work; all still require representative runtime measurement.

The additive [`current-cost-claim-composition-v1.json`](../experiments/glm-5.2/current-cost-claim-composition-v1.json) enforces that policy in code. It asks whether six current interventions—public NVFP4, FP8 semantic KV, independent mapping, tiered cache, P/D, and model-specific hardware—support a joint GLM output-cost result. Seven candidate evidence records yield **zero admissible claims**. Qwen storage/kernel/quality results fail model and scope; mapping measures network bytes rather than cost; SCALE-Sim reports component cycles rather than deployed latency or cost; P/D uses a different synthetic workload and has its cost claim locked; the economic frontier matches the requested intervention set but is analytical and explicitly claim-locked. Only one exact scope-, intervention-, metric-, quality-, SLO-, baseline-, and candidate-matched measured end-to-end artifact can unlock the result. Marginal speedups are never multiplied.

## Overnight thesis update: the target providers already own the vertical GLM stack

The most important market finding since the first synthesis is negative and actionable. Baseten's current GLM-5.2 engineering report describes almost exactly the proposed software-side company thesis: architecture-specific shared DSA support in its custom engine, an in-house NVFP4 quantization calibrated on agent behavior, Blackwell kernels, KV-aware routing, P/D disaggregation with NVIDIA Dynamo/NIXL, and MTP speculation. Baseten reports more than 280 streaming tokens/s per user through Artificial Analysis, about 800 ms TTFT, and 2× higher throughput from disaggregation on its observed workload shapes. [Baseten GLM-5.2 engineering report](https://www.baseten.co/blog/how-we-built-the-worlds-fastest-api-for-glm-52/) (accessed 2026-07-12).

Those public numbers are not enough to infer aggregate capacity or COGS: the topology, utilization, errors, cost, and reproducible denominator for the 2× claim are undisclosed. They are nevertheless sufficient to change the experimental control. A BF16, cache-unaware, aggregated, MTP-disabled vLLM run is no longer a fair incumbent. The minimum credible control is shared DSA + quality-qualified NVFP4 + FP8 KV + KV-aware routing + P/D disaggregation + MTP, under the same workload and SLO.

NVIDIA's public GLM-5.2 NVFP4 checkpoint reinforces that correction. Its model card targets B200/B300 and reports FP8-to-NVFP4 deltas between −0.81 and +0.86 points across five selected benchmarks. This is vendor quality evidence, not our reproduction, but it makes public selective-expert NVFP4 an incumbent baseline rather than proprietary upside. [NVIDIA GLM-5.2 NVFP4 model card](https://huggingface.co/nvidia/GLM-5.2-NVFP4) (accessed 2026-07-12).

The business now has a narrower burden of proof: the simulator must discover and validate a model or hardware intervention beyond that stack, or automate the search enough faster than Baseten/Fireworks/NVIDIA to be commercially valuable. The machine-readable evidence snapshot is [`glm-5.2-incumbent-stack-2026-07-12.json`](../validation/results/glm-5.2-incumbent-stack-2026-07-12.json).

Fireworks' public GLM-5.2 report narrows the burden further. Its Fast path independently chooses expert and attention sharding, uses data-parallel attention to keep compressed MLA KV local, tiers repeated agent prefixes, quality-gates lower precision, tunes speculation, and separates prefill from decode. Fireworks reports a 446 token/s Artificial Analysis peak and about 2× Standard on the same workload. FireOptimizer separately claims automated tuning across hardware mapping, model quantization/tuning, and serving behavior from representative data. [Fireworks GLM-5.2 Fast](https://fireworks.ai/blog/glm-5p2-fast), [FireOptimizer](https://fireworks.ai/blog/fireoptimizer) (accessed 2026-07-12).

The surviving differentiated thesis is no longer “automate full-stack tuning.” It is “simulate and search model-architecture and hardware changes that current deployment optimizers cannot make, while predicting real quality/SLO/cost deltas faster than incumbent teams.” That is a more difficult but falsifiable company.

### The simulator and model-co-design categories are not empty

The checked [`competitive landscape`](../validation/results/inference-codesign-competitive-simulation-landscape-2026-07-12.json) turns this market review into a fail-closed artifact: 30 primary sources, 19 competitive entries, 32 source-scoped claims, 12 occupied layers, five unpassed gates, and zero permitted business claims. It explicitly refuses to infer competitor absence from missing public disclosure.

NVIDIA's May 2026 DynoSim release is a direct public control for the serving simulator. It is a Rust full-stack Dynamo twin that composes vLLM/SGLang scheduler behavior, hardware-informed forward-pass timing, routing, planning, KV tiers, and trace replay on one discrete-event clock. NVIDIA reports replaying 23,608 requests in 2.41 seconds on an Apple M4 MacBook Air, about 1,500× real time, and explicitly describes an autoresearch loop over router, planner, and cache source changes. The related open AIConfigurator searches aggregated and disaggregated layouts using collected silicon timing when available. This does not invalidate our model/hardware work, but it falsifies “a fast Rust serving simulator” as differentiated product scope. [NVIDIA DynoSim](https://developer.nvidia.com/blog/dynosim-simulating-the-pareto-frontier/), [DynoSim runs](https://github.com/ai-dynamo/dynamo/blob/main/docs/dynosim/runs.md), and [AIConfigurator](https://github.com/ai-dynamo/aiconfigurator) (accessed 2026-07-12).

NVIDIA's July 10 hardware-friendly model-design guide overlaps the model half: it recommends near-square width/depth choices, 128/256/512-aligned dimensions, low-precision-friendly layers, regular pipeline stages, and independent attention/FFN parallelism. The commercial burden is no longer proving that model shape affects hardware. It is automatically finding a non-obvious quality-safe change beyond those rules and predicting its real magnitude. [NVIDIA AI model co-design](https://developer.nvidia.com/blog/ai-model-co-design-hardware-friendly-llm-design/) (accessed 2026-07-12).

Etched is the direct capital control for the future hardware company. Its current site says it co-designs chips, racks, software, packages, cooling, interconnect, and manufacturing; has N4P A0 silicon; has run terabytes of production traffic patterns through a simulator; employs 400+ engineers; has raised $800M; and is producing against more than $1B of customer demand or contracts. These are vendor statements, not independently validated performance or economics. They still show that the “simulation environment becomes a vertically integrated inference-hardware company” path already has a heavily financed competitor with silicon and supply-chain execution. [Etched](https://www.etched.com/) (accessed 2026-07-12).

ASTRA-sim, Timeloop/Accelergy, and LLMServingSim2.0 further establish end-to-end distributed-system, accelerator-mapping, and heterogeneous serving/hardware simulation as existing research categories. LLMServingSim2.0 reports sub-2% error for its tested GPU deployments; that claim is not reproduced and cannot transfer to GLM or hypothetical silicon. The strategic conclusion is narrower: the asset must be *validated predictive discovery*, not simulator breadth. [ASTRA-sim](https://github.com/astra-sim/astra-sim), [Timeloop/Accelergy](https://timeloop.csail.mit.edu/), and [LLMServingSim2.0](https://arxiv.org/abs/2511.07229) (accessed 2026-07-12).

The strongest company sequence is now: first sell or use evidence-backed model/hardware discoveries; then operate a provider only if one discovery survives full quality, agentic SLO, and cost controls; consider silicon only after the improvement transfers or contracted demand amortizes a per-model lifetime. MLPerf's open division and full-system wall-power protocol provide an eventual independent hardware target. AA-AgentPerf supplies more relevant public coding-agent geometry—5K–131K request lengths, tool delays, dynamic prefixes, and explicit TTFT/output-speed tiers—although its private test set and vendor results are not local evidence. [MLPerf submission guide](https://docs.mlcommons.org/inference/submission/), [MLPerf power policy](https://mlcommons.org/benchmarks/inference-datacenter/), and [AA-AgentPerf methodology](https://developer.nvidia.com/blog/nvidia-achieves-leading-agentic-coding-performance-on-first-agentic-ai-benchmark/) (accessed 2026-07-12).

## Evidence ledger

The labels in this report are strict:

- **Measured:** produced by an executable local workload with recorded provenance.
- **Analytical:** produced by the Level 0 performance, serving, hardware, or economics model.
- **Vendor measurement:** reported by a primary model, framework, or hardware source but not reproduced here.
- **Derived:** arithmetic from a cited fact and explicit assumptions.
- **Inferred:** a decision or mechanism that remains falsifiable.
- **Synthetic control:** a deterministic workload or mechanism fixture created by this project; it is neither observed traffic nor benchmark performance.

### Measured evidence now available

| Evidence | Scope | Result | What it cannot establish |
|---|---|---|---|
| Qwen3-0.6B naive full-weight INT4 sweep | Five group sizes, CPU teacher-forced numerics, 155 target tokens | Every group failed at least one gate | Standard task quality, Qwen3-8B quality, packed-kernel speed, serving cost |
| Qwen3-0.6B selective INT4 | `o_proj`, `gate_proj`, and `up_proj`, group 8; 155 selection targets, 512 independent WikiText-2 targets, and 4,096 sequential WikiText-2 targets | Passes all declared teacher-forced proxy gates; 24.63% estimated weight-byte reduction | Standard task quality, canonical full-test perplexity, runtime compression, latency, energy, cost, Qwen3-8B transfer |
| Qwen3-0.6B packed-format quality bridge | BF16-stored group scales; 512/4,096 WikiText targets; frozen exact-source PIQA-256 subset | Both proxies pass all five gates. PIQA is 67.97% baseline versus 68.36% candidate; the declared ≤2-point loss gate passes, but the 95% paired-bootstrap delta interval [−2.34,+3.13] points crosses the non-inferiority margin | Full PIQA, confirmatory task non-inferiority, decontamination, safety/agent tasks, packed full-model execution, serving, energy, cost |
| Qwen3-0.6B packed INT4 smoke | Three exact layer-zero `o_proj`/gate/up tensors; group-8 signed nibbles plus BF16 scales; single-thread Apple M4 Pro | 16.78→6.29 MB, exact QDQ equivalence, but 5.300 ms packed versus 3.875 ms scalar f32-QDQ: packed is 1.368× slower | Tuned BF16/BLAS/vLLM baseline, batch/SIMD kernel, full-model residency, quality transfer to BF16 scales, serving, energy, or cost |
| Qwen3-0.6B packed INT4 batch frontier | Same three tensors; identical row/tile/group/pair/lane traversal at B=1/4/16/64 | All 12 work/output checks exact; packed is 6.60%, 1.73%, 3.05%, and 2.04% slower; strict no-crossover result | Explicit SIMD or tuned kernel, activation-layout creation, BF16/BLAS/vLLM baseline, full model, quality, serving, energy, cost |
| Qwen3-0.6B KV-head sharing frontier | Per-layer tensor-distance pairing; nine candidates over 512 held-out targets; maximum pass repeated on 4,096 targets | Four single-pair layer changes pass; KV bytes −1.786%, weights −0.176%, ideal ceiling 1.018×. Five layers fails; full 8→4 sharing fails catastrophically | Uptraining recovery, task quality, alias-kernel correctness, runtime bytes, latency, energy, cost, GLM transfer |
| Qwen3-0.6B full KV-sharing recovery | Separate WikiText-2 train split; exact 8→4 sharing; frozen K/V; rank-8 Q/O adapters; 2,048 train + 512 holdout targets | Only 3.80% of NLL gap recovered; perplexity ratio 2,534.8, RMSE 4.415, cosine 0.3516, top-1 1.37%; all gates fail; 8K continuation stopped | Activation-aware or gradual conversion, trainable shared K/V, literature-scale budgets, canonical/task quality, runtime/cache/kernel/cost |
| Qwen3-0.6B vLLM CPU serving c1/c2/c4/c8 | Eight-request all-at-once burst, 128 input + 32 output, no prefix reuse | All requests execute; no concurrency passes all class objectives | GPU/provider performance, agent-length workloads, cache behavior, cost, repeatability |
| Qwen3-0.6B vLLM repeatability admission | Frozen randomized c1/c2/c4/c8 × five-repeat cold/warm protocol; 20% co-tenant threshold; three clean five-second samples required | [`7b71feaf…`](../validation/results/qwen3-0.6b-vllm-cpu-repeatability-v1.json): one prior c8 pair accepted; resumed campaign blocked before launch after 355/355 samples failed to form a clean streak; threshold unchanged and all rejected evidence retained | Repeatability, calibration, GPU/provider performance, cost, or any direction of serving improvement |
| Offline vLLM CPU throughput | Eight prompts, same 128/32 geometry | 61.62 total token/s | Request tails, queueing, SLOs, provider cost |
| Timeloop v4 external frontend smoke | Exact Qwen BF16 `o_proj` problem plus adapted official architecture/mapper fixture | Pinned frontend parses/processes and exactly reconciles MACs/FLOPs/bytes; native mapper returns 127 because executable/dependencies are absent | Mapping, cycles, utilization, calibration, energy, area, performance, or cost |
| SCALE-Sim v3 native sweep | Exact Qwen `o_proj` and GLM expert-gate GEMMs × six array/dataflow/SRAM configurations | 12/12 native runs; OS32 wins both, base rank is identical, and 4 MiB SRAM gives no native read/core-cycle benefit | BF16/NVFP4 execution, GPU time, calibrated memory, energy, area, whole model, serving, or cost |

### Synthetic workload control now available

The checked [`AA-AgentPerf public-geometry proxy`](../experiments/workloads/aa-agentperf-public-proxy-v1.json) reuses the canonical trace and workload-contract schemas. It contains 64 requests across eight overlapping sessions, exact public input-length bounds of 5K and 131K with a 27K mean, 1.728M input and 15,104 synthetic output tokens, 56 tool delays with a one-second median, dynamic prefixes in every session, and three explicitly synthetic class SLO tiers. The generator is deterministic and a second CLI run was byte-identical.

This is not AA-AgentPerf's private test set. Session count, turn mix, output lengths, prefix ratios, detailed delay distribution, arrival process, and SLO tiers are project assumptions. The artifact permits no AA-AgentPerf score, measured performance, NVIDIA/provider performance, or cost claim. Its purpose is to prevent the next serving and economics experiments from optimizing against eight identical 128/32 prompts while preserving a content-addressed, inspectable contract.

### Analytical evidence now available

| Evidence | Result | Boundary |
|---|---|---|
| Qwen3-8B same-methodology paired study | 48.39% input, 31.16% output, and 34.67% workload-weighted cost reduction | Level 0 oracle, synthetic workload, unvalidated quality and hardware |
| Qwen3-8B fleet sizing | 21 logical devices to 7 at nearly equal aggregate modeled output goodput | Search-envelope feasibility, not manufacturability or measured throughput |
| Qwen3-8B sensitivity | All 243 input cases and 162/243 output cases beat assumed owned H100; no 1,000-unit output case wins | H100 and custom-silicon TCO are assumptions, not quotes |
| GLM-5.2 architecture dossier | Exact released architecture, storage, cache lower bounds, and prioritized hypotheses | Research specification; no local GLM execution or cost result |
| GLM-5.2 storage/residency envelope | Under 64 × 32K reserved tokens, H200 minima are 16–17 BF16, 9–10 FP8, and 6–7 NVFP4 | Exact/model-backed capacity plus explicit cache assumptions; no measured route, bandwidth, latency, or throughput |
| NVFP4 + FP8-KV four-B200 frontier | FP8 semantic KV saves 94.221 GB raw and 108.354 GB total after fragmentation; lower case misses four modeled B200s by 5.268 GB, upper by 104.052 GB; lower case fits 60×32K but not 61×32K | Aggregate capacity arithmetic only. TP4, placement, allocation, kernels, serving, SLO, and cost remain false |
| Independent GLM attention/expert mapping | Coupled TP16 versus DP-local attention plus topology-local EP8 over two exact batch-8/context-16K work units | Hop bytes −85.86% and cross-domain bytes 225.608 MB→0; partial-residency crossover favors decoupled only from concurrency 43 | No calibrated link time, collectives, kernel, quality, throughput, SLO, or cost; full capacity is bounded |
| Fixed-budget GLM P/D serving control | 21 deterministic aggregate/P-D cases over one synthetic long-input agent trace | Neutral P/D raw output cost +5.18%; explicit P/D-upside −35.22%; congested full-KV transfer can remove the advantage | Rates/effects/transfer bounded and uncalibrated; no continuous batching, full residency, failures, measured latency, SLO, or provider cost |
| GLM-5.2 recursive-MTP sweep | Conditional-acceptance accounting, break-even acceptance, rejected work, and best depth across three synthetic scenarios | Planning model with synthetic acceptance and normalized work, not a performance claim |
| Canonical GLM decode action ledger | Typed dependency DAG with six action classes and checked FLOP/byte/message accounting | Synthetic mechanism slice; no calibrated latency, energy, or cost |
| Whole-decode GLM lowering | 29 actions; exact 837.116B FFN FLOPs for 16 candidates; total 837.116B–3.387T FLOPs; 52.320–731.797 GB FFN reads | Attention, DSA, cache, route-residency, MTP, and other non-FFN bounds are not jointly calibrated; route is synthetic and timing/cost stay locked |
| Public NVFP4 whole-decode lowering | Exact compute is unchanged; checkpoint payload falls 69.15%; upper FFN read bound falls 36.49%, but opaque FFN reads span zero to one full 464.795 GB payload pass | Selective tensor layout and reuse are opaque; lower byte bound is uncertainty, not a saving; quality, timing, and cost stay locked |
| Fair Blackwell NVFP4 roofline | Custom 12 TB/s/2 PF is 0.774× B200 at the lower-work corner and 1.342× at the upper-work corner; B300 is effectively tied with B200 in the HBM-bound upper case | The ranking sign flips with opaque traffic. Custom lacks native selective-NVFP4 support and is explicitly non-executable; no latency, serving, energy, or cost claim |
| Whole-decode hardware roofline | Same old profiles produce a 3.592× component-time ratio, down from 5.38× on the mechanism fixture; routed-expert HBM reads dominate | Baseline uses 3.35 TB/s rather than published H200 4.8 TB/s; no contention, serving, capacity-coupled mapping, energy, or cost claim |
| Launch-date throughput counterfactual | With identical uncalibrated control costs, custom headline rates are 2.143× published-peak H200; preliminary Rubin rates are 1.535× faster than custom | Peak component ranking only, not sustained or deployable performance; demonstrates that 12 TB/s HBM and 2 PFLOP/s are not a future moat |
| Whole-decode work-bound sensitivity | Lower-work versus upper-work throughput spans 17.98× H200, 20.56× custom, and 24.66× Rubin | Model/work uncertainty exceeds modeled hardware differences; route locality and remaining phase work must collapse first |
| Optimistic BF16 H200 business screen | 364.5K free-prefill/linear-scale peak billable token/s versus 337.3K required; 1.0805× headroom | Cannot reject but cannot establish viability; 7.45% loss fails, and every cost/provider claim stays locked |
| Economic robustness frontier | 4,374 points, 54 regions; 3,104 below margin, 354 fragile clears, 916 individual 1.25× clears, but zero regions robust across the full sweep | Source is the uncalibrated BF16 optimistic screen and lacks the incumbent combined stack; it classifies fragility, not provider economics |
| Exact one-quantum serving replay | Byte-pinned trace/ledger/roofline replay reports 63.117, 129.822, and 191.488 output token/s for H200/custom/Rubin selections | Fully reused input, one atomic quantum, loose synthetic SLO, zero intra-quantum TPOT, no repeated decode/contention/prefill; all claims false |
| GLM DSA/IndexShare sweep | Exact 73.08% indexer-execution reduction; dense/sparse component crossover between 2K and 8K; selected-index zero-HBM bound changes time only 0.01–0.14% | Incumbent model architecture and modeled serial components; no irregular-gather, utilization, distributed, SRAM, or end-to-end calibration |
| Ledger hardware roofline smoke test | Original profile ratio is 5.38×, but a throughput-only substitution yields 1.054× and fixed/coordination-only substitution yields 4.079× | The 5.38× is invalid as a performance claim: incomplete 222M-FLOP fixture and aggressive control/message assumptions, not a GLM, physics, manufacturability, or cost bound |
| Custom-hardware physical-feasibility audit | **Conditional GO for software/model research; NO-GO for tapeout** | Headline rates are plausible but at or below commodity roadmaps; capacity, PPA, package, power, yield, cost, and a launch-date residual advantage remain unproven |
| Chakra v0.0.4 export | Six representable compute/collective nodes exported as a pinned 3,084-byte protobuf stream | Interchange only; unsupported actions and rank semantics are not fabricated |
| GLM tiered prefix-cache trace | HBM-only versus HBM/host/NVMe exclusive-LRU lifecycle on 15 synthetic agent accesses | Synthetic whole-prefix trace and modeled links; no concurrent serving or calibrated recompute |
| GLM MoE routing and placement | Exact 75×256×top-8 geometry; synthetic uniform and source-affine routes across three topologies | Exact dispatch accounting but synthetic route stability and modeled links; no latency or cost |
| Provider economics | Explicit list-price, gross-margin, utilization, failure, power, capex, and NRE thresholds | Public price is not competitor COGS; enterprise discounts are unknown |
| Selective INT4 weight-traffic bound | Ideal speedup ranges from 1.066× at 25% weight-read time to 1.327× at 100% | Derived upper bound; the first measured scalar packed kernel regresses, so the bound is not attainable evidence |
| Cross-stack cost claim composition | Seven current Qwen/GLM records, zero admissible exact joint GLM output-cost claims | Evidence-policy result; prevents fictional multiplication but does not itself measure performance or cost |

## Measured quality: selective changes beat blanket quantization so far

### Selection result

The strongest current measured quality artifact is [`int4-o-gate-up-group8-quality-v1.json`](../artifacts/qwen3-0.6b/int4-o-gate-up-group8-quality-v1.json). It applies symmetric signed INT4 quantize-dequantize to every layer's attention output projection and MLP gate/up projections. Q/K/V, MLP down projections, and the language-model head remain full precision.

| Metric | Result | Gate | Outcome |
|---|---:|---:|---|
| Mean NLL delta | +0.02413 | ≤ +0.15 | Pass |
| Perplexity ratio | 1.02443 | ≤ 1.15 | Pass |
| Logit RMSE | 0.47377 | ≤ 0.50 | Pass, close to boundary |
| Logit cosine | 0.99004 | ≥ 0.98 | Pass |
| Top-1 agreement | 86.45% | ≥ 80% | Pass |

The storage estimate is:

| Quantity | Value |
|---|---:|
| Quantized parameters | 234,881,024 |
| Unique model parameters represented | 596,049,920 |
| Baseline checkpoint weight bytes | 1,192,099,840 |
| Estimated mixed-precision deployed weight bytes | 898,498,560 |
| Estimated reduction | **24.6289%** |
| Estimated whole-model bits/parameter | 12.0594 |

This artifact remains a **measured numerical pass plus an analytical whole-model storage estimate**. It explicitly records `runtime_storage_compressed: false`; the quality run still executes dequantized weights. A separate three-tensor packed-kernel smoke now measures representation bytes and scalar runtime, but it does not make the quality artifact runtime-compressed or prove full-model memory, speed, energy, or cost reduction.

The selection corpus is only eight hand-authored examples and 155 target tokens. It is not a standard benchmark and is too small to establish agent-task non-inferiority, safety, long-context behavior, or rare regressions. RMSE is also close to its gate. Candidate selection on this corpus can overfit its gates, so a separate corpus was required.

### Independently sourced held-out replication

The checked [`qwen3-0.6b-int4-o-gate-up-wikitext2-test-v1.json`](../validation/results/qwen3-0.6b-int4-o-gate-up-wikitext2-test-v1.json) evaluates the already-selected candidate on 32 deterministic token windows from the pinned `Salesforce/wikitext` WikiText-2 raw test split. The corpus was not used to select the mask and its generated identity is pinned as `bad296b44904bebae31ba4ace054aba59ac2885299a8b66db776afbcf004ba8e`.

| Metric | Held-out result | Gate | Outcome |
|---|---:|---:|---|
| Mean NLL delta | +0.03239 | ≤ +0.15 | Pass |
| Perplexity ratio | 1.03292 | ≤ 1.15 | Pass |
| Logit RMSE | 0.46207 | ≤ 0.50 | Pass, still close to boundary |
| Logit cosine | 0.99025 | ≥ 0.98 | Pass |
| Top-1 agreement | 86.33% | ≥ 80% | Pass |

All five gates pass over 512 held-out target tokens. This is stronger evidence that tensor-family selectivity matters, but it remains a custom teacher-forced proxy rather than the canonical full WikiText protocol or an agent-task benchmark. The run still uses float32 QDQ and explicitly records `runtime_storage_compressed: false`.

### Expanded sequential BF16 replication

The checked [`qwen3-0.6b-int4-o-gate-up-wikitext2-sequential4096-bf16-v1.json`](../validation/results/qwen3-0.6b-int4-o-gate-up-wikitext2-sequential4096-bf16-v1.json) evaluates the already selected mask over 4,096 contiguous targets from the same pinned WikiText-2 test stream. It partitions token positions 32 through 4,127 into 64 non-overlapping targets with rolling 32-token contexts. Neither this corpus nor its result was used to select the mask.

| Metric | 4,096-target result | Gate | Outcome |
|---|---:|---:|---|
| Mean NLL delta | +0.06184 | ≤ +0.15 | Pass |
| Perplexity ratio | 1.06379 | ≤ 1.15 | Pass |
| Logit RMSE | 0.46070 | ≤ 0.50 | Pass |
| Logit cosine | 0.98995 | ≥ 0.98 | Pass |
| Top-1 agreement | 86.13% | ≥ 80% | Pass |

This materially reduces the chance that the 512-target pass was a tiny-sample accident, but its evidence boundary remains narrow. It is a teacher-forced BF16 QDQ proxy, not task, runtime, or cost proof. The quantization arithmetic and metric accumulation use float32, then dequantized weights execute as BF16; `runtime_storage_compressed` remains false. The subset is not canonical full-test WikiText-2 perplexity, confidence intervals were not estimated, and the separate packed smoke uses BF16 scales on only three layer-zero tensors, so quality transfer, full-model latency, energy, task success, serving behavior, and dollars per token remain unmeasured.

### Executable packed-kernel smoke: compression is not speed

The checked [`int4-packed-kernel-smoke-v1.json`](../experiments/qwen3-0.6b/int4-packed-kernel-smoke-v1.json) loads the exact layer-zero attention-output, MLP-gate, and MLP-up tensors from the pinned checkpoint, verifies per-tensor BLAKE3 identities, and packs 8,388,608 weights as signed low-nibble-first INT4 codes with one round-to-nearest-even BF16 scale per group of eight. Codes plus scales occupy 6,291,456 bytes versus 16,777,216 source BF16 bytes: **37.5% retained**, with scales consuming one third of packed storage.

The packed path and an independently materialized f32-QDQ reference produce identical dequantized-weight and output checksums with zero reported error on all three tensors. That closes a narrow correctness boundary. It does not transfer the earlier quality verdict because that run used float32 scales before copying dequantized values into BF16 model parameters.

The runtime result is negative and important. Across 15 measured single-thread iterations per tensor, summed median time is 5.29975 ms packed versus 3.87458 ms for the matched scalar f32-QDQ loop. The packed path is **1.3678× slower** despite the smaller logical representation; individual slowdowns are 1.322×, 1.373×, and 1.396×. Nibble extraction, scale conversion, and scalar loop structure overwhelm the byte saving at batch one. This is not a BF16 BLAS, vLLM, SIMD, GPU, or provider comparison, and logical bandwidth is not a hardware-counter DRAM measurement.

The additive [`int4-packed-batch-frontier-v1.json`](../experiments/qwen3-0.6b/int4-packed-batch-frontier-v1.json) tests whether weight-stationary batching amortizes that overhead. Both paths use the identical row→tile→group→nibble-pair→batch-lane traversal and low/high accumulation order; the reference independently materializes f32-QDQ weights. Every tensor×batch point has equal MACs, identical output checksums, zero maximum error, and zero RMSE. The result is a strict no-crossover frontier:

| Batch | Packed median | Matched f32-QDQ median | Packed time ratio | Result |
|---:|---:|---:|---:|---|
| 1 | 5.484 ms | 5.145 ms | 1.066× | Slower |
| 4 | 9.999 ms | 9.829 ms | 1.017× | Slower |
| 16 | 27.853 ms | 27.030 ms | 1.030× | Slower |
| 64 | 39.302 ms | 38.515 ms | 1.020× | Slower |

A provisional positive frontier was deliberately discarded before reporting because its f32 control traversed columns differently and was about 1.8× slower than the established scalar control. The corrected matched result agrees in direction with the original smoke; its smaller loss comes from both paths sharing generalized group/pair/tile overhead. Feature-major input construction is excluded, compiler auto-vectorization was not inspected, no explicit SIMD or unsafe code is used, and the control is still not tuned BF16/BLAS/vLLM. The current safe Rust kernel form is therefore rejected as a speed lever. Architecture-specific work is justified only as a bounded experiment against a fair tuned baseline, not as assumed upside.

### Packed-format quality bridge: proxies pass, exact-source task point gate passes

The packed Rust representation stores each group scale in BF16, whereas the earlier quality study used a float32 scale before copying dequantized weights into BF16 parameters. The additive bridge reproduces the runtime arithmetic exactly at the representation boundary: codes are derived with the original float32 `max_abs/7` scale, that scale is rounded to BF16 RNE for storage, and dequantization uses the stored BF16 value before materializing candidate BF16 weights.

Both held-out teacher-forced proxies pass all five gates. At 512 targets, NLL delta is +0.03160, perplexity ratio 1.03210, RMSE 0.46980, cosine 0.98993, and top-1 agreement 87.70%. At 4,096 targets, the checked [`BF16-scale result`](../validation/results/qwen3-0.6b-int4-o-gate-up-bf16scale-wikitext2-sequential4096-v1.json) reports +0.05935, 1.06115, 0.46078, 0.98995, and 86.25%. BF16 scale rounding therefore does not create the feared proxy regression relative to the prior float32-scale QDQ point.

The first frozen PIQA-256 artifact was withdrawn before promotion during provenance review. Its loader stripped trailing whitespace even though the pinned official dataset script preserves it, affecting 30 of 512 selected choices and changing continuation tokenization. The selection indices, tensor mask, seed, scoring rule, and predeclared two-point gate stayed frozen while the exact source strings were restored.

The checked [`exact-source PIQA-256 result`](../validation/results/qwen3-0.6b-int4-o-gate-up-piqa256-bf16scale-v1.json) scores 174/256 baseline versus 175/256 candidate: 67.97% versus 68.36%, a +0.39-point delta. Candidate-only and baseline-only correct counts are seven and six, exact two-sided McNemar is 1.0, and the declared maximum two-point accuracy-loss gate passes. However, the paired-bootstrap 95% delta interval is [−2.34,+3.13] points, crossing the −2-point margin. The honest conclusion is therefore a passing frozen point estimate with confirmatory non-inferiority still inconclusive, not proof of task equivalence. It is also a subset result rather than full PIQA, and it does not establish decontamination, packed-kernel equivalence, agent quality, safety, serving, energy, or cost. The corrected artifact is content-bound as `165df94d…`; the withdrawn metrics are not evidence. Catching and rerunning this error is itself a useful validation-system result: source fidelity is part of the quality contract, not harmless preprocessing.

### Ideal performance bound

The checked [`qwen3-0.6b-selective-int4-impact-bound-v1.json`](../validation/results/qwen3-0.6b-selective-int4-impact-bound-v1.json) asks how much the 24.6289% weight-byte estimate could matter before implementing a kernel. With weight-read fraction `f` and byte reduction `r`, the deliberately optimistic bound is `speedup = 1 / (1 - f × r)`.

| Fraction of time spent reading weights | Ideal maximum speedup | Ideal maximum cost reduction |
|---:|---:|---:|
| 25% | 1.066× | 6.16% |
| 50% | 1.140× | 12.31% |
| 75% | 1.227× | 18.47% |
| 90% | 1.285× | 22.17% |
| 100% | **1.327×** | **24.63%** |

This ignores dequantization, alignment, cache, scheduling, and kernel overhead and holds hourly cost, utilization, quality, and SLO compliance fixed. The selective change therefore cannot explain a 5–10× win by weight traffic alone. A materially larger benefit would need a discontinuity such as one fewer device, a larger feasible batch, less replication, higher utilization, or another independent model/hardware change.

### Negative result: naive full INT4

The checked-in [`qwen3-0.6b-int4-sweep-v1.json`](../validation/results/qwen3-0.6b-int4-sweep-v1.json) remains important negative evidence. Group sizes 8, 16, 32, 64, and 128 all failed at least one declared numerical gate.

- Group 8 was closest but required six effective bits/quantized weight after scales and still failed logit RMSE and cosine.
- Group 128 matched the Qwen3-8B analytical storage assumption at 4.125 effective bits but failed all five numerical thresholds.
- The result does not invalidate calibrated, rotation-aware, or tensor-selective schemes. It does invalidate treating blanket W4 as free.

### Transfer boundary

The passing 0.6B selective variant does **not** validate the Qwen3-8B paired candidate. The analytical candidate simultaneously assumes broad group-128 W4, FP8 KV, four rather than eight KV heads, a narrower FFN, a custom kernel, and re-sized hardware. Evidence is scoped to exact model revision and exact intervention fingerprint.

### Direct model-change test: one-shot KV sharing is safe only where immaterial

The new [`qwen3-0.6b-kv-head-dedup-quality-frontier-v1.json`](../validation/results/qwen3-0.6b-kv-head-dedup-quality-frontier-v1.json) tests the user’s proposed mechanism directly. For every Qwen layer, the harness computes the minimum joint K/V-weight-distance perfect pairing. It then replaces selected head pairs by their BF16 mean. The resulting heads are exactly duplicate after the shared QK normalization and RoPE path, so a future alias-aware kernel could store one KV head per pair; the current Transformers runtime deliberately still computes and stores both, and records both runtime-reduction flags as false.

| Selected layers × pairs/layer | Estimated KV-byte reduction | NLL delta | Logit RMSE | Cosine | Top-1 | 512-target gate |
|---:|---:|---:|---:|---:|---:|---|
| 1 × 1 | 0.446% | +0.01274 | 0.17187 | 0.99866 | 93.16% | Pass |
| 2 × 1 | 0.893% | +0.00562 | 0.24363 | 0.99735 | 91.80% | Pass |
| 4 × 1 | **1.786%** | +0.01894 | 0.42371 | 0.99181 | 89.84% | **Pass** |
| 5 × 1 | 2.232% | +0.09702 | 0.71426 | 0.97660 | 80.86% | Fail RMSE/cosine |
| 28 × 1 | 12.500% | +1.11756 | 2.17818 | 0.75565 | 50.20% | Fail |
| 28 × 4 | 50.000% | +8.14768 | 4.58210 | 0.35282 | 0.78% | Fail catastrophically |

The maximum passing four-layer point also passes the independent 4,096-target sequential corpus: NLL delta +0.001409, perplexity ratio 1.001410, logit RMSE 0.438812, cosine 0.990930, and top-1 agreement 87.646%. It changes 2,093,380 actual weight values out of 596,049,920 parameters and estimates only 0.1759% lower deployed weight storage. Even if all decode time were KV traffic, its 1.786% byte reduction is capped at 1.0182×. Full sharing would save 57,344 bytes/token and 4.93% of checkpoint weights but is unusable without recovery training. The evidence therefore rejects one-shot KV merging as a material business lever; architecture-aware uptraining remains an explicit experiment, not an assumed result.

The checked [`qwen3-0.6b-kv-head-recovery-2k-v1.json`](../validation/results/qwen3-0.6b-kv-head-recovery-2k-v1.json) now tests one such recovery recipe with fully disjoint training data. It maintains exact pair sharing after every optimizer step, freezes the teacher, base model, K/V, and trains 1,376,256 FP32 rank-8 Q/O adapter parameters with teacher KL plus next-token cross entropy. After 2,048 training targets, mean NLL improves from 11.66569 to 11.35587 against a 3.51801 baseline: only **3.8025%** of the original gap. Perplexity remains 85,466 versus 33.7 baseline, logit RMSE remains 4.415, cosine worsens from 0.35282 to 0.35161, and top-1 agreement reaches only 1.37%. Every gate remains more than twice outside budget.

The run was technically stable—16 optimizer steps, exact sharing, 6.263 GB peak RSS, and about 77.6 seconds/step—but not on a credible promotion trajectory. A fresh 8,192-target run was projected at 82.8 minutes, so the same recipe was stopped at the predeclared checkpoint and no 4,096-target confirmation holdout was run. This rejects hard minimum-weight-distance pair means with frozen K/V and small-budget rank-8 Q/O-only recovery. It does not reject activation-aware initialization, trainable shared K/V projections, gradual fusion, different data, or literature-scale uptraining. The exact 50% semantic-cache opportunity cannot be credited because quality fails and the stock runtime still materializes eight heads.

## New GLM serving controls: mapping and P/D gains are conditional

The checked [`parallel-mapping-control-v1.json`](../experiments/glm-5.2/parallel-mapping-control-v1.json) compares a coupled TP16 attention-plus-MoE mapping with DP-local attention and two topology-local EP8 expert domains. It uses two explicit, unchanged lowerer work units, each batch 8, context 16,384, and 16 candidates. Coupled ring traffic is 1,804,861,440 hop bytes and 146,880 messages, including 225,607,680 cross-domain bytes. Decoupling bounds traffic at 255,197,184–255,246,336 hop bytes and 130–132 messages with zero cross-domain bytes: an 85.86% byte reduction, but not a latency or cost result.

Memory moves in the opposite direction at low concurrency. With FP8 semantic KV, the coupled plan robustly has lower partial per-device residency through 32 concurrent 16K requests, the bounds overlap from 33–42, and decoupled is lower from 43 onward. At concurrency 16, full coupled capacity is 48.101–60.449 GB/device and feasible under the modeled 164 GB/device envelope; decoupled is 61.450–172.630 GB/device and uncertain because the public NVFP4 checkpoint does not expose a complete non-routed tensor split. This validates independent mapping as a search dimension already used by Fireworks, while rejecting a universal “decoupled is cheaper” assumption.

The additive [`parallel-mapping-90k-control-v1.json`](../experiments/glm-5.2/parallel-mapping-90k-control-v1.json) adds a provider-inspired token-geometry anchor. It lowers an exact 90,000-token request instead of scaling the 16K result and preserves batch 8, 16 candidates, and two integer mapping repetitions. FP8 semantic MLA state rises from 736,100,352 bytes/request at 16K to 4,043,520,000 at 90K. Network work is unchanged by this fixture’s contract, but cluster partial-residency preference moves from decoupled at concurrency 43 to concurrency 8; the max-device threshold moves to 9. At concurrency 16, both full-capacity bounds are uncertain: coupled is 108.958–176.788 GB/device and decoupled 65.254–179.901 GB/device. Long token geometry therefore makes local attention/KV placement relevant at ordinary concurrency, but the fixture is not a representative workload and the opaque non-routed checkpoint split still blocks a full-capacity winner.

The checked [`parallel-mapping-context-frontier-v1.json`](../experiments/glm-5.2/parallel-mapping-context-frontier-v1.json) turns those anchors into a fast residency-only policy surface over eight exact contexts and concurrency 1–96. It reproduces every stored 16K and 90K anchor point before extrapolating only the exact linear semantic-KV term. Requiring both cluster-total and max-device bounds to agree, decoupled mapping becomes robustly lower at concurrency 43, 22, 11, 9, 6, 4, 3, and 2 for 16K, 32K, 65K, 90K, 131K, 262K, 524K, and 1M respectively. At 90K, C8 is cluster-lower but the combined policy remains unresolved until C9. The candidate full-capacity upper bound remains uncertain through 262K because of opaque checkpoint mapping; no partial-residency result is promoted into a deployment choice. Context-dependent attention/DSA work is explicitly excluded, so latency, throughput, quality, and cost remain false.

The checked [`pd-serving-control-v1.json`](../experiments/glm-5.2/pd-serving-control-v1.json) then holds the fleet at eight $7/hour slots and compares aggregate workers with 4/1/3, 3/1/4, and 2/1/5 prefill/transfer/decode splits. Under neutral phase effects, the best P/D delta-cache case costs $473.62 per million raw modeled output tokens versus $450.30 for aggregate, 5.18% worse. When the request explicitly penalizes aggregate phase interference by 25% and gives P/D specialization a 20% rate advantage, prefill-heavy P/D falls to $395.05 versus $609.81, 35.22% lower. Congested full-KV transfer raises that P/D case to $455.11 and can make other splits roughly 13.9% worse than neutral aggregate. These dollar values come from uncalibrated synthetic rates and are not provider COGS; every end-to-end latency, SLO, cost, and provider claim is false. The decision variable is now empirical phase interference plus the delta/full KV-transfer endpoint, not the presence of a P/D architecture.

## Measured serving: the importer works; the baseline is not stable

All four checked reports are `measured_hardware` artifacts imported through the Rust serving contract with exact model, checkpoint, tokenizer, engine, topology, trace, and source identity. The fixed trace contains eight simultaneous arrivals, each with 128 input tokens, 32 output tokens, and zero prefix reuse. Class labels change SLO thresholds but not request geometry.

| Max concurrency | Duration | Output token/s | Imported p95 TTFT | Imported p95 TPOT | Requests meeting both | Class objectives met |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 15.623 s | 16.39 | 14,183 ms | 47.25 ms | 3/8 | 0/3 |
| 2 | 15.687 s | 16.32 | 13,959 ms | 107.62 ms | 0/8 | 0/3 |
| 4 | 10.279 s | 24.90 | 7,856 ms | 145.86 ms | 0/8 | 0/3 |
| 8 | 7.850 s | 32.61 | 4,865 ms | 232.48 ms | 0/8 | 0/3 |

All 32 request executions succeeded. Higher concurrency increases aggregate output throughput and reduces burst completion/queue time, but TPOT deteriorates. At c1, token cadence is within the per-request TPOT gates, but queued requests miss TTFT. At c8, most coding and long-agent requests satisfy their TTFT ceilings, but every class misses TPOT. No point passes the full contract.

The imported TTFT intentionally includes waiting from the trace's common arrival time. Raw vLLM client TTFT begins when the client dispatches a request after its concurrency gate opens. The Rust adapter reconstructs client-side admission delay as queue time, which is why c1's imported p95 TTFT is 14.2 seconds even though dispatched-request raw TTFT is sub-second. This is the correct view for the frozen burst, but it must be documented when comparing raw and imported reports.

### Repeatability failure and blocked controlled rerun

The selected c1 and c8 reports use second runs. Their earlier raw runs with the same nominal 8×128×32 geometry differ materially:

| Point | First raw output token/s | Selected rep2 output token/s | Rep2 / first | First → rep2 mean TTFT | First → rep2 mean TPOT |
|---|---:|---:|---:|---:|---:|
| c1 | 10.88 | 16.39 | **1.51×** | 890 → 543 ms | 66.16 → 45.48 ms |
| c8 | 10.58 | 32.61 | **3.08×** | 16,518 → 4,326 ms | 245.43 → 113.32 ms |

This is a repeatability failure, not a performance win. Uncontrolled concurrent local model-training and benchmark workloads were observed during the run window. The machine was not isolated, cores and frequency were not pinned, thermals and power were not recorded, and the artifacts do not capture co-tenant process state. Warm-up, compilation, cache state, thermals, and co-tenant contention are confounded; no exact attribution is defensible.

The `warm` labels in the selected manifests are not backed by a controlled cold-versus-warm protocol. There is no clean cold-start replicate, c2 and c4 have no retained repeated measurements, and c1/c8 have only one selected repeat each. Engine startup is excluded. These reports validate the measurement/import path and show a qualitative concurrency tradeoff; they are not yet suitable for simulator calibration or provider comparison.

The new repeatability harness freezes the missing protocol rather than interpreting those results. It deterministically shuffles five cold/warm pairs at each of c1/c2/c4/c8, launches a fresh engine for every pair, captures host/provenance state, binds the benchmark to performance cores, rejects unrelated processes at or above 20% CPU, and retains every rejected attempt. One initial c8 pair was accepted. A later c2 attempt correctly rejected one measured pair when `airportd` crossed the threshold, and prelaunch gates caught Spotlight, system, Claude, and other repository activity.

The resumed campaign then required three consecutive clean five-second host samples before launching any server. Over the frozen 1,800-second admission window, all 355 samples failed to form a clean streak; the final sample found `mds_stores` at 315.5% CPU. The wait terminated after 1,802.79 seconds with `host_contamination_blocked`, wrote its timeout evidence, and launched zero resumed servers. Moving raw output to a non-indexed temporary root and adding no-index markers did not retroactively clear the already-running Spotlight scan. The threshold was not relaxed and no rejected measurement was promoted. The checked [`repeatability result`](../validation/results/qwen3-0.6b-vllm-cpu-repeatability-v1.json) content-binds this terminal as `7b71feaf…`, the 355-sample aggregate, the frozen config, the one accepted c8 pair, and 25 rejected c2 attempts. This is a successful fail-closed experiment-control result, but it supplies no serving repeatability, simulator-calibration, GPU, provider, or cost evidence.

The remaining rerun protocol is:

1. Run the frozen harness after Spotlight and all unrelated agents are quiescent; do not change its admission threshold.
2. Complete all five randomized cold/warm repeats per c1/c2/c4/c8 point and preserve contamination aborts.
3. Report medians, confidence intervals, coefficient of variation, and raw outliers only after the complete run.
4. Use the result only to validate local repeatability mechanics, then repeat with representative agent lengths, prefix reuse, and arrival processes before calibration.

## Qwen3-8B analytical result: useful mechanism, not validation

The current analytical paired candidate changes model representation, kernel, serving, and hardware together. Relative to the unchanged-model custom-sizing reference:

| Metric | Reference | Candidate | Modeled change |
|---|---:|---:|---:|
| Input cost/M | $0.010987 | $0.005671 | −48.39% |
| Output cost/M | $0.622804 | $0.428709 | −31.16% |
| Workload-weighted cost/M | $0.050531 | $0.033013 | −34.67% |
| Logical fleet | 7 devices × 3 replicas | 7 devices × 1 replica | 21 → 7 |
| Aggregate output goodput | 2,180.85 token/s | 2,189.00 token/s | approximately equal |
| Trace energy per replica | 812.9 kJ | 263.8 kJ | −67.54% |

The clearest modeled mechanism is discontinuous fleet sizing: reduced weight/KV traffic and more compute arrays let one seven-device candidate replica replace three reference replicas at roughly equal modeled aggregate goodput. This is exactly the kind of cross-layer interaction the environment should search.

It is not a measured speedup. The performance oracle is analytical, the hardware is not independently simulated or synthesized, and the paired checkpoint does not exist. The output economics are fragile: the 243-case sensitivity ranges from $0.3099 to $4.1024/M output, only 162 cases beat the assumed owned-H100 reference, and none of the 81 low-volume 1,000-unit cases win.

The analytical result should be used to prioritize KV precision, KV structure, tensor-selective weight compression, and topology thresholds. It must not appear in investor material as a provider saving.

## Business boundary

The detailed evidence is in [`BUSINESS_VALIDATION.md`](BUSINESS_VALIDATION.md) with a machine-readable snapshot in [`provider-economics-2026-07-12.json`](../validation/results/provider-economics-2026-07-12.json).

### Current public price floor

As of 2026-07-12:

- Fireworks, Baseten, and Z.AI list GLM 5.2 at $1.40/M uncached input and $4.40/M output.
- Fireworks cached input is $0.14/M; Baseten and Z.AI list $0.26/M.
- Fireworks lists H100 and H200 dedicated capacity at $7/GPU-hour and B200 at $10/GPU-hour.
- Baseten's converted public rates are approximately $6.50/H100-hour and $9.98/B200-hour, with volume discounts advertised but not quantified.

These are customer prices, not competitor costs. Identical list prices do not reveal provider margin or transfer pricing. Enterprise and reserved-capacity quotes may be lower.

### Falsifiable unit-economics target

On the repository's synthetic agent mix, 87.25% of input tokens are assumed cached. Fireworks Standard then costs a derived $0.56555/M total billable tokens. To price 20% below that and retain 60% gross margin:

| Billing dimension | Maximum infrastructure COGS/M |
|---|---:|
| Uncached input | $0.4480 |
| Cached input | $0.0448 |
| Output | $1.4080 |
| Combined synthetic mix | **$0.1810** |

At 65% useful load and 98% availability, the combined ceiling requires 2,410 billable token/s per $1/hour of fully loaded serving-system cost. An illustrative $56/hour eight-H200 system needs about 134,935 billable total token/s. This is a required benchmark result, not a GLM performance prediction.

### NRE reality

If infrastructure reaches $0.10/M, only $0.08098/M remains within the working COGS envelope for model-specific engineering and silicon NRE:

| NRE | Required lifetime tokens | Three-year average token/s |
|---:|---:|---:|
| $25M | 0.309 quadrillion | 3.26M |
| $100M | 1.235 quadrillion | 13.05M |
| $300M | 3.705 quadrillion | 39.16M |

The current hardware configuration's $300M NRE amortized over 100,000 devices is a scenario, not an expected sales plan. Per-model silicon becomes rational only with contracted demand or a reusable substrate whose model-specific portion is cheap to change.

### Competitive implication

Incumbents already market custom kernels, disaggregated serving, caching, model-specific quantization, autoscaling, and dedicated capacity. The defensible wedge is not “write the stack from scratch.” It is a demonstrably better co-design search loop that changes model structure together with memory, interconnect, kernels, scheduling, and hardware, then predicts which changes survive quality and product constraints.

## GLM-5.2: strongest opportunity and strongest warning

The full source record is [`GLM_CO_DESIGN.md`](GLM_CO_DESIGN.md).

### Released architecture facts

- Exact BF16 tensor inventory: 753,329,940,480 parameters.
- 78 backbone layers: three dense and 75 sparse MoE layers.
- 256 routed experts per sparse layer, eight selected per token, plus one shared expert.
- Derived routed-expert parameters: 96.21% of the BF16 tensor inventory.
- DeepSeek Sparse Attention with top-2,048 gathered positions.
- IndexShare reduces full backbone indexers from 78 to 21 and reuses indices across four-layer blocks.
- Native context: 1,048,576 tokens.
- One shared-parameter MTP module used recursively.
- Semantic one-million-token main MLA cache lower bound: 89.856 GB in BF16 or 44.928 GB at an ideal one byte/element, before scales, padding, indexer state, replication, and fragmentation.
- Native FP8 repository storage is about 761.0 GB. NVIDIA's selective expert NVFP4 repository storage is about 464.9 GB.

The Rust model contract now has a typed `hybrid_moe_mla_dsa` architecture with separate resident and approximate-active ledgers, routed/shared experts, MLA geometry, DSA/IndexShare, MTP, expert-selective storage, and the exact pinned BF16 payload. A first executable envelope now lowers checkpoint storage, semantic MLA cache, explicit extra/indexer cache bounds, fragmentation, device memory, bandwidth bounds, hourly price, and business break-even requirements. Detailed route distributions, compound-cache lifecycle, collectives, indexer work, calibrated phase latency, and end-to-end serving remain unsupported or fail closed.

### Executable storage and residency envelope

The checked [`storage-envelope-v1.json`](../experiments/glm-5.2/storage-envelope-v1.json) reserves 64 concurrent sequences at 32,768 tokens each: 2,097,152 token slots. The exact semantic MLA component alone is 188,441,690,112 bytes. The scenario adds explicit zero-to-32-KiB extra cache and zero-to-8-KiB indexer state per token, 64 GiB fixed runtime state, and 10% fragmentation. These are experiment assumptions, not released deployment facts.

| Checkpoint | Exact payload | Total modeled residency | H200 checkpoint minimum | H200 total minimum | Minimum H200 cost/hour | Required billable token/s at the business gate |
|---|---:|---:|---:|---:|---:|---:|
| BF16 | 1.507 TB | 1.968–2.067 TB | 12 | **16–17** | $112–$119 | 269,871–286,737 |
| Native FP8 | 755.6 GB | 1.104–1.203 TB | 6 | **9–10** | $63–$70 | 151,802–168,669 |
| NVIDIA expert-selective NVFP4 | 464.8 GB | 769.6–868.4 GB | 4 | **6–7** | $42–$49 | 101,201–118,068 |

The device-count effect is economically material: under one frozen capacity scenario, public selective expert quantization cuts the H200 residency floor by roughly 56–65% versus BF16. It is also already an incumbent baseline. The required token rates are commercial hurdle rates obtained by multiplying minimum hourly device cost by the 2,409.56 billable token/s per $1/hour gate; they are not predicted GLM throughput. The report leaves end-to-end latency and cost/M token null because route traffic, effective bandwidth, and serving have not been measured together.

### Recursive-MTP acceptance and work envelope

The Rust `glm-mtp-sweep` command implements conditional prefix acceptance. For depth `d`, expected accepted drafts are the sum of cumulative conditional acceptance probabilities; one target fallback or bonus token is then committed, and draft, verification, and scheduler work are charged explicitly. The checked [`mtp-sweep-v1.json`](../experiments/glm-5.2/mtp-sweep-v1.json) uses illustrative normalized work assumptions and deliberately synthetic acceptance paths.

| Recursive proposal depth | Homogeneous conditional acceptance needed to break even under the illustrative work model |
|---:|---:|
| 1 | 10.00% |
| 2 | 30.00% |
| 3 | 42.40% |
| 4 | 50.99% |

| Synthetic acceptance path | Best depth | Ideal normalized work speedup | Interpretation |
|---|---:|---:|---|
| Low, decaying | 1 | 1.227× | Depths 3–4 regress |
| Medium, decaying | 1 | 1.500× | Extra accepted tokens do not repay deeper draft work |
| High, decaying | 2 | 1.820× | Depth 3 remains close but loses under the assumed work curve |

This is an experiment-planning result, not a GLM speedup. Acceptance was not sampled from the exact checkpoint, work units were not measured on hardware, and serving/quality contracts were not supplied. The report therefore sets end-to-end latency, cost, and quality claim permissions to false. Its useful output is the calibration target: measure conditional acceptance by workload class and real draft/verify work before selecting recursive depth.

### MoE route-aware placement and replication

The checked [`moe-route-skew-v1.json`](../experiments/glm-5.2/moe-route-skew-v1.json) executes exact GLM geometry—75 MoE layers, 256 routed experts, and top-8 dispatch—over 16 source shards × 4,096 tokens. It compares uniform routing with an intentionally source-affine rotating 32-expert hotset carrying 85% of dispatches, three device topologies, uniform versus traffic-aware primary placement, and an optional 1,024 additional expert replicas. Each BF16 layer-local expert occupies the exact 75,497,472 bytes.

On the eight-device fully connected case:

| Route and placement | Local dispatch fraction | Remote dispatches | Endpoint payload | Added expert storage |
|---|---:|---:|---:|---:|
| Uniform route, uniform primary | 12.50% | 34,406,400 | 845.57 GB | 0 |
| Uniform route, +1,024 traffic-aware replicas | 13.16% | 34,144,256 | 839.13 GB | 77.31 GB |
| Source-affine hotset, uniform primary | 12.50% | 34,406,400 | 845.57 GB | 0 |
| Source-affine hotset, traffic-aware primary | **43.59%** | 22,180,800 | 545.12 GB | 0 |
| Source-affine hotset, placement +1,024 replicas | 45.91% | 21,267,392 | 522.67 GB | 77.31 GB |

The source-affine placement reduces remote dispatch and endpoint bytes by **35.53% at zero extra expert storage**. Replication adds 5.33% to expert-instance storage and then reduces remote dispatch only another 4.12%. Under uniform routing, the same replication budget reduces remote dispatch by just 0.76%. On the eight-device ring, source-affine traffic-aware placement reduces hop bytes from 1,932.74 GB to 731.95 GB, or 62.13%, because it removes remote dispatches and shortens remaining paths.

The current decision is therefore **measure route affinity and stability first; optimize primary placement before paying for replicas**. The result is deliberately distribution-dependent: the uniform negative control gets no primary-placement win, and a shifting real route could erase or reverse the hotset result.

The checked [`glm-5.2-route-placement-impact-bound-v1.json`](../validation/results/glm-5.2-route-placement-impact-bound-v1.json) converts traffic reduction into an ideal fixed-cost ceiling. For the fully connected endpoint metric, speedup is only 1.216× when network service is 50% of runtime and cannot exceed 1.551× even at an impossible 100% network bottleneck. For ring hop bytes the corresponding ceilings are 1.451× and 2.641×. Placement alone therefore cannot support a 5× claim. Exact GLM route histograms, churn, link calibration, topology contention, queueing, and SLOs are required before any dollars/token effect is permitted.

### Canonical action ledger

The Rust action ledger is now the backend-neutral contract for cross-layer work. It represents compute, memory movement, cache operations, network/collectives, synchronization, and scheduler decisions as a validated dependency DAG. Every action carries model, phase, and evidence provenance; FLOPs, non-FLOP operations, bytes, and messages use checked units. The ledger content ID is canonical and deliberately excludes adapter measurements so the same semantic workload can be compared across backends.

The first checked GLM decode slice has 19 actions: six compute, four memory, two cache, one network, two synchronization, and four scheduler actions. Its 222,298,112 FLOPs, 5,275,648 memory bytes, 24,576 network bytes, and 56 messages are fixture assumptions chosen to exercise MoE, DSA/IndexShare, and MTP lowering; they are not claimed GLM totals. The [`inspect-action-ledger` result](../experiments/glm-5.2/decode-action-ledger-inspection-v1.json) keeps latency, energy, and cost null because no calibrated adapter supplied every action measurement.

This is the core architectural decision: Foundry owns immutable model semantics and accounting, while external simulators attach replaceable evidence. A backend cannot silently drop an unsupported action and still produce a complete result.

#### Hardware critical-path smoke test

The `ledger-roofline` adapter maps every ledger action to an explicit compute engine, memory path, cache tier, network, synchronization, or scheduler timing. It computes a dependency-only optimistic critical path and a fully serial sum; missing hardware support is an error. The checked [`decode-ledger-roofline-v1.json`](../experiments/glm-5.2/decode-ledger-roofline-v1.json) compares two deliberately modeled timing profiles:

| Fixture result | H200-like modeled profile | Aggressive GLM-specific profile |
|---|---:|---:|
| Optimistic critical path | 48.622 µs | 9.037 µs |
| Serial action sum | 57.134 µs | 11.065 µs |
| Implied committed token/s | 61,701 | 331,961 |
| Relative ideal speedup | 1.00× | **5.38×** |

The **5.38× ratio is invalid as a performance claim and does not validate the 5–10× thesis**. The source ledger is a mechanism/API fixture with only 222.3 million FLOPs, not a complete roughly 40B-active GLM decode. The baseline serial sum is 35.4 µs fixed timing, 18.21 µs coordination, and only 3.52 µs throughput work; the assumed custom profile reduces those to 7.4, 3.082, and 0.583 µs. Replacing only the fixture's throughput totals with the custom totals yields a 1.054× serial diagnostic, while replacing only fixed and coordination totals yields 4.079×. The apparent gain is therefore created mainly by aggressive fixed-launch, scheduler, synchronization, and per-message latency assumptions on an under-complete workload. It is not a physics bound, area/power design, calibrated H200 model, serving result, or cost result.

The smoke test is still useful because it catches a central requirement: a 5× path cannot come from matrix throughput or weight bytes alone. On this fixture the largest H200-like action is MoE dispatch at 17.855 µs, so the assumed win requires coordinated improvements to fabric/message latency and the control plane as well as DSA and expert compute. The next honest run must lower full active model work and then sweep plausible hardware intervals; if 5× disappears there, this fixture must not be used to rescue it.

The independent [`custom-hardware feasibility audit`](CUSTOM_HARDWARE_FEASIBILITY.md) narrows the hardware thesis further. The assumed 12 TB/s HBM path, 1.6 TB/s fabric, and 2 PFLOP/s engines are plausible, but at or below relevant current or announced commodity peaks. The profile also omits capacity, power, precision, area, package, yield, NRE, and landed cost. The modeled expert-selective NVFP4 residency still needs 3–4 devices at 288 GB, while a single-package design needs 17–19 future 48 GB HBM4E stacks and only arithmetically fits the announced 2028 20-stack package envelope. The decision is **conditional GO for model/software co-design and NO-GO for silicon commitment** until a quality- and SLO-matched commodity stack proves at least 1.5× lower measured fully loaded cost per token on two models and leaves a material residual benefit for silicon.

#### Chakra interchange

The first external interchange adapter emits an actual length-delimited Chakra v0.0.4 protobuf stream pinned to schema commit `8b20269327725ad078483ce85d5f6dbb1cbfa611`. The checked [`chakra-decode-representable-v1.json`](../experiments/glm-5.2/chakra-decode-representable-v1.json) preserves 171,966,464 FLOPs, 8,192 non-FLOP operations, 24,576 collective bytes, 56 messages, and canonical dependencies across five compute nodes and one collective node. Its binary content ID is `1e8212424f8f5bb0a2615510dc530a1eb2543092ed694278c4fee91107b6d4ac`.

The exporter declares aggregate phase semantics with no rank assignment and emits no timing. Memory, cache, synchronization, scheduler, and point-to-point actions fail explicitly rather than being dropped or assigned invented ranks/tags. This is interchange readiness, not ASTRA validation.

#### Timeloop problem-contract boundary

The first accelerator-mapping adapter slice emits a deterministic Timeloop v4 schema-0.4 problem from Foundry’s typed `KernelProblem`. The checked [`Qwen o_proj manifest`](../experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.json) and [`problem YAML`](../experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.yaml) reconcile the exact BF16 batch-1 decode geometry (`M=1`, `N=1024`, `K=2048`) to 2,097,152 MACs, 4,194,304 FLOPs, 4,096 input bytes, 4,194,304 weight bytes, and 2,048 output bytes. Content ID is `f88f03ed0d8ae74a571d4dd21126663d3557b55263eaf87f40b50f9fe385f8bd`.

The checked [`Timeloop external smoke`](../experiments/qwen3-0.6b/timeloop-external-smoke-v1/report.json) now proves that pinned TimeloopFE 0.4 parses and processes the exact export with an adapted official v4 architecture/mapper hierarchy. The frontend independently reconciles 2,097,152 MACs, 4,194,304 FLOPs, and 4,200,448 total logical tensor bytes. It then invokes the real native path, which exits at the measured boundary: `timeloop-mapper` is absent and the local arm64 host lacks libconfig++, yaml-cpp, ISL, Barvinok, NTL, and polylibgmp. Docker and Homebrew/system packages were not modified.

This is a frontend-contract pass and machine-readable native blocker, not a simulated accelerator result. Every mapping, cycle, utilization, calibration, energy, area, performance, and cost claim remains false. The adapter also rejects the passing INT4 candidate: `KernelProblem` has scalar bit width but no group size, scale precision/count, or quantization metadata. Emitting four-bit weights would incorrectly discard the group-8 scheme’s 16-bit scales and six effective bits per transformed weight. The next truthful steps are a pinned native backend or independent lightweight simulator plus a typed quantization sidecar—not a fake INT4 mapping win.

#### SCALE-Sim native hardware sweep

The second hardware oracle executes rather than stopping at its frontend. The checked [`SCALE-Sim report`](../validation/results/qwen3-glm-scalesim-v3-gemm-sweep-v1.json) pins the official MIT `v3.0.0` release at commit `7fd972e7c650e81c77294c9433143a282235c5e7`; it also records the upstream metadata inconsistency that this tag's `setup.py` declares package version `2.0.2`. Twelve real runs cover exact Qwen `o_proj` (`M=1,N=1024,K=2048`) and a GLM routed-expert gate reference (`M=1,N=2048,K=6144`) under WS16, WS32, WS64, IS32, OS32, and a 4 MiB-SRAM WS32 control.

OS32 is the same-oracle winner for both, at 70,825 Qwen and 400,521 GLM prefetch-inclusive cycles. It is 2.808× and 2.925× lower than WS32 respectively. The whole base ranking is identical across models—OS32, IS32, WS64, WS32, WS16—so the first external hardware sweep shows dataflow sensitivity but **no model-specific best architecture**. Increasing SRAM 64 KiB→4 MiB leaves native filter reads and core cycles unchanged and worsens the inclusive cycle count, so no SRAM-capacity benefit is observed.

These are native SCALE-Sim counts, not GPU or wall-clock latency. Dense simulator elements are not BF16/NVFP4 execution, CALC mode is not a calibrated HBM system, utilization is only about 3%, and no energy/area backend ran. This independent result is useful precisely because it rejects two generic hardware stories before expensive simulation: model identity alone did not change the best base mapping, and larger SRAM alone did not help.

### Tiered compound-prefix cache experiment

The `glm-tiered-cache` engine models an exclusive LRU hierarchy with whole-entry admission, eviction, demotion, lower-tier hits, promotion, capacity, adjacent-link bytes, and a serial transfer-time lower bound. The checked [`tiered-prefix-cache-v1.json`](../experiments/glm-5.2/tiered-prefix-cache-v1.json) uses 89,856 semantic MLA bytes plus an assumed 8,192 indexer bytes per token, a synthetic 15-access agent trace, and modeled HBM/host/NVMe links.

| Result | 4 GB HBM only | 4 GB HBM + 8 GB host + 32 GB NVMe |
|---|---:|---:|
| Hit requests | 2/15 | 10/15 |
| Hit tokens | 8,192 / 258,048 | 163,840 / 258,048 |
| Tokens requiring recompute | 249,856 | 94,208 |
| Dropped entries | 12 | 0 |
| Link movement | 0 | 40.562 GB |
| Modeled serial transfer time | 0 | 1.262 s |

Tiering avoids 155,648 recompute tokens, a 62.30% reduction relative to HBM-only, but it moves 2.658 bytes across links for every byte of state associated with avoided recompute because promotion causes demotion. Under the illustrative serial timing, recompute must cost more than 8.11 microseconds per avoided token—equivalently be slower than about 123,372 tokens/s—for movement to win before contention and overlap.

This is not a cost result. The trace is synthetic, prefix entries are all-or-nothing rather than paged, bandwidths are assumptions, recompute is not calibrated, and concurrent link/HBM/compute contention is absent. The experiment already refines the design decision: cache-hit rate is insufficient; the optimizer must compare avoided prefill work against promotion/demotion amplification and tier contention.

### Simulator build-versus-integrate decision

The primary-source comparison in [`SIMULATOR_LANDSCAPE.md`](SIMULATOR_LANDSCAPE.md) found no reviewed simulator with native validated support for GLM-5.2's combined MoE, MLA, DSA/IndexShare, recursive MTP, tiered state, and online serving path. Rebuilding every simulator is not the best evidence path.

Foundry should own the model semantic compiler, request/serving state, canonical action ledger, experiment optimizer, uncertainty, and dollars/token accounting in Rust. Third-party tools remain version-pinned subprocess or trace adapters:

- LLMServingSim for an independent F2 serving comparison.
- Chakra plus ASTRA-sim 2.2 for collectives and network escalation.
- Timeloop plus Accelergy and SCALE-Sim for accelerator mapping, energy, and array studies.
- Accel-Sim, ns-3/Garnet, or gem5 only for the few hypotheses that survive fast physics and economic bounds.

The integration must be killed if it cannot reproduce its own published case, preserve action counts, predict held-out deltas within 15%, or retain design ranking. This keeps the company asset in the cross-layer semantics and evidence loop rather than in a collection of simulator forks.

### Priority hypotheses

1. Selective expert quantization and topology thresholds, using NVIDIA NVFP4 as the baseline rather than novelty.
2. An IndexShare-aware DSA scan/top-k/gather datapath with on-chip cross-layer index reuse.
3. A tiered MLA plus indexer-cache hierarchy with lifecycle-correct transfer and prefix reuse.
4. Routing-aware expert placement, replication, and interconnect under measured route skew.
5. Acceptance-aware MTP depth and fused verification under real coding outputs.
6. Prefill/decode disaggregation and network topology for 70K–1M-token agent contexts.

Z.AI, NVIDIA, vLLM, and SGLang report meaningful gains from related interventions. Those are **vendor measurements and released implementation evidence**, not independent validation. They raise the baseline the company must beat: native FP8/NVFP4, IndexShare, MTP, context parallelism, LayerSplit/HiCache, expert parallelism, and PD disaggregation.

### GLM business implication

GLM-5.2 strengthens the broad co-design thesis because its bottlenecks cross model, kernel, cache, CPU control plane, and network. It weakens any claim that the low-hanging fruit is untouched. A credible custom design must find an interaction beyond public selective quantization and framework tuning, or implement them at materially lower all-in cost.

## Current falsification gates

### Gate 1 — measurement repeatability

Pass when isolated warm and cold CPU/GPU runs have declared host state, at least five repeats, confidence intervals, and bounded variance. The frozen local campaign now enforces this contract but terminated host-contamination blocked before its second pair; protocol correctness is not measurement repeatability. Until a complete admitted run exists, no measured-serving point may calibrate the simulator.

### Gate 2 — simulator predictive validity

Pass when the simulator predicts at least three measured intervention deltas across two context regimes within 15%, obtains candidate rank correlation of at least 0.8, and predicts at least one regression. Absolute timing fit alone is insufficient.

### Gate 3 — executable selective compression

Pass when the selective INT4 candidate has a tuned full-model packed kernel with measured resident bytes, latency, throughput, and energy against a fair same-hardware baseline, plus standard task-level and safety non-inferiority. The correct scalar smoke and matched B1–B64 batch frontier are RED results for performance and do not pass this gate.

### Gate 4 — Qwen3-8B checkpoint quality

Pass only with the exact Qwen3-8B revision and exact combined change fingerprint. W4, FP8 KV, reduced KV structure, and narrower FFN need individual and combined ablations. Small-model evidence cannot unlock this gate.

### Gate 5 — tuned same-hardware baseline

Pass when the same model, tokenizer, precision, trace, cache semantics, quality, and SLO run on current tuned vLLM, SGLang, and TensorRT-LLM where supported. Record versions, commands, failures, tails, memory, power, and cost source.

### Gate 6 — provider comparison

Pass when an identical trace is replayed against Fireworks, Baseten, Z.AI, and other relevant endpoints with billed tokens, cache hits, failures, task success, TTFT/TPOT, and an actual quote. Compare cost per successful task as well as cost per token.

### Gate 7 — repeatability across models

Pass when at least 1.5× measured fully loaded cost reduction survives on two model architectures. One bespoke win is a project, not a platform.

### Gate 8 — GLM fidelity

Pass when typed MoE, MLA, DSA, IndexShare, MTP, compound cache, and expert/network behavior reproduce at least one released GLM deployment regime. No GLM economic result is valid before this.

### Gate 9 — commercial viability

Pass the base case at 20% below the best available provider quote and 60% gross margin. The downside must survive a 40% incumbent discount, 20% lower utilization, doubled failure reserve, and 30% annual incumbent improvement.

### Gate 10 — silicon authorization

Authorize tapeout only after a calibrated architecture model, synthesis/emulation evidence, independent cost estimate, contracted volume, and explicit salvage path. Require at least 4× base-case launch advantage and at least 2× under joint pessimistic performance, utilization, cost, yield, volume, and incumbent-improvement assumptions.

## Next work in evidence order

1. Rerun the CPU concurrency matrix under isolation with a cold/warm protocol and repeat statistics.
2. Treat the exact-source PIQA-256 point pass as provisional task evidence and expand to a prepowered full task and agent-quality suite before claiming non-inferiority; do not spend further compute on the rejected Q/O-only KV-recovery recipe.
3. Validate the BF16-scale packed representation on the frozen task subset; treat the current safe Rust scalar/batch kernel as a performance loss and reopen runtime only for a bounded architecture-specific implementation against a tuned same-hardware baseline.
4. Feed the exact analytical DSA counts into the whole-decode ledger, capture exact-checkpoint route/MTP histograms, and calibrate irregular gathers before interpreting hardware ratios; keep both 5.38× and 3.592× excluded from performance claims.
5. Calibrate the new GLM storage and MTP envelopes with exact-checkpoint route/acceptance traces and measured backend work when suitable hardware becomes available.
6. Reproduce one public GLM software intervention in a high-fidelity backend and test simulator delta prediction.
7. Acquire representative privacy-safe agent traces and real provider quotes before refining market claims; populate the composition gate only with exact joint evidence rather than marginal speedup products.

## Investor-safe statement

The strongest defensible statement today is:

> We have built a deterministic analytical co-design loop, provenance-strict measurement paths, and initial model-quality, training, kernel, serving, and external-hardware experiments. Selective Qwen3-0.6B INT4 passes the BF16-scale 4,096-target proxy; its exact-source PIQA point estimate passes while the paired interval leaves confirmatory non-inferiority inconclusive. Scalar and matched batch packed kernels regress despite retaining 37.5% of BF16 tensor bytes, but a prospectively locked explicit-NEON path then measures 4.457× over scalar packed and 3.284× over scalar f32-QDQ on the same three tensors. Its predicted magnitude misses by 44.7%, so the component win does not calibrate the simulator. A direct KV-sharing frontier passes only at 1.786% lower KV bytes; material sharing destroys quality, and the first recovery recipe restores just 3.80% of its NLL gap. On GLM-5.2, mapping remains capacity-uncertain on the public-agentic token geometry, while a fully drained HBM3 sweep reverses a locality result when traffic expands from one line to a BF16 record. No result establishes lower dollars per token, provider advantage, custom-silicon readiness, or 5–10×. The strongest evidence today is a growing ability to find real component wins while rejecting non-material, conditional, geometry-sensitive, falsely composed, or badly predicted claims before hardware spend.

Do not say:

- “We reduced inference cost by 34.67%.”
- “Our INT4 model is quality-equivalent.”
- “We beat vLLM, Fireworks, or Baseten.”
- “The simulator is calibrated.”
- “Custom hardware will deliver 5–10×.”

## Artifact index

- [Model-specific optimization decision register](OPTIMIZATION_DECISIONS.md)
- [Business validation](BUSINESS_VALIDATION.md)
- [GLM-5.2 co-design dossier](GLM_CO_DESIGN.md)
- [Simulator landscape and integration decision](SIMULATOR_LANDSCAPE.md)
- [GLM-5.2 storage-envelope request](../configs/glm-5.2-storage-envelope-v1.json)
- [GLM-5.2 storage-envelope report](../experiments/glm-5.2/storage-envelope-v1.json)
- [GLM-5.2 MTP sweep request](../configs/glm-5.2-mtp-sweep-v1.json)
- [GLM-5.2 MTP sweep report](../experiments/glm-5.2/mtp-sweep-v1.json)
- [Canonical GLM decode action ledger](../crates/foundry-core/tests/fixtures/glm-5.2-decode-ledger-v1.json)
- [Canonical GLM decode ledger inspection](../experiments/glm-5.2/decode-action-ledger-inspection-v1.json)
- [GLM ledger hardware timing plan](../configs/glm-5.2-ledger-roofline-v1.json)
- [GLM ledger hardware roofline smoke report](../experiments/glm-5.2/decode-ledger-roofline-v1.json)
- [Representable Chakra source ledger](../crates/foundry-core/tests/fixtures/glm-5.2-chakra-ledger-v1.json)
- [Chakra v0.0.4 export manifest](../experiments/glm-5.2/chakra-decode-representable-v1.json)
- [Chakra v0.0.4 protobuf stream](../experiments/glm-5.2/chakra-decode-representable-v1.et)
- [Timeloop Qwen BF16 problem manifest](../experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.json)
- [Timeloop Qwen BF16 problem YAML](../experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.yaml)
- [Timeloop external frontend/native-blocker report](../experiments/qwen3-0.6b/timeloop-external-smoke-v1/report.json)
- [SCALE-Sim Qwen/GLM native GEMM sweep](../validation/results/qwen3-glm-scalesim-v3-gemm-sweep-v1.json)
- [GLM-5.2 tiered-cache request](../configs/glm-5.2-tiered-prefix-cache-v1.json)
- [GLM-5.2 tiered-cache report](../experiments/glm-5.2/tiered-prefix-cache-v1.json)
- [GLM-5.2 MoE route/placement request](../configs/glm-5.2-moe-route-skew-v1.json)
- [GLM-5.2 MoE route/placement report](../experiments/glm-5.2/moe-route-skew-v1.json)
- [GLM-5.2 route-placement ideal impact bound](../validation/results/glm-5.2-route-placement-impact-bound-v1.json)
- [Qwen3-8B analytical study](../experiments/qwen3-8b/README.md)
- [Qwen3-8B compact summary](../experiments/qwen3-8b/summary-v0.json)
- [Selective INT4 passing artifact](../artifacts/qwen3-0.6b/int4-o-gate-up-group8-quality-v1.json)
- [Selective INT4 held-out WikiText-2 summary](../validation/results/qwen3-0.6b-int4-o-gate-up-wikitext2-test-v1.json)
- [Selective INT4 ideal impact bound](../validation/results/qwen3-0.6b-selective-int4-impact-bound-v1.json)
- [Selective INT4 packed-kernel smoke](../experiments/qwen3-0.6b/int4-packed-kernel-smoke-v1.json)
- [Selective INT4 matched batch frontier](../experiments/qwen3-0.6b/int4-packed-batch-frontier-v1.json)
- [Locked AArch64 NEON prediction](../validation/predictions/qwen3-0.6b-int4-aarch64-neon-v1.json)
- [Prospective AArch64 NEON result](../experiments/qwen3-0.6b/int4-aarch64-neon-v1.json)
- [Selective INT4 packed-format 4,096-target proxy](../validation/results/qwen3-0.6b-int4-o-gate-up-bf16scale-wikitext2-sequential4096-v1.json)
- [Qwen3-0.6B KV-sharing quality frontier](../validation/results/qwen3-0.6b-kv-head-dedup-quality-frontier-v1.json)
- [Qwen3-0.6B 4,096-target KV-sharing validation](../validation/results/qwen3-0.6b-kv-head-pair-mean-layer4-wikitext2-sequential4096-bf16-v1.json)
- [KV-head reduction recovery literature dossier](../validation/results/qwen-kv-head-reduction-literature-2026-07-12.json)
- [Qwen3-0.6B 2K KV-head recovery result](../validation/results/qwen3-0.6b-kv-head-recovery-2k-v1.json)
- [Small-model proxy selection](SMALL_MODEL_PROXY_SELECTION.md)
- [Public-agentic GLM mapping screen](../experiments/glm-5.2/agentic-mapping-screen-v1.json)
- [Fully drained synthetic Ramulator2 HBM3 sweep](../validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json)
- [Predictive-validity gate](../validation/results/simulator-predictive-validity-gate-2026-07-12.json)
- [Expanded competitive landscape](../validation/results/inference-codesign-competitive-simulation-landscape-2026-07-12.json)
- [Fail-closed model/stack business decision synthesis](../validation/results/model-stack-business-decision-2026-07-12.json)
- [Fail-closed current GLM cost-claim composition](../experiments/glm-5.2/current-cost-claim-composition-v1.json)
- [GLM-5.2 independent parallel-mapping control](../experiments/glm-5.2/parallel-mapping-control-v1.json)
- [GLM-5.2 context × concurrency mapping frontier](../experiments/glm-5.2/parallel-mapping-context-frontier-v1.json)
- [GLM-5.2 P/D serving control](../experiments/glm-5.2/pd-serving-control-v1.json)
- [Naive INT4 checked summary](../validation/results/qwen3-0.6b-int4-sweep-v1.json)
- [Measured CPU serving c1](../validation/results/qwen3-0.6b-vllm-cpu-serving-c1-v1.json)
- [Measured CPU serving c2](../validation/results/qwen3-0.6b-vllm-cpu-serving-c2-v1.json)
- [Measured CPU serving c4](../validation/results/qwen3-0.6b-vllm-cpu-serving-c4-v1.json)
- [Measured CPU serving c8](../validation/results/qwen3-0.6b-vllm-cpu-serving-c8-v1.json)
- [Provider economics snapshot](../validation/results/provider-economics-2026-07-12.json)
