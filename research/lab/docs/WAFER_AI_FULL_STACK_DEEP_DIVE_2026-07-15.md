# Wafer AI full-stack research deep dive

Date: 2026-07-15  
Decision: what should the Inference Foundry learn from Wafer AI, particularly its recent AMD work, to improve model-specific inference research?

Companion report: [Wafer AI product and inference infrastructure](WAFER_AI_PRODUCT_AND_INFRASTRUCTURE_REPORT_2026-07-15.md), including supplier evidence, the TensorWave exclusivity question, product packaging, and a recommended launch path.

## Executive conclusion

Wafer is the closest public analogue to the Inference Foundry thesis found in this review. Its published work supports the central claim that model-specific co-optimization can produce large serving gains by searching across weights, inference engines, decoding, cache state, parallelism, kernels, and hardware as one system.

The strongest lesson is not to begin with custom kernels or to prefer AMD by default. Wafer's successful sequence is:

1. Measure the exact model and workload on the target hardware.
2. Search compatible engines, representations, decoding features, KV-cache formats, and parallel layouts.
3. Fix correctness and support gaps that prevent promising combinations from running.
4. Profile the residual bottleneck.
5. Specialize kernels or heuristics for the exact shapes only when the profile justifies it.
6. Re-measure end-to-end quality, latency, throughput, and economics.

This is evidence for a thin research factory: capable agents, concise research skills, direct access to profilers and GPUs, durable telemetry, and fast experiment loops. Wafer's public material does not support building a large deterministic orchestration system. Its public agent skill is short; the sophistication is in the tools, measurements, model/hardware knowledge, and iteration.

Wafer has credible AMD results, but its claims are mostly first-party or co-authored vendor evidence and are workload-specific. Current independent market measurements also show that Wafer is competitive rather than universally fastest or cheapest. Treat its results as high-value priors and implementation blueprints, not transferable performance claims.

## Scope and falsifiability

This review covers Wafer's public product, technical articles, public repositories, current model listings, and third-party measurements. It asks whether the company's public work demonstrates a useful full-stack research method and which parts can improve the GLM-4.7 Flash campaign and later GLM-5.2 work.

It does not audit Wafer's private production code, reproduce its benchmarks, or establish its margins. Most end-to-end results lack complete runnable artifacts. The conclusions would weaken if matched reproduction showed that the reported gains disappear, quality regresses materially, or the economics rely on unavailable hardware rates or unsustainable utilization.

Evidence labels used below:

- **Measured, first-party:** Wafer reports a measurement and enough workload detail to interpret it, but it has not been independently reproduced here.
- **Measured, co-authored vendor:** a hardware/cloud vendor publishes a result with Wafer; useful but not independent.
- **Independent live measurement:** a third party currently measures Wafer's public endpoint.
- **Public artifact:** code, benchmark output, pull request, or skill is inspectable at a pinned revision.
- **Derived:** arithmetic applied to cited prices or measurements.
- **Inferred:** a conclusion drawn from several pieces of evidence rather than directly reported.

## What Wafer appears to be building

[Wafer's technology description](https://www.wafer.ai/technology) presents an autonomous performance engineer that profiles a model, identifies bottlenecks, generates changes, verifies them, and deploys the resulting stack. Its declared search surface spans:

- workload orchestration, batching, and scheduling;
- decoding and speculative execution;
- quantization and numerical representation;
- serving engines such as vLLM, SGLang, TensorRT-LLM, and ATOM;
- CUDA, HIP, Triton, and NKI kernels; and
- NVIDIA, AMD, and AWS accelerator hardware.

The company also sells model endpoints, so its optimization loop is tied to deployment economics rather than kernel benchmark scores alone. [Y Combinator](https://www.ycombinator.com/companies/wafer) lists Wafer as a six-person S25 company founded in 2025. That small team and the breadth of its published work are meaningful evidence that agent-amplified research can increase researcher leverage, although they do not reveal how autonomous the private system is.

## The strongest full-stack case studies

| Model and hardware | Reported outcome | Layers changed | Research lesson | Evidence strength |
| --- | --- | --- | --- | --- |
| GLM-5.2 on 8× AMD MI355X | 213 output tok/s single stream on an Artificial Analysis-like 10K/1.5K workload; 2,626 output tok/s/node at 2.4 requests/s on a 20K/1K, 60%-cache-hit workload | BF16→MXFP4 with Quark; engine comparison; SGLang support fixes; MTP quantization mapping; ROCm compatibility; FP8 KV; AITER all-reduce fusion; TP8 versus TP4×DP2; shape-specific MoE heuristic | The win was a sequence of representation, compatibility, decoding, communication, topology, and kernel-selection changes. It was not primarily a new kernel. | Measured, first-party; quality point estimates and workloads are reported, but no matched independent reproduction or full stack is public. |
| Qwen3.5-397B-A17B on AMD MI355X | 310 output tok/s single stream, reported as 20% above a tuned baseline | ATOM; MXFP4 weights; FP8 KV; MTP-3; custom M=4 MoE GEMM; router/shared-expert fusion; prefix-cache and chunked-prefill correctness fixes | Exact decode geometry created a profitable specialized kernel, while recurrent-state cache correctness was a production-critical systems problem. | Measured, first-party; technically detailed but not independently reproduced. |
| Qwen3.6-35B-A3B on AMD MI355X | 430 output tok/s single stream and 15K aggregate output tok/s/node at a production operating point | ATOM feature/configuration search; FP8 weights and KV; two MTP draft tokens; TP4×DP2 | Some large wins come from searching existing features and topology rather than writing a kernel. | Measured, first-party. |
| Kimi K2.5, DeepSeek V3.2, and GLM-5 on 8× AMD MI350X/MI355X | Kimi: 22.5→255.2 tok/s; DeepSeek single stream: 38.5→200.8 tok/s and c64 aggregate: 548→2,165 tok/s; GLM-5: 151.1 tok/s mean | Quantization, attention and MoE paths, fusion, graphs, speculation, and TP/DP configuration | Frontier-model support gaps leave large cross-layer opportunities on new hardware. | Measured, co-authored vendor; [DigitalOcean and Wafer](https://www.digitalocean.com/blog/maximize-frontier-models) explicitly note that results are internal and configuration-sensitive. |
| Llama 3.1 8B on AMD MI300X versus NVIDIA H100 | 7,353 versus 11,553 aggregate tok/s, but 3,695 versus 2,315 tokens per dollar using stated $1.99/h and $4.99/h prices | vLLM nightly; FP8; custom kernels; HIP graphs | Slower hardware can win the economic objective if its rate and utilization compensate. | Measured, first-party; the NVIDIA comparison used published NIM data and market assumptions rather than one matched venue. |

Sources: [GLM-5.2 on AMD](https://www.wafer.ai/blog/glm52-amd), [Qwen3.5 kernel work](https://www.wafer.ai/blog/kernels-are-still-the-moat), [Qwen3.6 on MI355X](https://www.wafer.ai/blog/qwen36-mi355x), [DigitalOcean full-stack study](https://www.digitalocean.com/blog/maximize-frontier-models), and [MI300X cost study](https://www.wafer.ai/blog/the-overlooked-gpu).

### GLM-5.2 is the most relevant blueprint

Wafer's GLM-5.2 study is unusually valuable because the intervention chain is explicit:

- It compared vLLM, ATOM, and SGLang rather than treating the incumbent runtime as fixed.
- It chose SGLang because vLLM did not support the needed MXFP4/GLM-MoE-DSA combination and ATOM degraded at long context.
- It quantized the BF16 checkpoint to MXFP4 with AMD Quark, then checked model quality against the official FP8 checkpoint.
- It repaired an MTP module-prefix mapping issue and a ROCm/CUDA include guard that blocked the desired configuration.
- It enabled FP8 KV cache and AITER all-reduce fusion.
- It measured MTP as close to a 3× single-stream improvement in that scope.
- It used TP8 for single-stream speed and TP4×DP2 for aggregate production throughput.
- It adjusted the MoE kernel heuristic for GLM-5.2's exact dimensions and routing geometry.

This is a direct blueprint for the later GLM-5.2 campaign on AMD. It is not transferable evidence for GLM-4.7 Flash: checkpoint size, active parameters, representation, shapes, runtime support, workload, and hardware differ.

### Specialized kernels are valuable after localization

Wafer's Qwen3.5 work provides the clearest custom-kernel example. For one request plus three speculative draft tokens, it specialized an M=4 MoE path, removed sorting/permutation, fused gate-up, activation, and down projection, dequantized on load, and eliminated intermediate HBM traffic. Wafer reports that six launches became one, the MoE call became 1.84× faster, and end-to-end decode gained 30–40 tok/s.

The important research pattern is the boundary condition: a stable and frequent exact shape justified specialization. A generic instruction to “optimize kernels” would not have identified M=4 or established that the call was material to end-to-end cost.

### Correctness is part of performance research

The same Qwen3.5 study found that hybrid recurrent GDN state made conventional prefix caching incomplete. Before repair, temperature-zero output could be coherent but nondeterministic. It also found a chunked-prefill slicing bug. These are not peripheral production chores: correct prefix reuse reportedly changed 16K-token TTFT from 37.7 seconds to 150 milliseconds at high hit rates.

The lab should therefore verify semantic correctness at the boundary where a risky optimization changes numerical behavior, cache state, concurrency, or generated kernels. It should not expand this into repeated campaign-wide validation when the identity and intervention do not change.

## How Wafer's agents appear to work

### Direct tools and short loops

Wafer's public posts show a repeated loop of documentation search, profiler inspection, implementation, correctness testing, and benchmark comparison:

- A [profile-guided optimization study](https://www.wafer.ai/blog/profile-guided-optimization) used NCU to expose 64 blocks on 145 SMs, 0.04 waves/SM, and 6.25% occupancy; vectorization and unrolling improved the kernel by roughly 9× to 11.65× depending on comparison.
- Its [top-k sigmoid study](https://www.wafer.ai/blog/topk-sigmoid-optimization) reports seven AMD variants in hours, moving through atomics, shared memory, wave shuffles, DPP, and hand-written assembly. The associated [ROCm AITER pull request](https://github.com/ROCm/aiter/pull/1909) exposes correctness and benchmark results publicly.
- [Trace Compare](https://www.wafer.ai/blog/trace-compare) aligns AMD and NVIDIA traces and separates prefill from decode so agents can identify platform-specific overhead rather than optimize aggregate traces blindly.
- Its [ROCprofiler Compute guide](https://www.wafer.ai/blog/rocprofiler-compute) emphasizes roofline and hardware-counter evidence on AMD.
- The [Wafer CLI](https://www.wafer.ai/blog/wafer-cli) gives agents documentation search with citations, NCU/NSYS/PyTorch-trace analysis, direct Perfetto queries, remote GPU evaluation, and workspaces.

The public [Wafer guide skill](https://github.com/wafer-ai/skills/blob/9348c00b6d734d9f2a444670493e5029b12023cf/.cursor/skills/wafer-guide/SKILL.md) is concise. It describes the available tools and a basic optimize/evaluate loop. It does not encode a large state machine. This aligns with the current research-factory direction: behavior belongs in compact skills; code should provide reliable execution, telemetry, artifacts, and cleanup.

### Telemetry breaks theory-only plateaus

The profile-guided case also shows the limit of agent reasoning without observations. The agent found several local optimizations from code, but the profile revealed a grid too small for the GPU. Even then, it did not change launch geometry. This is a useful warning: a capable model still needs explicit, queryable traces and must be prompted to revisit the experimental geometry when measurements contradict its current line.

The practical requirement is not maximal telemetry collection. It is low-friction access to enough telemetry to attribute time and cost by prefill/decode, operator, launch, communication, cache behavior, and utilization, with the configuration and workload identity attached.

### Generated-kernel evaluation needs a narrow adversarial boundary

Wafer's [reward-hacking field guide](https://www.wafer.ai/blog/reward-hacks-field-guide), [reward-hacking analysis](https://www.wafer.ai/blog/reward-hacking), and [Kernel Arena methodology](https://www.kernelarena.ai/methodology) document false speedups such as unsynchronized timing, no-op or stale-buffer reuse, pointer-keyed caching, out-of-bounds shared memory, and exploiting weak tolerances.

Use synchronized timing, fresh or poisoned buffers, guard regions, determinism checks, and basic resource sanity for generated-kernel contests. Keep those checks at the generated-kernel benchmark boundary. Re-running the same adversarial suite for every engine flag or topology experiment would slow the factory without protecting the changed risk surface.

## Public artifacts and what is actually reproducible

Pinned public repositories inspected for this review:

| Repository | Revision | What it provides | Limitation |
| --- | --- | --- | --- |
| [chipbenchmark](https://github.com/wafer-ai/chipbenchmark/tree/c6744a0fa6b083e73e305d7d931ed29ab8cd4b43) | `c6744a0fa6b083e73e305d7d931ed29ab8cd4b43` | Model/hardware/precision benchmark layout, scripts, and hardware data | Last pushed July 2025; does not contain current frontier AMD production work. |
| [kernel-arena](https://github.com/wafer-ai/kernel-arena/tree/8363bf36e493a2d2f6357e4d6b16b6e4e445fe11) | `8363bf36e493a2d2f6357e4d6b16b6e4e445fe11` | Public kernel tasks, solutions, correctness rules, and agent results | Microbenchmarks, not end-to-end serving; no SPDX license was exposed in the repository metadata inspected. |
| [HIP benchmark results](https://github.com/wafer-ai/HIP-Benchmarks-Results/tree/93d4c7b42eba4ac0b3c0d3dc171ca92483d76135) | `93d4c7b42eba4ac0b3c0d3dc171ca92483d76135` | Generated HIP solutions and results | Benchmark output rather than the private optimization platform; no SPDX license was exposed. |
| [skills](https://github.com/wafer-ai/skills/tree/9348c00b6d734d9f2a444670493e5029b12023cf) | `9348c00b6d734d9f2a444670493e5029b12023cf` | The compact public Wafer guide skill | Tool usage surface, not the private director, telemetry store, or production stack; no SPDX license was exposed. |
| [GPU performance resources](https://github.com/wafer-ai/gpu-perf-resources/tree/42f0908908686e70de88ddd9cb5b62dc25e9c9da) | `42f0908908686e70de88ddd9cb5b62dc25e9c9da` | Curated GPU optimization references | Reference collection; no SPDX license was exposed. |

Absence of an SPDX license in the inspected metadata is not a legal determination, but it means these repositories should be used as evidence unless a usable license is confirmed. The public artifacts do not include Wafer's complete serving stack, model-specific production patches, experiment scheduler, telemetry store, or cost accounting. Reproducing its commercial system from public code is not currently possible.

Kernel Arena's public MI300X results are also a warning against choosing the optimized model itself as the kernel-writing agent. In its 41-task aggregate, the `glm_4.7` agent passed 38 tasks but beat the PyTorch reference on only seven; `glm_4.7_min` passed 31 and beat the reference on ten, with one large outlier. Several stronger frontier agents passed 40–41 and produced many more faster solutions. These are generic kernel-generation tasks rather than GLM-4.7 serving kernels, but they support retaining a stronger director/researcher model for low-level optimization.

## Market reality check

Independent live measurements qualify Wafer's first-party headlines:

- [Artificial Analysis's Wafer page](https://artificialanalysis.ai/providers/wafer), retrieved 2026-07-15, reports GLM-5.2 at up to 230 output tok/s, 1.60-second TTFT, and `$0.79/M` under its default 7:2:1 cache-hit-input-output blend.
- [Artificial Analysis's GLM-5.2 provider comparison](https://artificialanalysis.ai/models/glm-5-2/providers) currently lists faster endpoints and a cheaper blended provider. Wafer is credible and competitive, not the universal frontier.
- Wafer's listed standard prices are `$0.20/M` cached input, `$1.20/M` uncached input, and `$4.10/M` output. The derived blend is `(7×0.20 + 2×1.20 + 1×4.10)/10 = $0.79/M`; at that exact mix this is `$7.90` per million output tokens after including the associated nine million input/cache tokens.
- [OpenRouter's GLM-5.2 page](https://openrouter.ai/z-ai/glm-5.2) reports different live speed for Wafer because its routing, workload, and measurement window differ. Do not treat endpoint measurements from distinct harnesses as matched contradictions.
- [Vercel's launch note](https://vercel.com/changelog/glm-5-2-fast-via-wafer-now-available-on-ai-gateway) reports that its own benchmarking found more than 2× serverless throughput and over 170/200 tok/s for smaller/larger contexts. This is useful partner validation, but it does not expose a fully matched public benchmark artifact.

The appropriate competitive use is to record Wafer as both a serving-stack prior and a market comparator. Its public endpoint price does not establish its underlying GPU cost or margin, and its node benchmarks do not establish sustainable retail cost.

## Full-stack opportunity map for the research factory

The director should search interactions among these layers rather than allocate one permanent project to each:

| Layer | Questions telemetry should answer | Typical interventions |
| --- | --- | --- |
| Model and quality | Which layers/operators are sensitive? Does the candidate preserve task quality? Is speculation trained and calibrated? | Selective precision, distillation, pruning, architecture or MTP changes, calibration-aware quantization |
| Checkpoint and representation | Where are memory bandwidth, capacity, and dequantization costs paid? | BF16/FP8/AWQ/NVFP4/MXFP4, mixed precision, weight layout, KV precision |
| Engine and compatibility | Which runtime supports the exact architecture/representation correctly and efficiently? | vLLM/SGLang/ATOM/TRT-LLM comparison, targeted support fixes, compiler settings |
| Decode algorithm | Is decode compute-, memory-, launch-, or acceptance-limited? | MTP/speculative decoding, draft count, verification strategy, CUDA/HIP graphs |
| Cache and state | What is the real prefix/KV hit rate and does state reuse preserve semantics? | Prefix cache, recurrent-state cache, KV layout/precision, cache-aware routing |
| Parallelism and placement | Is communication or replica underfill dominating at the target load? | TP/DP/EP, TP4×DP2, multiple replicas/GPU, disaggregation, NUMA/network placement |
| Scheduler and workload | What concurrency and queue envelope minimizes cost while meeting background completion/reliability needs? | Continuous batching, admission control, chunked prefill, request bucketing, asynchronous queues |
| Kernels and compiler | Which exact operators/shapes dominate residual end-to-end time? | Existing-library selection, autotuning tables, fusion, layout, generated or hand-written kernels |
| Hardware and venue | Which accelerator and rate maximize sustainable useful tokens per dollar? | NVIDIA/AMD/Trainium/older GPUs, spot or reserved capacity, power and interruption strategy |
| Production economics | Does the measured operating point survive utilization, failures, retries, and orchestration? | Replica sizing, autoscaling, checkpoint recovery, rate negotiation, capacity portfolio |

The unit of prioritization should be a cross-layer hypothesis with a quick falsifier, for example: “At background concurrency 16, TP4×DP2 with FP8 KV on engine X reduces all-in output cost because communication is no longer on the critical path.” It should not be “investigate parallelism” or “optimize kernels.”

## Implications for GLM-4.7 Flash now

GLM-4.7 Flash is a 30B-A3B model and the current AWQ artifact is about 20.2 GB. Wafer's frontier-model MI355X successes do not imply that an eight-GPU MI355X node is the cheapest placement for this much smaller model. The likely economic opportunity may instead be replication, high background batching, or cheaper older GPUs.

The next full-stack search should be telemetry-led:

1. Preserve the current runnable AWQ control and establish cost/quality at the target background load.
2. Compare current compatible engines and representation paths only where the exact checkpoint can run; do not assume vLLM is fixed.
3. Measure MTP on this exact model before investing. Existing external evidence suggests it may regress rather than help in at least one GLM-4.7 scope, which is the opposite of Wafer's GLM-5.2 result.
4. Search concurrency, batching, cache policy, and replica/topology geometry before custom kernel work. A 20.2 GB artifact may fit multiple serving replicas on large-memory accelerators or fit cheaper hardware with a better hourly rate.
5. Use operator and launch traces from the best economic operating point to decide whether a shape-specific MoE dispatch, heuristic, fusion, or dequantization kernel is material.
6. Screen AMD as a candidate using model fit, engine maturity, exact measured throughput, available rate, and multi-replica utilization. Benchmarking on Nebius does not constrain eventual placement.
7. Compare sustainable all-in output cost against the Artificial Analysis GLM-4.7 Flash hurdle already recorded in the campaign, with scope-matched quality and background-workload reporting.

This does not require eight simultaneous layer projects. The director should rank two or three competing explanations for the current cost bottleneck, run the cheapest discriminating measurements in parallel, and update the ranking from the resulting telemetry.

## Implications for GLM-5.2 next

Wafer's AMD study should be treated as a direct competitor blueprint and a reproduction checklist:

- Quark MXFP4 conversion and scope-matched quality evaluation;
- SGLang versus current vLLM/ATOM support and long-context behavior;
- MTP quantization mapping and ROCm compatibility;
- FP8 KV and AITER communication fusion;
- TP8 versus TP4×DP2 under single-stream and aggregate loads; and
- the exact GLM-5.2 MoE heuristic shapes on MI355X.

The first GLM-5.2 director turn should refresh Wafer's endpoint prices and independent speed, inspect whether upstream runtimes have absorbed Wafer's fixes, and reproduce the cheapest high-information subset. It should not recreate fixes that are now upstream or claim Wafer's MI355X numbers on another stack.

## Minimal changes adopted in this repository

1. Add one concise director instruction to search the interaction among quality/checkpoint, engine, decode, cache, topology, kernels, hardware, and economics, and to profile before specializing.
2. Link this review from the GLM-4.7 campaign as a recurring full-stack prior and mark the GLM-5.2 path as a later competitor blueprint.
3. Keep code responsibilities unchanged: reliable launching, cleanup, timing, telemetry, identity, and artifact storage. Keep research judgment in the director and researcher skills.
4. Do not add a Wafer-specific service, deterministic stage gate, permanent per-layer portfolio, or mandatory validation loop.

## Sources and retrieval record

All sources were retrieved 2026-07-15 unless noted. Prices, provider rankings, hardware availability, product features, and repository heads can change.

| Source | Publisher | Evidence used | Type |
| --- | --- | --- | --- |
| [Technology](https://www.wafer.ai/technology) | Wafer | Declared full-stack product surface and optimization loop | Vendor-reported |
| [YC company profile](https://www.ycombinator.com/companies/wafer) | Y Combinator | Team, cohort, product positioning | Third-party company profile |
| [Seed round](https://www.wafer.ai/blog/seed-round) | Wafer | Funding and company context | Vendor-reported |
| [GLM-5.2 on AMD](https://www.wafer.ai/blog/glm52-amd) | Wafer | GLM-5.2 intervention sequence, quality, and performance | Measured, first-party |
| [Kernels are still the moat](https://www.wafer.ai/blog/kernels-are-still-the-moat) | Wafer | Qwen3.5 kernels, cache correctness, and performance | Measured, first-party |
| [Qwen3.6 on MI355X](https://www.wafer.ai/blog/qwen36-mi355x) | Wafer | Configuration search, topology, prices, performance | Measured, first-party |
| [Maximize frontier models](https://www.digitalocean.com/blog/maximize-frontier-models) | DigitalOcean and Wafer | AMD full-stack methods and model results | Measured, co-authored vendor |
| [The overlooked GPU](https://www.wafer.ai/blog/the-overlooked-gpu) | Wafer | MI300X/H100 throughput and stated economics | Measured/derived, first-party |
| [Top-k sigmoid optimization](https://www.wafer.ai/blog/topk-sigmoid-optimization) | Wafer | Agent kernel-iteration sequence | Measured, first-party |
| [AITER pull request 1909](https://github.com/ROCm/aiter/pull/1909) | ROCm/Wafer contributor | Public code and benchmark table | Public artifact |
| [Profile-guided optimization](https://www.wafer.ai/blog/profile-guided-optimization) | Wafer | Profiler-guided agent behavior | Measured, first-party |
| [Trace Compare](https://www.wafer.ai/blog/trace-compare) | Wafer | Cross-platform trace analysis | Vendor-reported tool behavior |
| [ROCprofiler Compute](https://www.wafer.ai/blog/rocprofiler-compute) | Wafer | AMD profiling workflow | Technical guide |
| [Wafer CLI](https://www.wafer.ai/blog/wafer-cli) | Wafer | Agent documentation, trace, evaluation, and workspace tools | Vendor-reported |
| [Reward hacks field guide](https://www.wafer.ai/blog/reward-hacks-field-guide) | Wafer | Generated-kernel evaluator failure modes | Technical analysis |
| [Kernel Arena methodology](https://www.kernelarena.ai/methodology) | Wafer/Kernel Arena | Correctness and timing methodology | Public methodology |
| [Artificial Analysis: Wafer](https://artificialanalysis.ai/providers/wafer) | Artificial Analysis | Independent live endpoint price and performance | Independent live measurement |
| [Artificial Analysis: GLM-5.2 providers](https://artificialanalysis.ai/models/glm-5-2/providers) | Artificial Analysis | Current competitive placement | Independent live measurement |
| [OpenRouter: GLM-5.2](https://openrouter.ai/z-ai/glm-5.2) | OpenRouter | Alternate live provider measurement and pricing | Third-party live measurement |
| [Vercel Wafer launch](https://vercel.com/changelog/glm-5-2-fast-via-wafer-now-available-on-ai-gateway) | Vercel | Partner benchmark and availability | Partner-reported measurement |
