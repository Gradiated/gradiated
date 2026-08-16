# Simulator landscape and Foundry integration strategy

**Research date:** 2026-07-12  
**Decision being supported:** what Foundry should build, reuse, or reject in order to test whether model-specific hardware/software co-design materially lowers delivered dollars per token.

## Executive decision

No available project is a credible end-to-end oracle for Foundry's thesis. The strongest existing tools each validate a slice:

- NVIDIA DynoSim is now a direct open Rust control for the serving layer: workload replay, backend-specific schedulers, hardware-informed pass timing, routing, planning, KV tiers, and autoresearch on one timeline. AIConfigurator supplies silicon-backed deployment search. Rebuilding this scope is not differentiation.
- LLMServingSim 2.0 and Vidur are useful serving-system references, but both ultimately derive device timing from measurements of existing hardware. They cannot by themselves predict a novel model and novel accelerator.
- ASTRA-sim/Chakra are useful for distributed execution and network backends, not as Foundry's model, serving, or economics representation.
- Timeloop+Accelergy and SCALE-Sim are useful for mapping tensor operators onto candidate accelerators and estimating data movement, area, and energy. They do not model request arrivals, dynamic batching, KV policy, or model quality.
- A pinned Ramulator2 HBM3 sweep now exercises a real memory-controller simulator with complete request drain. It is patched-native, synthetic, single-channel, and uncalibrated; it establishes only within-geometry sensitivity, not GLM, GPU, system, energy, or cost performance.
- Accel-Sim+AccelWattch and gem5 provide detailed microarchitectural checks, but are too slow and target-specific to sit in the inner design loop.
- llm-d-inference-sim is a good API, routing, and Kubernetes test double. Its configured sleep-time formulas are not hardware prediction.
- KernelSight-LM is the closest published architecture to the fidelity ladder Foundry needs, but it is currently a paper rather than an integrable codebase, is still anchored to GPU microbenchmarks, and publishes no evidence for MoE, MLA, sparse attention, or multi-token prediction.

**Recommendation:** keep a Rust-owned model compiler, canonical action ledger, experiment policy, uncertainty model, and dollar-cost gate, but treat serving simulation as replaceable infrastructure rather than product moat. Compare or integrate DynoSim/AIConfigurator and LLMServingSim instead of recreating their mature surfaces. Adopt Chakra as an import/export format, not as Foundry's canonical internal schema. Use ASTRA-sim 2.2 for collective/network studies and Timeloop+Accelergy/SCALE-Sim for candidate accelerator studies. Add Accel-Sim or gem5 only for hypotheses that survive the fast tiers.

The business moat is not another roofline calculator or serving twin. It can only be validated predictive discovery: translating a model mutation and an agentic workload into causal compute, memory, communication, cache, serving, quality, and cost actions; replacing estimators without changing the experiment; predicting held-out intervention ordering and magnitude; and accumulating a private corpus of cross-layer measurements and decisions. NVIDIA's public model-co-design guidance and Etched's claimed simulator-to-silicon program make even this a burden of proof, not presumed white space.

## Evidence standard and terminology

This report uses only project repositories, project documentation, and original papers. Marketing claims are labeled as such when the evidence is narrower than the wording. Facts below are separated from Foundry recommendations.

Fidelity terms used here:

- **F0 — accounting/roofline:** tensor shapes, FLOPs, bytes, capacity, peak bandwidth/compute, and simple communication equations.
- **F1 — calibrated operator/kernel:** measured or learned timing/energy for operators or kernels, composed without detailed device execution.
- **F2 — serving/system discrete event:** arrivals, queues, batches, scheduling, cache state, parallelism, and resource contention.
- **F3 — detailed component simulation:** packet, memory-controller, systolic-array, instruction, or cache-line execution.
- **F4 — measured system:** real serving software and hardware. This is the calibration and held-out validation tier, not a simulator.

“Cycle-level” is not synonymous with “cycle-accurate microarchitecture.” A simulator can timestamp events in cycles while obtaining a layer's duration from a profile. The important question is which causal mechanisms it actually models.

## Comparison at a glance

| Project | Best-supported fidelity | Serving/model | Network | Hardware/energy | Needs target GPU or profiling? | Code license | Foundry disposition |
|---|---|---|---|---|---|---|---|
| NVIDIA DynoSim + AIConfigurator | F1+F2 | Strong vLLM/SGLang/TRT-LLM replay, routing, planner, P/D, KV tiers, agentic traces, deployment search | Dynamo topology and transfer models | Measured/silicon database plus empirical/SOL modes | No GPU for bundled silicon profiles; profiling needed for unsupported systems | Apache-2.0 repositories | Primary serving/search control; integrate or compare, do not rebuild as moat |
| LLMServingSim 2.0 | F1+F2; F3 network option | Strong continuous batching, MoE, parallelism, cache/offload | ASTRA analytical backend | Profile-selected GPU/CPU/CXL/PIM behavior; no GPU microarchitecture | No GPU to replay bundled profiles; NVIDIA GPU/CUDA/vLLM to add hardware | MIT in repository | Integrate as comparison oracle; borrow scenarios, not architecture |
| Vidur | F1+F2 | Strong dense-model serving and deployment search | Profiled collectives | Device represented by learned timing profiles | GPU for every new model/SKU; multi-GPU/node for new network profile | MIT | Use as regression oracle and design reference; do not embed as core |
| llm-d-inference-sim | Realtime API test double, not predictive fidelity | Strong API/control-plane mimic | Configured P/D transfer delay | No causal device model or energy | No GPU; optional CPU render/tokenizer sidecar | Apache-2.0 | Use for API, router, metrics, and failure tests only |
| ASTRA-sim 2.2 + Chakra | F2 distributed DAG; selectable F0/F3 backends | Workload trace, not inference serving | Analytical, ns-3, Garnet, or custom | Roofline/SCALE-Sim compute and analytical remote memory | No GPU once trace/timings exist | MIT + Chakra Apache-2.0 | Integrate network/collective backend and Chakra interchange |
| ASTRA-sim 3.0 paper | Proposed cache-line F3 for GPU/network | Kernel DAG, not serving | InfraGraph + detailed network | Generic CU/load-store execution | Paper evaluates generic GPU | No public 3.0 release identified | Track; do not schedule integration against unreleased code |
| Timeloop + Accelergy | F0/F1 analytical mapping/energy | Tensor algebra only | Static on-chip communication abstraction | Strong memory hierarchy, mapping, action energy/area | No GPU; energy tables/plugins must be calibrated | BSD-3-Clause + MIT | Integrate for candidate accelerator mapping and energy/area |
| Accel-Sim + AccelWattch | Instruction/SASS F3 | Executed kernels only | On-chip GPU model; not serving fabric | Detailed GPU performance and power | Real NVIDIA GPU/CUDA/NVBit for new traces and calibration; pre-traces exist | BSD-style; see license caveat | Escalation backend for a few decisive kernels |
| SCALE-Sim v3 | Matrix-array F3 | GEMM/convolution/attention operators only | On-chip/multicore data movement; Ramulator for DRAM | Systolic array, sparsity, layout, SRAM/DRAM, Accelergy | No GPU | MIT | Integrate for custom matrix-engine hypotheses |
| Ramulator2 v2.1.0 | Memory-controller F3 | Synthetic request traces only | None | DRAM command, row-buffer, bank, and controller timing; no accelerator or energy model | No GPU | MIT | Independent irregular-memory sensitivity oracle; calibration and GLM transfer remain blocked |
| gem5 | Full-system/component F3 | Actual software only if ported | Ruby/Garnet/HeteroGarnet | CPU, memory, AMD gfx9 GPU, device models | No physical GPU; efficient AMD GPU full-system use prefers x86 Linux/KVM and ROCm images | BSD-3-Clause with mixed components | Use only for CPU/memory/ISA hypotheses that pass faster tiers |
| ns-3 | Packet-network F3 | None | Strong packet/protocol/network emulation | None | No GPU; C++/Python/CMake | GPLv2 | Access through ASTRA or isolated adapter when packet effects matter |
| KernelSight-LM | F1+F2 in paper | Strong dense serving composition | Analytical TP collective | Roofline × learned efficiency and host overhead | Tier A uses prior-GPU data; Tier B adds target microbenchmarks | Paper only; no implementation license | Reproduce the useful ideas; reassess if code is released |
| LLMCompass | Operator/mapping F1 | Static inference graph, no online serving | Multi-GPU communication model | Hardware mapper plus area/cost model | Runs on commodity hardware; no target GPU required for simulation | BSD-3-Clause | Baseline and idea source, not a production dependency |
| GenZ | F0 analytical | Static latency/memory estimate | TP ring and PP hop model | Hardware-spec sensitivity | No GPU | MIT | Fast independent sanity check only |

License names describe the top-level code at the cited revision, not every dependency. A commercial distribution still requires a pinned software-bill-of-materials review. In particular, ns-3 is GPLv2; keeping it behind a process boundary is an engineering recommendation, not a legal conclusion.

## Coverage of model-specific mechanisms

Legend: **N** = explicitly native in public documentation or paper; **T** = representable only after Foundry translates it to generic trace/actions, potentially with adapter or backend changes; **K** = representable only by running or implementing the corresponding kernels; **P** = partial proxy, not a causal model; **—** = no public evidence. Here, DSA means DeepSeek Sparse Attention and its dynamic index/gather behavior, not generic static sparsity.

| Project | MoE/EP | MLA | DSA/sparse attention | MTP | Tiered KV/cache |
|---|---:|---:|---:|---:|---:|
| LLMServingSim 2.0 | **N** | **T** | **T** | **T** | **N** for KV offload and CPU/CXL/PIM memory tiers |
| Vidur | **T** | **T** | **T** | **T** | **P**: prefix cache work exists on canary; no causal multi-tier model documented |
| llm-d-inference-sim | **P**: arbitrary latency profile only | — | — | — | **P**: GPU prefix blocks and P/D transfer delay, not multi-tier bandwidth/contention |
| ASTRA-sim/Chakra | **T** via routed experts/all-to-all | **T** | **T** | **T** | **T** via remote-memory/data-movement actions |
| Timeloop+Accelergy | **T** for individual expert tensors, not dynamic routing | **T** operator mapping | **T** via sparse tensor model | **T** as extra operators | **P**: static memory hierarchy, not runtime cache policy |
| Accel-Sim+AccelWattch | **K** | **K** | **K** | **K** | **K** if software explicitly moves data; no serving policy |
| SCALE-Sim v3 | **T** for expert GEMMs | **T** for matrix portions | **P**: SpMM/data sparsity is not dynamic attention indexing | **T** as extra GEMMs | — |
| Ramulator2 | — | **T** for explicitly lowered cache requests | **P**: synthetic logical-token gather only | — | **P**: one DRAM tier without runtime cache policy |
| gem5 | **K** | **K** | **K** | **K** | **K** with a complete runtime/device implementation |
| KernelSight-LM paper | — | — | — | — | **N** for two-tier GPU/disk prefix cache |
| LLMCompass | **T** after extending graph/operator support | **T** | **T** | **T** | — |
| GenZ | —; expert parallelism is a documented TODO | — | — | — | — |

“Representable” is deliberately weaker than “supported.” A generic DAG can encode an MLA projection or an expert all-to-all after Foundry already knows its tensor shapes and routing behavior; it does not discover those behaviors, guarantee the right kernel mapping, or validate the result.

## Target implication: GLM-5.2 cannot be a dense trace with a new name

GLM-5.2 is an unusually strong stress test for the adapter architecture. Z.ai's official repository describes a 744B/40B-active family with DSA and says GLM-5.2 adds a 1M-token context, one-per-four-layer IndexShare, and an improved MTP path; the vendor reports 2.9× lower per-token FLOPs from IndexShare at 1M context and up to 20% longer MTP acceptance ([official repository](https://github.com/zai-org/GLM-5)). The official SGLang deployment guide identifies 78 layers, 256 routed experts with top-8 activation, DSA top-2048 selection, and one MTP layer ([SGLang GLM-5.2 guide](https://docs.sglang.io/cookbook/autoregressive/GLM/GLM-5.2)). The pinned checkpoint config also exposes low-rank query and compressed-KV dimensions characteristic of MLA ([pinned config](https://huggingface.co/zai-org/GLM-5.2/raw/b4734de4facf877f85769a911abafc5283eab3d9/config.json)).

No reviewed simulator publishes native, validated support for that combination. The correct division of responsibility is:

| GLM-5.2 mechanism | Foundry-owned semantic model | External escalation |
|---|---|---|
| MoE top-8 routing | Per-token expert choice/skew, placement, batching, capacity, weight residency, and EP schedule | ASTRA for all-to-all/fabric; Timeloop/SCALE-Sim for expert engines; selected real kernels for calibration |
| MLA compressed KV | Exact projections, semantic KV bytes, cache placement, quantization, and reuse | Timeloop/SCALE-Sim for matrix portions; selected kernel simulation for fused attention; memory-tier adapter for movement |
| DSA top-2048 | Index projection/scan/top-k, irregular gather, core attention, context dependence, and index-cache state | Accel-Sim only for an implemented GPU kernel; custom memory/NoC model for candidate gather hardware |
| IndexShare | Which layers own an indexer and how indices remain live across the four-layer group | Generic ledger dependencies; no third-party model should infer this |
| MTP | Draft depth, acceptance distribution, verification, rollback, scheduler occupancy, and output-token accounting | Kernel timing backend for draft/verify operators; serving result stays Foundry-owned |
| 1M context/tiered state | KV/index capacity, prefix lifecycle, transfer, eviction, and concurrency | ASTRA/ns-3 for shared-fabric transfer; detailed memory backend only for finalists |

A smaller proxy must preserve the mechanism under test, not merely parameter count. The frozen [proxy ladder](SMALL_MODEL_PROXY_SELECTION.md) keeps Qwen3-0.6B as the current local quality-bearing dense proxy and reserves NOSA-1B for a future single-CUDA-GPU sparse-locality/offload experiment. Neither can transfer performance or cost approval to GLM-5.2. A dense model can validate accounting and basic serving but cannot validate expert skew or all-to-all; a generic MoE can validate routing but not DSA gathers. The first credible GLM result should therefore compose separately validated mechanism slices in one ledger, carry uncertainty for each slice, and remain labeled a prediction until an actual GLM-5.2 serving trace is held out for F4 validation.

## Tool dossiers: facts and implications

### 0. NVIDIA DynoSim and AIConfigurator

#### Primary-source facts

DynoSim is a Rust discrete-event twin of the NVIDIA Dynamo inference stack. Its public documentation composes trace or synthetic workload replay, vLLM/SGLang/TRT-LLM scheduler models, hardware-informed forward-pass timing, aggregated and disaggregated workers, KV-aware routing, host/offload tiers, and planner actions. NVIDIA reports replaying a 23,608-request Mooncake tool-agent trace with eight workers in 2.41 seconds on an Apple M4 MacBook Air, roughly 1,500× faster than the simulated window. The release explicitly describes configuration sweeps and autoresearch-style source changes to router, planner, and cache policy, with real-cluster testing retained as the validation loop ([announcement](https://developer.nvidia.com/blog/dynosim-simulating-the-pareto-frontier/), [run documentation](https://github.com/ai-dynamo/dynamo/blob/main/docs/dynosim/runs.md)).

AIConfigurator searches deployment layouts for Dynamo or llm-d across TensorRT-LLM, vLLM, and SGLang. It supports aggregated/disaggregated workers, parallelism and MoE placement, SLA filters, replay-backed search, and generated deployment artifacts. Its documentation distinguishes `SILICON`, `HYBRID`, `EMPIRICAL`, and speed-of-light database modes and says only silicon mode is reproducible. The repository includes a native Rust/PyO3 core and is Apache-2.0 licensed ([repository](https://github.com/ai-dynamo/aiconfigurator)).

#### Foundry recommendation

Make DynoSim plus AIConfigurator the minimum public comparison for serving configuration search. Foundry should only retain independent serving code where it is required to evaluate model/hardware semantics these tools cannot express or to enforce cross-vendor evidence policy. A feature checklist is not enough: compare request timelines, cache behavior, scheduler decisions, and held-out hardware deltas. Any claimed advantage must arise from model or hardware discovery, evidence portability, or prediction accuracy—not from implementing another Rust event queue.

### 1. LLMServingSim 2.0

#### Primary-source facts

The project describes itself as a cycle-level LLM-serving simulator with a Python front end mirroring vLLM continuous batching, an ASTRA-Sim C++ analytical network backend, and per-hardware timing from a vLLM-based layerwise profiler. It explicitly supports heterogeneous accelerators, CPU/CXL/PIM memory tiers, MoE routing, and TP/PP/EP/DP multi-instance parallelism ([repository](https://github.com/casys-kaist/LLMServingSim)). The public documentation additionally lists chunked prefill, prefix caching, KV-cache offload, ShareGPT traces, and closed-loop agentic sessions ([overview](https://llmservingsim.ai/docs/getting-started/overview)).

The simulator can run from preprofiled data on a Linux/Docker host. Ubuntu 22.04+ is tested; Git submodules, about 12 GB of disk, and Docker are required. An NVIDIA GPU and Container Toolkit are optional for simulation but required to profile new hardware, and the documentation recommends 32 GB RAM for the vLLM benchmark side ([installation overview](https://llmservingsim.ai/docs/getting-started/overview)). The repository build compiles its ASTRA-Sim and Chakra submodules.

Its strongest evidence is unusually concrete but narrow. The published validation replays 300 pinned ShareGPT-derived requests at about 10 requests/s against vLLM 0.19.0 on one RTX PRO 6000 system. Mean TTFT/TPOT/end-to-end errors are -0.3%/+0.7%/+0.4% for Llama-3.1-8B TP1, +2.4%/+1.7%/+2.0% for Qwen3-32B TP2, and -1.5%/+1.1%/+0.9% for Qwen3-30B-A3B DP2×EP2. The worst listed P99 deviation is +4.7% for MoE TTFT ([validation](https://llmservingsim.ai/docs/validation)). This validates three bundled `(hardware, model, topology)` combinations, not arbitrary future accelerators or GLM-family mechanisms.

The code repository has an MIT `LICENSE` and GitHub identifies it as MIT ([repository](https://github.com/casys-kaist/LLMServingSim)); the documentation footer says Apache 2.0. Treat the repository license at the pinned commit as controlling for code and record the discrepancy in the SBOM.

#### Foundry recommendation

Use LLMServingSim as the first F2 comparison adapter and reproduce its three committed validation scenarios. Do not fork its Python object model into Foundry. Import/export request traces and compare per-request timelines, batch composition, collective volume, TTFT, TPOT, and throughput. Its profile lookup can also serve as an F1 oracle while Foundry's own ledger remains authoritative.

It is the best existing check for MoE/EP serving behavior, but its profiler makes it weakest exactly where Foundry's thesis is strongest: unbuilt hardware, new kernels, and architecture changes that alter the operations themselves. Require an explicit “measured profile,” “interpolated profile,” or “counterfactual hardware” provenance tag on every result.

### 2. Vidur

#### Primary-source facts

Vidur is a Python discrete-event LLM inference simulator that combines experimental operator profiling with predictive models and reports TTFT, TPOT, end-to-end latency, batch size, throughput, and capacity-per-dollar. It models multiple replicas, tensor parallelism, pipeline parallelism, trace or synthetic request generation, Poisson arrivals, chunked-prefill scheduling, and configuration search. The main branch lists Llama, CodeLlama, InternLM, and Qwen dense models on A100/H100/A40-class configurations; prefix caching and additional routing work is described as canary-branch work ([repository](https://github.com/microsoft/vidur)).

Adding a model requires real GPU profiling for MLP and attention. A single GPU can collect compute profiles, while TP4/TP8 collective profiles require four/eight GPUs and pipeline links may require two nodes. Once CSV profiles exist, simulations run on CPU. CPU overhead profiling scripts exist but are not fully documented and tie the simulator to a serving implementation ([profiling guide](https://github.com/microsoft/vidur/blob/main/docs/profiling.md)). Runtime setup requires Python 3.10 and the project's Python environment; no Linux-only requirement is stated in the main setup.

The MLSys 2024 paper reports less than 9% inference-latency error across its validation range and reports finding a Llama-2-70B deployment in one CPU hour versus an estimated 42,000 GPU hours for deployment-based search ([paper](https://arxiv.org/abs/2405.05465)). The repository is MIT licensed ([license](https://raw.githubusercontent.com/microsoft/vidur/main/LICENSE)).

#### Foundry recommendation

Use Vidur for differential tests of dense-model scheduling and configuration search. Do not use its random-forest timing tables as evidence for hardware changes outside their profiled domain. A model shape file that “runs” is not support for MLA, sparse attention, MTP, or expert routing; those mechanisms require new ledger actions and held-out validation.

KernelSight-LM's 2026 paper reports a failure case in which mismatched Vidur profile mode produced 436% median TPOT error on its GB200 runs. That is a useful warning about profile provenance, not a general refutation of Vidur's published validation ([KernelSight-LM paper](https://arxiv.org/abs/2606.28565)). Foundry should make the profile collection mode, serving-engine version, graph/capture mode, dtype, kernel set, and admissible interpolation range part of every calibrated artifact's identity.

### 3. llm-d-inference-sim

#### Primary-source facts

llm-d-inference-sim is a Go, Apache-2.0, OpenAI-compatible and vLLM-gRPC-compatible server intended to test clients, schedulers, routing, observability, LoRA lifecycle, disaggregated prefill, and Kubernetes infrastructure without a GPU ([repository](https://github.com/llm-d/llm-d-inference-sim)). It offers deterministic or random responses, token streaming, selected vLLM Prometheus metrics, failure injection, Docker/Kind deployment, and optional real Hugging Face tokenization/rendering through a CPU vLLM sidecar.

Its latency mechanism is explicitly parameterized. Prefill is either a constant or `overhead + uncached_tokens × time_per_token`; decode is `(output_tokens - 1) × inter_token_latency`; saturation applies a configured multiplicative load factor; and P/D transfer is constant or `prompt_tokens × transfer_time_per_token` ([latency documentation](https://github.com/llm-d/llm-d-inference-sim/blob/main/docs/latency-simulation.md)). The KV subsystem hashes fixed token blocks, emits vLLM-style ZMQ lifecycle events, uses an unused-block eviction policy, and adjusts the configured prefill formula for prefix hits. Its reported cache “medium” is always GPU ([KV documentation](https://github.com/llm-d/llm-d-inference-sim/blob/main/docs/kv-cache.md)). No hardware-accuracy validation is published because hardware prediction is not its purpose.

#### Foundry recommendation

Integrate it into API and router conformance tests, not the experiment engine. It is particularly valuable for exercising KV-aware routing, P/D request fields, metrics consumers, LoRA lifecycles, and injected failures. Feeding Foundry timing into llm-d could produce a useful live demo, but agreement would only show that llm-d replayed Foundry's assumptions.

### 4. ASTRA-sim 2.2, ASTRA-sim 3.0, and Chakra

#### Primary-source facts

The released ASTRA-sim repository is an MIT-licensed C++ distributed-AI simulator. Its workload layer consumes MLCommons Chakra execution-trace DAGs and models compute/memory/network resources and collective scheduling ([repository](https://github.com/astra-sim/astra-sim), [workload documentation](https://astra-sim.github.io/astra-sim-docs/workload-layer/overview.html)). The 2.2 documentation exposes analytical, ns-3, Garnet, and custom network backends; SCALE-Sim and roofline compute backends; and one analytical remote-memory backend ([network backends](https://astra-sim.github.io/astra-sim-docs/network-backend/network-backend.html), [compute backends](https://astra-sim.github.io/astra-sim-docs/compute-backend/compute-backend.html), [remote memory](https://astra-sim.github.io/astra-sim-docs/remote-memory-backend/remote-memory-backend.html)).

The analytical network backend is not exact by default. On the project's HGX-H100 ring-all-reduce validation, reported geometric-mean errors are 20.63%, 12.01%, and 9.69% for 2, 4, and 8 GPUs. The recommended procedure empirically extracts warm-up latency and practical link bandwidth and forces the same NCCL ring algorithm used by the model ([HGX-H100 validation](https://astra-sim.github.io/astra-sim-docs/validation/hardware/gpu-validation-hgx-h100.html)). This is good evidence for a calibrated collective backend and equally good evidence against treating datasheet bandwidth as sufficient.

The June 2026 ASTRA-sim 3.0 paper proposes cache-line-sized load/store simulation, a detailed generic GPU execution model, InfraGraph infrastructure representation, and MSCCL++ custom-collective translation. Its case studies use a generic GPU and explicitly present design-space demonstrations rather than product-accuracy validation ([paper](https://arxiv.org/abs/2606.10440)). As of this research date, the official repository still says “currently at version 2.0”; the latest public tag is 2.2.0 and no 3.0 tag is published. The 3.0 paper therefore cannot yet be an implementation dependency.

Chakra defines a graph schema for compute, memory, communication, data/control dependencies, timing, and resource constraints, plus collection and analysis tools ([MLCommons project](https://mlcommons.org/working-groups/research/chakra/), [repository](https://github.com/mlcommons/chakra)). Its top-level `LICENSE.md` is Apache 2.0 ([license](https://raw.githubusercontent.com/mlcommons/chakra/main/LICENSE.md)); a stale README sentence says MIT, so pin and record the actual license file.

#### Foundry recommendation

Build a one-way Foundry-ledger-to-Chakra exporter and a results importer. Keep fields that Chakra cannot express in a namespaced metadata envelope. Never lower the canonical ledger to “compute node taking N cycles”; that loses the bytes, placement, cache, kernel, provenance, and counterfactual information needed to rerun the same experiment at another fidelity.

Use ASTRA-sim 2.2 for collective scheduling and topology questions, first with its analytical backend and then with ns-3/Garnet only when contention changes a decision. MoE, MLA, DSA, and MTP are generic actions from ASTRA's perspective. Foundry must own their semantic lowering and validate generated message sizes and dependencies.

### 5. Timeloop and Accelergy

#### Primary-source facts

Timeloop is a BSD-3-Clause C++/Python infrastructure with a fast analytical model and a mapper for dense and sparse tensor algebra over configurable compute, memory hierarchy, interconnect, and dataflow. Version 2/Sparseloop adds stochastic compressed-sparse modeling; version 3/Ruby adds imperfect factorization, spatial skews, and flattened mappings. Native builds require `isl` and `barvinok`; the project also provides a Docker-oriented installation path ([repository](https://github.com/NVlabs/timeloop), [installation](https://accelergy.mit.edu/infra_instructions.html)).

The original validation compares a NVDLA-derived design and Eyeriss over 107 DeepBench plus synthetic convolution/GEMM/GEMV kernels. The analytical model assumes the maximum of isolated compute/memory/network cycle counts and negligible pipeline stalls, an assumption appropriate to double-buffered designs but not all accelerators ([paper](https://accelergy.mit.edu/timeloop.pdf)).

Accelergy is an MIT-licensed Python plugin infrastructure that consumes architecture descriptions, component/action definitions, and action counts to produce energy reference tables, area reference tables, and total energy estimates. It is tested on Red Hat Linux, Ubuntu, and macOS and explicitly supports custom estimator plugins ([repository](https://github.com/Accelergy-Project/accelergy)). Its ICCAD 2019 validation modeled a 65 nm Eyeriss implementation: total estimated energy was within 5% of post-layout results and major component energy breakdowns were within 8% ([paper](https://accelergy.mit.edu/paper.pdf)). Those figures validate a methodology with calibrated component tables, not an uncalibrated future chip.

#### Foundry recommendation

Use Timeloop to answer “what static mapping and memory hierarchy minimizes actions for this operator?” and Accelergy to attach energy/area estimates to those actions. Do not let either tool decide request schedules, expert routes, cache eviction, or dollars per token.

The adapter should pass one stable operator/action slice at a time and return mapping, cycles, utilization, per-level accesses, energy, and area with a calibration domain. Foundry should then compose these into dynamic execution. This makes it possible to swap in a measured kernel, SCALE-Sim, or a future RTL model without changing the model compiler.

### 6. Accel-Sim and AccelWattch

#### Primary-source facts

Accel-Sim is a detailed GPU simulator with an NVBit SASS trace front end and a PTX execution-driven mode. AccelWattch is integrated in the same repository and can consume SASS/PTX simulation activity, hardware counters, or a hybrid ([repository and setup](https://github.com/accel-sim/accel-sim-framework), [license](https://github.com/accel-sim/accel-sim-framework/blob/dev/LICENSE)). The license file calls itself “BSD 2-Clause” but contains a third non-endorsement condition; record it as a nonstandard BSD-style license and obtain a legal classification rather than assigning an inaccurate SPDX identifier. Current setup targets a modern Linux distribution, C++/Python dependencies, CUDA, and a provided Ubuntu/CUDA container. A physical NVIDIA GPU is required to capture new SASS traces or hardware-counter calibration, although pre-traced workloads and hardware results are available.

The ISCA 2020 paper reports 15% performance error, a 79-percentage-point reduction in cycle error over the prior model, and validation across 80 workloads/1,945 kernel instances; it reports about 12.5 thousand simulated instructions per second in trace mode ([paper](https://people.ece.ubc.ca/aamodt/publications/papers/accelsim.isca2020.pdf), [official publication summary](https://engineering.purdue.edu/tgrogers/publication/khairy-isca-2020/)). That speed is inappropriate for full overnight serving sweeps.

AccelWattch's MICRO 2021 validation uses a Volta GV100 and 26 kernels. Depending on mode, it reports 7.5–9.2% MAPE and Pearson correlation of 0.83–0.91; a DeepBench case study reports 12.79% MAPE. Transferring the calibrated model to Pascal and Turing reports 11% and 13% MAPE, respectively ([paper](https://paragon.cs.northwestern.edu/papers/2021-MICRO-AccelWattch-Kandiah.pdf), [project overview](https://accel-sim.github.io/accelwattch.html)).

#### Foundry recommendation

Do not connect full request traces to Accel-Sim. Select only kernels whose predicted improvement drives the final business case: for example, MLA attention decode, sparse-attention gather, expert dispatch, a compressed-weight GEMM, or KV-tier DMA overlap. Simulate a small shape grid, fit a surrogate with uncertainty, and use that surrogate in F1/F2 sweeps.

Accel-Sim is most credible for modifications near an NVIDIA-like GPU with supported instructions. A radically different accelerator, new memory semantic, or custom ISA requires extensive model work and may be better represented first in Timeloop/SCALE-Sim and later in RTL. “The trace ran” is not evidence that a novel hardware path is modeled.

### 7. SCALE-Sim v3

#### Primary-source facts

SCALE-Sim is an MIT-licensed Python simulator for systolic arrays running convolution, fully connected, GEMM, and attention-like matrix operations. Version 2 provides analytically computed cycles validated against RTL, double-buffered input/filter/output memories, bandwidth- versus stall-aware modes, and cycle-level SRAM/DRAM traces. Version 3 adds multicore partitioning, hierarchical memories, row/layer sparsity, Ramulator integration, data-layout modeling, and Accelergy energy/power integration ([repository](https://github.com/scalesim-project/SCALE-Sim), [v3 paper](https://arxiv.org/abs/2504.15377)). It does not require a GPU.

The v3 paper demonstrates why memory detail matters: one reported ResNet18 comparison reverses the preferred dataflow after DRAM stalls are included. It presents architecture studies rather than broad silicon validation. “Cycle-accurate” here describes the modeled matrix array and traffic, not a full GPU, host, driver, or serving stack.

#### Foundry recommendation

Use SCALE-Sim for custom matrix-engine array size, dataflow, buffer, layout, sparsity, and DRAM questions. Lower only the matrix portions of MLA, experts, attention, and MTP heads. Keep vector operations, dynamic indexing, expert imbalance, cache policy, and serving overlap in Foundry's ledger.

### 8. gem5

#### Primary-source facts

gem5 is a BSD-3-Clause modular computer-system and processor-microarchitecture simulator written primarily in C++ and Python. It supports full-system and syscall-emulation modes, CPUs/ISAs, configurable memory systems, Ruby coherence, and Garnet networks. Building requires a C++ compiler, Python, SCons, zlib, m4, and optionally protobuf; full-system work also needs firmware, kernels, and disk images ([repository](https://github.com/gem5/gem5)).

The current full-system GPU path models AMD gfx9 ISA devices and provides Vega10, MI210/MI250X, and MI300X configurations. Efficient full-system runs prefer an x86 Linux host with KVM; using the atomic CPU on another host can slow the CPU portion by roughly 100×. Applications target ROCm/HIP and require the matching system images ([GPU full-system documentation](https://www.gem5.org/documentation/general_docs/gpu_models/gpufs)). Ruby provides detailed configurable caches, coherence, DMA, DRAM contention, and interconnect models ([Ruby documentation](https://www.gem5.org/documentation/general_docs/ruby/)).

#### Foundry recommendation

The present Apple/ARM development machine is a poor host for efficient gem5 GPU full-system experiments. Defer gem5 until a hypothesis depends on host/runtime/ISA/cache-coherence behavior that analytical action accounting cannot resolve. Likely candidates are a custom KV DMA engine, coherent CXL-style cache tier, host-device scheduling overhead, or a RISC-V control processor—not routine tensor timing.

### 9. ns-3

#### Primary-source facts

ns-3 is a GPLv2 C++/Python discrete-event network simulator supporting IP and non-IP networks, packet/protocol models, trace collection, and real-time emulation ([project overview](https://www.nsnam.org/about/)). The current tutorial supports Linux, macOS, and Linux-emulation environments and requires a C++ compiler, Python, CMake, and a build system; optional modules add dependencies ([installation tutorial](https://www.nsnam.org/docs/release/3.46/tutorial/html/getting-started.html)). ASTRA-sim already exposes ns-3 as a network backend.

#### Foundry recommendation

Use ns-3 only when packetization, transport, queueing, incast, congestion control, or P/D/KV traffic sharing changes the answer. Analytical collectives should remain the default. Prefer ASTRA's integration or an isolated Foundry adapter, cache its results, and obtain license counsel before distributing a combined product.

### 10. KernelSight-LM

#### Primary-source facts

KernelSight-LM is a June/July 2026 paper describing a Vidur-derived discrete-event serving simulator whose execution model decomposes steps into roofline kernels multiplied by learned efficiency, TP communication, and measured host-overhead terms. It models continuous batching, chunked prefill, mixed prefill/decode, and a GPU/disk prefix cache ([paper](https://arxiv.org/abs/2606.28565)).

It has two data policies. Tier A holds out the target GPU and uses datasheet specifications plus microbenchmarks from prior GPUs; Tier B adds one model-agnostic target microbenchmark sweep. Predicting held-out GB200 from A100/H200-NVL/L40S data, the paper reports 12.1% per-kernel error for Tier A and 3.8% for Tier B. Across six model families, reported median errors for TTFT/TPOT/throughput are 15.4%/12.8%/3.0% for Tier A and 14.3%/6.2%/2.7% for Tier B. Its scheduler's launch sequence/time has Spearman correlation +0.985 with vLLM in the reported setup.

The paper does not link a public implementation or software license. Its evaluated model table includes dense decoder families up to 70B; it publishes no native or validated MoE, MLA, DSA, or MTP path. Its main value to Foundry today is architectural evidence that kernel decomposition, an explicit host model, a fidelity/data-policy declaration, and serving-aware composition improve over a raw roofline.

#### Foundry recommendation

Implement these concepts in Foundry's Rust-owned F1 tier: bounded efficiency surfaces by kernel class, separate prefill/decode behavior, host overlap, and a mandatory target-data policy. Do not copy unpublished implementation details or make KernelSight-LM a roadmap dependency. Re-evaluate if the authors release code with a commercially usable license.

### 11. LLMCompass and GenZ

#### Primary-source facts

LLMCompass is a BSD-3-Clause Python artifact for static LLM inference hardware evaluation, performance-optimal mapping, and area/cost exploration. Setup uses Python 3.9, PyTorch, SCALE-Sim, SciPy, and plotting packages ([repository](https://github.com/PrincetonUniversity/LLMCompass)). Its ISCA 2024 paper reports 10.4% average operator-latency error, 4.1% average end-to-end LLM-inference error, and a 16-minute GPT-3 175B/4×A100 run including 26,400 mapper trials. The paper's hypothetical designs reach up to 3.41× performance/cost versus A100 by changing compute and memory choices ([paper](https://arxiv.org/abs/2312.03134)). It is a research artifact with seven public commits and no online serving model.

GenZ is an MIT-licensed Python analytical LLM hardware analyzer for latency and memory sensitivity. It models dtype/quantization, batching, fusion, TP with ring all-reduce, and PP with hop communication. Expert and sequence parallelism are explicit TODOs, and the repository presents no hardware-validation error summary ([repository](https://github.com/abhibambhaniya/GenZ-LLM-Analyzer)).

#### Foundry recommendation

Run both as independent F0/F1 baselines on a small frozen scenario set. They are valuable for catching arithmetic and unit errors and for comparing design-space conclusions. Do not integrate their internal schemas; Foundry needs online serving, dynamic cache/expert behavior, uncertainty, and quality/economics constraints that neither owns.

## Build-vs-integrate architecture

### The boundary

```text
Model + workload + serving policy + hardware + economics
                         |
                  Rust experiment spec
                         |
           model compiler + serving simulator
                         |
               canonical action ledger
                 /        |         \
        native F0/F1   external F2   external F3
        roofline and   ASTRA/LLM-    Timeloop, SCALE,
        surrogates     ServingSim     Accel-Sim, gem5
                 \        |         /
             calibrated results + uncertainty
                         |
          Rust cost/quality/Pareto optimizer
```

### Foundry must own

1. **Model IR and semantic lowering.** Describe layers, tensor shapes, precision, placement, weight/KV state, expert routing distributions, MLA projections, sparse-attention indices, MTP branches/acceptance, and model-quality constraints. Produce causal actions rather than a single latency number.

2. **Canonical action ledger.** Each immutable action should include identity and dependencies; request/token/phase; operation and tensor shape; bytes and source/destination memory tier; communication endpoints and collective; kernel/mapping candidate; cache allocation/hit/eviction; time/energy distribution; and provenance/calibration domain. Ledger versions must be content-addressed and migratable.

3. **Serving and workload engine.** Own arrivals, agentic session dependencies, continuous batching, chunked prefill, prefix sharing, P/D placement, MTP scheduling, admission, routing, failures, queueing, and SLOs. Third-party timing estimators should never silently change these semantics.

4. **Fidelity and uncertainty policy.** Every result must say which actions were analytical, profiled, interpolated, learned, or detailed-simulated; its admissible domain; uncertainty interval; and validation revision. The optimizer should penalize uncertainty, not rank point estimates as equally trustworthy.

5. **Economics.** Convert time, capacity, energy, silicon area/yield, memory/network/host resources, utilization, amortization, NRE, cooling, and operational margin into input/output dollars per token for the specified agentic workload. Existing architecture tools' “cost” metrics are inputs, not the business objective.

6. **Model-quality gate.** Any weight, quantization, sparsity, MLA/DSA, or MTP change must carry accuracy/perplexity/task-quality evidence. A faster different model is not a serving optimization unless quality is held to a declared constraint.

7. **Search, attribution, and experiment history.** Own multi-objective search, paired baselines, sensitivity analysis, counterfactual attribution, negative results, and reproducible manifests. The accumulated model-specific action/performance/cost corpus is a compounding moat.

### Reuse behind adapters

| Adapter | Input from ledger | Output retained by Foundry | Default use |
|---|---|---|---|
| LLMServingSim | Frozen request trace, model/topology/profile configuration | Per-request schedule/timing and batch/collective comparison | F2 differential oracle |
| Vidur | Same frozen dense scenario and supported profile | Schedule and service metrics | Secondary F2 oracle |
| llm-d | Foundry latency profile and API scenario | Protocol/metrics/router behavior | Integration tests and demos |
| Chakra/ASTRA | DAG slice with compute durations, collectives, topology | Communication completion times, contention, utilization | F2 collective/network studies |
| Timeloop+Accelergy | Tensor problem, architecture, mapping constraints, component library | Mapping, cycles, accesses by level, energy, area | F1 candidate accelerator |
| SCALE-Sim | GEMM/SpMM shape stream, array/memory/layout configuration | Cycles, stalls, SRAM/DRAM traces, energy | F3 matrix engine |
| Ramulator2 | Explicit DRAM address-vector request trace and controller configuration | Fully drained controller cycles, read latency, row outcomes, request accounting, and raw native stats | F3 irregular-memory sensitivity |
| Accel-Sim+AccelWattch | Selected executable/trace and GPU configuration | Per-kernel cycles/counters/power | F3 GPU escalation |
| gem5 | Selected runtime/device workload and system image | Host/device/memory/ISA timing | F3 full-system escalation |
| ns-3 | Flow/packet trace and network configuration | Flow completion, queues, loss/utilization | F3 fabric escalation |

All adapters should be version-pinned containers or executables with a narrow file/RPC protocol. Inputs and outputs should be content-addressed; stdout is not a data contract. Preserve raw backend output alongside normalized results. A backend failure must make an experiment incomplete, never trigger an unmarked analytical fallback.

### Adapter implementation status — 2026-07-12

The Chakra v0.0.4 interchange path is executable and content-addressed for the representable compute/collective ledger subset. The first Timeloop slice is now executable at the problem-contract boundary: [`timeloop-o-proj-bf16-decode-b1-v1.json`](../experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.json) and its generated [`problem YAML`](../experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.yaml) lower an exact Qwen3-0.6B BF16 attention output projection (`B=1`, `M=1`, `N=1024`, `K=2048`) into Timeloop v4 schema `0.4`. Native accounting reconciles 2,097,152 MACs, 4,194,304 FLOPs, 4,096 input bytes, 4,194,304 weight bytes, and 2,048 output bytes. The export is pinned as `f88f03ed0d8ae74a571d4dd21126663d3557b55263eaf87f40b50f9fe385f8bd`.

The checked [`external smoke report`](../experiments/qwen3-0.6b/timeloop-external-smoke-v1/report.json) now crosses the real frontend boundary. TimeloopFE 0.4 at commit `5603893c0ff75183b5ffd6839aba33774fc3b6fe` parses and processes the exact YAML together with a pinned adapted official architecture and mapper. Its normalized instance and arithmetic reconcile exactly to the Foundry manifest. The frontend then attempts the real native path and receives native return code 127 because `timeloop-mapper` is absent. Local probes find GMP 6.3.0 but not libconfig++, yaml-cpp, ISL, Barvinok, NTL, or polylibgmp; Docker and system package managers were deliberately not used.

This is frontend compatibility and a measured installation blocker, not an accelerator mapping. No native mapping, cycles, utilization, energy, area, calibration, performance, or cost output exists, so all such claims remain false. The adapter also rejects INT4/FP8 and other quantized types because `KernelProblem` does not yet carry group size, code representation, scale type/count, or metadata storage. Treating the passing group-8 Qwen scheme as four bits per weight would undercount its six effective bits per transformed weight. The next Timeloop step is either a version-pinned native environment or a container plus a typed quantization-storage sidecar. The current action ledger also preserves aggregate FLOPs rather than M/N/K, so operator geometry must remain pinned to the kernel problem instead of being reconstructed from the ledger.

The independent SCALE-Sim path is now native rather than contract-only. [`qwen3-glm-scalesim-v3-gemm-sweep-v1.json`](../validation/results/qwen3-glm-scalesim-v3-gemm-sweep-v1.json) pins the official MIT repository at release tag `v3.0.0`, commit `7fd972e7c650e81c77294c9433143a282235c5e7`, and executes 12/12 cases over two exact GEMMs and six array/dataflow/SRAM configurations. Qwen `o_proj` reconciles 2,097,152 MACs and 4,200,448 logical tensor bytes; the GLM architectural-BF16 routed-expert gate reference reconciles 12,582,912 MACs and 25,182,208 bytes. Raw logs are preserved and deterministic replay is byte-identical.

Within this one uncalibrated oracle, output-stationary 32×32 minimizes prefetch-inclusive cycles for both operators. It uses 2.808× fewer cycles than WS32 for Qwen and 2.925× fewer for GLM, demonstrating that mapping choice matters. The complete five-architecture base ranking is nevertheless identical across models, so this slice finds no model-specific best array. Raising WS32 SRAM from 64 KiB to 4 MiB changes neither native filter reads nor core cycles and worsens prefetch-inclusive cycles 2.043× for Qwen and 1.186× for GLM. That falsifies a generic “more SRAM helps” claim under this configuration. SCALE-Sim's dense elements do not encode BF16/NVFP4 arithmetic, CALC bandwidth is not a calibrated memory system, and cycles have no bound frequency or GPU calibration; no wall time, energy, area, whole-model, serving, or cost claim follows.

The independent [`Ramulator2 HBM3 sensitivity report`](../validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json) pins official v2.1.0 and uses a recorded AppleClang dependent-template compatibility patch with no intended simulator-semantic change. Its external runner attempts at most one request per memory tick and continues until every callback completes. Across 18 cases and two replays per case, all 1,363,968 requests receive callbacks; accepted, served, callback, controller-tick, total-read-latency, and row-outcome accounting reconcile, and paired raw stats are byte-identical. This is patched-native execution, not a pristine build.

The useful result is geometry dependence, not a promoted optimization. Sorting the same selected set by ascending logical token position changes fully drained controller cycles by **−27.744%** when one selected token represents one 32-byte transaction, but by **+59.194%** when one token expands to 36 contiguous transactions, a synthetic one-layer 1,152-byte BF16 MLA record. The cluster-64 architecture hypothesis similarly changes cycles by **−50.569%** and **+2.709%** in those geometries. Logical-token order is not a lexicographic physical-HBM-address sort, and cluster cases intentionally change the selected set. The model uses one channel/controller, one injection attempt per tick, and no refresh. It is an uncalibrated sensitivity probe, not GLM trace fidelity, GPU/kernel or wall-clock performance, end-to-end serving, quality, energy, cost, provider, or tapeout evidence.

The [`agentic token-geometry mapping screen`](../experiments/glm-5.2/agentic-mapping-screen-v1.json), generated from its pinned [`request`](../configs/glm-5.2-agentic-mapping-screen-v1.json), retargets 64 public synthetic proxy requests to GLM token counts only. In the order coupled/overlap/decoupled, request-weighted partial-residency policy counts are `64/0/0` at C1, `63/0/1` at C8, `48/0/16` at C16, `24/0/40` at C32, and `8/8/48` at C64. Every candidate full-capacity result remains uncertain—64 of 64 requests at every concurrency—so the screen does not choose a deployment. It excludes tokenizer equivalence, outputs, arrivals, tool delays, dynamic prefix behavior, context-dependent compute, network timing, quality, SLO, energy, cost, and provider performance.

The fail-closed [predictive-validity machinery](../validation/predictive_validity/gate.py) and current [gate result](../validation/results/simulator-predictive-validity-gate-2026-07-12.json) are executable, but the gate is **NOT_MET**. One prospective AArch64-NEON component pair is admitted: direction is correct, while 44.7% relative effect error fails the 15% limit. Rank correlation is unavailable, no regression was predicted, only one intervention/regime exists, and cost promotion remains false. Promotion requires precommitted exact-scope, blinded, non-overlapping hardware holdouts covering at least three interventions and two context regimes, including a predicted regression.

### What not to build now

- Do not write a second packet simulator, GPU ISA simulator, systolic-array simulator, or generic tensor mapper before a specific validated gap demands it.
- Do not port third-party Python/C++ simulators to Rust for aesthetic consistency. Process isolation makes language irrelevant; ownership of semantics and iteration speed matters.
- Do not begin with RTL or a “GLM-5.2 chip.” First identify a stable model-specific bottleneck whose conservative value survives F0, an independent F1 model, F2 serving composition, and sensitivity analysis.
- Do not optimize average tokens/s alone. The objective is delivered dollars per input/output token at a declared quality, workload mix, SLO, utilization, and demand scale.

## 30/60/90-day integration roadmap

### Days 0–30: make estimates comparable

**Build**

- Freeze action-ledger v1, calibration provenance, uncertainty fields, and adapter protocol.
- Implement native F0 operator/memory/communication accounting for one dense proxy and one small MoE/MLA-capable proxy.
- Freeze an agentic workload suite spanning short/long prompts, multi-turn prefix reuse, burst/steady arrivals, and input/output price accounting.
- Add deterministic paired-baseline reporting: tuned vLLM-like baseline versus each co-design change, with a waterfall for compute, HBM, KV, communication, queueing, energy, and amortized hardware cost.

**Integrate**

- Containerize and pin LLMServingSim; reproduce its three bundled simulator-side validations and normalize its outputs.
- Add Chakra export and ASTRA analytical-network smoke tests.
- Add one Timeloop+Accelergy dense GEMM case and one SCALE-Sim case; reconcile operation counts and memory bytes with the native ledger.
- Add GenZ and LLMCompass as non-gating arithmetic/conclusion cross-checks.

**Day-30 gate**

- The same scenario has one immutable ledger and can be replayed through at least three backends.
- Tensor operation counts, tensor sizes, and collective bytes agree to within 1% where semantics overlap.
- Results disclose calibration origin and never label extrapolated hardware as validated.
- A full fast sweep of at least 10,000 F0/F1 candidates completes overnight on local CPU hardware.

### Days 31–60: exercise the thesis, not just the framework

**Build**

- Lower MoE routing/imbalance, MLA KV compression, sparse-attention block selection, MTP acceptance/rollback, and multi-tier KV movement into explicit ledger actions.
- Implement a calibrated kernel-efficiency surface and host-overlap model inspired by KernelSight-LM, with separate prefill/decode domains.
- Add two-level surrogate fitting: detailed backend samples train F1 surfaces; held-out shapes report error and extrapolation distance.
- Add conservative cost distributions for HBM/DRAM/CXL, die area/yield, power/cooling, host/network, utilization, NRE, and demand.

**Experiment**

- Test at least four causal hypotheses on the small proxy: tiered KV, MLA-like KV reduction, expert-specific memory/compute provisioning, and one weight/dataflow change.
- For each, sweep both current GPU-like hardware and one model-specific hypothetical accelerator. Report physical upper bound, implementable estimate, uncertainty, and break-even volume.
- Escalate network-sensitive winners to ASTRA ns-3/Garnet; escalate matrix-engine winners to SCALE-Sim/Timeloop. Do not escalate losers.

**Day-60 gate**

- At least one model mechanism is represented causally across model, kernel, memory, serving, and economics layers.
- Relative improvement direction agrees across two independent estimators on at least 80% of held-out scenarios.
- The top-five design ranking has Spearman correlation at least 0.9 between fast and escalated tiers, or the report explains and models the disagreement.

### Days 61–90: produce a falsifiable investment result

**Build/integrate**

- Add Accel-Sim+AccelWattch for only the two or three kernels dominating the best candidate's value; fit held-out surrogates.
- If the winning hypothesis depends on coherent host/device or a new DMA/ISA mechanism, add one gem5 micro-workload. Otherwise explicitly defer gem5.
- Add real-hardware calibration when access becomes available: a short model-agnostic microbenchmark sweep plus end-to-end held-out request traces is higher value than a large unstructured benchmark bill.

**Deliver**

- One locked baseline and one co-designed candidate at matched quality/SLO, with p50/p95/p99, throughput, energy/token, required capacity, and fully loaded dollars/input and output token.
- An attribution waterfall showing which gains come from model change, kernel/mapping, memory system, fabric, serving policy, utilization, and financing assumptions.
- A robustness report across workload mix, arrival bursts, context distribution, cache hit rate, MTP acceptance, expert skew, hardware yield, and demand/utilization.
- A decision memo choosing among custom-silicon thesis, model-specific software/service thesis, simulator/optimizer product, or stop.

**Day-90 gate**

- Every headline improvement has a lower confidence bound, an independent cross-check, and a path to F4 validation.
- The claim is relative to a tuned current baseline, not an untuned framework default.
- The economics include NRE, idle capacity, yield, and time-to-market; no “free custom chip” assumption remains.

## Kill and pivot criteria

These criteria should be declared before viewing the final sweep.

### Kill a simulator/backend integration

- Reject an adapter if, after one focused calibration cycle, it cannot reproduce its own published artifact or preserve Foundry ledger counts.
- Reject it from the inner loop if a representative sample takes more than 24 hours or prevents at least 1,000 useful design evaluations per day; retain it only as an escalation oracle.
- Reject it for a mechanism if its abstraction removes the causal variable being tested—for example, a fixed latency profile for a memory-hierarchy change.
- Reject it as a decision oracle if held-out relative-error MAPE exceeds 15%, rank correlation falls below 0.9, or the sign of material improvements disagrees with F4 measurements more than once without an identified missing mechanism.

### Kill or narrow the custom-hardware thesis

- **Kill the 5–10× claim** if a generous physics-bound model—perfect software, ideal mapping, no queueing penalty—cannot reach 5× at matched quality. No implementation effort can recover a bound that the workload does not contain.
- **Kill per-model custom silicon** if the conservative lower bound is below 1.5× fully loaded dollars/token versus a tuned commodity stack, or if the path to at least 2× depends on simultaneously optimistic bandwidth, utilization, yield, cache hit, and model-quality assumptions.
- **Pivot to software/model co-design** if model/kernel/serving changes deliver at least 20% durable cost reduction but custom memory/compute/fabric adds less than another 20% after NRE and utilization.
- **Pivot to the simulation/optimization product** if Foundry predicts and ranks real deployments well but cannot justify tapeout economics. Accurate cross-stack capacity and cost optimization can still be valuable without manufacturing chips.
- **Stop the business** if held-out F4 error remains above 15% after two calibration cycles, if top-design ranking is unstable across realistic workload distributions, or if customers cannot provide enough model/workload detail to make model-specific optimization defensible.

### Kill a model modification

- Reject any model/weight change that violates the locked quality constraint, requires retraining cost excluded from the economics, or gains speed only on a benchmark distribution it was tuned against.
- Reject MLA/DSA/MTP/MoE changes whose benefit disappears under realistic context, acceptance, cache-hit, or expert-skew distributions.
- Reject a change if its best case is below 10% cost reduction and it adds a new kernel/runtime path with significant maintenance or correctness burden.

### Business evidence that would change this recommendation

The “Rust core + replaceable adapters” recommendation should be revisited if one external simulator demonstrates all of the following on held-out systems: native causal support for the target model mechanisms; novel-hardware prediction without per-model target profiling; online serving and agentic workloads; energy/cost outputs; less than 10% relative error and stable ranking; and an extension/licensing model compatible with a proprietary product. None of the reviewed systems currently meets that bar.

## Immediate implementation order

1. Canonical action ledger and provenance.
2. LLMServingSim differential adapter.
3. Chakra exporter + ASTRA analytical adapter.
4. Timeloop+Accelergy and SCALE-Sim operator adapters.
5. Kernel-level calibrated surrogate owned in Rust.
6. Only then, selective ns-3/Garnet, Accel-Sim/AccelWattch, or gem5 escalation.

This ordering buys evidence at each step. It also preserves the central strategic asset: Foundry can ask one model-specific question once, then refine the answer through multiple fidelity levels without rewriting the experiment or surrendering its semantics to a research simulator.
