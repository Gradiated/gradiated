# SOTA agentic inference lab capability plan

Date: 2026-07-25

## Decision

Build a thin scientific substrate around the existing director, researcher,
supervisor, GPU pool, and profiling tool. Do not build another research
workflow engine.

## Implementation status

Implemented in `research/factory/src/grad_research/science_tools/` and exposed
through the existing shared tools directory:

- paired endpoint replay with matched schedules, raw JSON/SSE evidence,
  resumability, typed success/comparability, and secret-safe endpoint metadata;
- selective first-divergence recording for tensors, logits, KV ownership,
  acceptance state, streams, operators, and kernels;
- trace-to-reproducer extraction with required exact shape and captured input;
- a deterministic exact-shape evaluator with fresh-output enforcement,
  real-consumer correctness, candidate-path proof, device-reported timing,
  compiler/profiler artifacts, and production-weighted opportunity;
- a narrow stock/candidate replacement registry;
- dependency-bound model-surgery phases and recovery curves;
- secret-free warm-workspace descriptions and a 40-entry upstream tool catalog.

The harness and GPU lifecycle were not changed. The instruments are optional,
have no standing third-party dependencies, and are presented to agents through
concise additions to the director, researcher, and supervisor skills. The
operator guide and schemas are in `research/factory/SCIENTIFIC_TOOLS.md`.

The previous direction is correct in three respects:

- deterministic code should own safety, resource accounting, repeatable
  measurement, and automatic evidence capture;
- agents should own hypotheses, experiment order, repair judgment, and close
  decisions;
- research should iterate inside a small number of durable mechanisms rather
  than creating a project for every attempt.

It needs three corrections:

1. Do not build a generic model-specific executor before an observed hot
   boundary requires it. Extract and own one hot boundary at a time.
2. Do not add a monolithic `lab-run` front door. Extend the existing thin
   tools and always preserve direct shell, SSH, and native profiler escape
   hatches.
3. Add two missing instruments before broader infrastructure: a paired
   endpoint replay harness and a first-divergence model microscope.

## Claim scope

This plan covers the research capabilities needed to discover, implement, and
measure model-specific inference improvements on NVIDIA and AMD GPUs. It does
not claim that the resulting lab will immediately produce frontier kernels or
beat a particular provider. It defines the smallest substrate that makes that
research reliable and fast.

The plan is falsified if it increases time from an agent's hypothesis to a
real GPU result, creates a new mandatory failure boundary, or does not reduce
the recurring observer, parser, layout, request-ownership, and integration
failures seen in the Gemma campaign.

## Current evidence

- The three role skills currently contribute about 8,642 words of prompt
  material. Much of the director and researcher text encodes historical
  operational failures rather than stable scientific judgment.
- The shared factory is about 10,869 Python lines. It already owns GPU
  inventory, spend, agents, traces, profiling, and notification; another
  orchestration layer would duplicate it.
- The Gemma lab has 206 project directories occupying about 1.1 TB. This
  fragments mechanism history and makes repair attempts look like independent
  research.
- `grad-profile` already provides baseline, timeline, compute-counter,
  normalization, comparison, energy, cost, and exact-shape-atlas functions.
  A second profiler wrapper is unnecessary.
- Recent Gemma failures repeatedly lacked one of two capabilities:
  production-shaped paired A/B replay, or a trace that identifies the first
  divergent tensor/state field. DFlash, grouped LM-head, fixed-M384 attention,
  contiguous KV, and several NGRAM integrations all exposed this gap.

## Minimal capability stack

### 1. Paired endpoint runner

Provide one optional runner that executes control and candidate against the
same resident model, workload, server identity, and measurement geometry.

It should:

- support in-process or restart-separated arms;
- freeze request order and seeds;
- retain raw streaming responses rather than only parsed rows;
- attach request, sequence, batch, and speculative-depth identities;
- record complete/incomplete requests, token IDs, finish reason, usage,
  latency, queueing, failures, cache counters, and candidate-path proof;
- write a comparison without deciding whether the difference is acceptable;
- resume an unstarted arm from retained state when practical.

The runner is a library and CLI used by a researcher, not a scheduler gate.
Researchers may use a project-specific runner when the shared one does not fit.

### 2. First-divergence model microscope

Add selectively enabled runtime hooks that can compare stock and candidate at
the first differing state. The initial schema should cover:

- request, sequence, layer, phase, decode step, draft depth, and tensor role;
- tensor shape, stride, dtype, scale convention, storage alias, and digest;
- optional sampled or complete tensor bytes;
- logits top-k, accepted prefix, bonus token, committed length, and next token;
- KV source and destination locations, valid lengths, and request ownership;
- CUDA stream/event identity and operator/kernel correlation.

Capture must be selective by request, layer, operation, and cycle. The default
cost is zero. A researcher turns it on only when causal localization is more
valuable than another blind endpoint run.

The microscope should have two operations:

```text
capture stock-or-candidate with a field selector
diff two captures and report the first divergent field
```

It should not contain model-specific pass/fail policy.

### 3. Trace-to-reproducer extraction

Turn a selected real runtime operation into a small runnable exact-shape
fixture containing its actual inputs, layouts, scales, output consumer, and
importance weight.

This bridges profiling and kernel work. The output is a normal directory with
Python/CUDA source and data, not a new service or serialized workflow:

```text
repro/
  metadata.json
  inputs/
  reference.py
  benchmark.py
  candidate/
```

The importance weight is the operation's non-overlapping production wall-time
share. It prevents agents from optimizing easy but immaterial kernels.

### 4. Small deterministic kernel evaluator

Adopt the useful part of modern agent-kernel harnesses: a local evaluator for
one extracted operation. It may deterministically report:

- compile success and generated-code identity;
- correctness through the real output consumer;
- warm timing distributions using the target benchmark contract;
- registers, shared memory, spills, grid waves, and optional selected counters;
- achieved fraction of an analytical speed-of-light bound;
- production-weighted endpoint opportunity.

It must not:

- choose the candidate;
- prescribe a fixed tuning sequence;
- force profiler collection;
- create a research project;
- block direct target execution through native tools.

Use the strongest incumbent available in the runtime or FlashInfer benchmark,
not only a convenient PyTorch baseline.

### 5. Hot-operation replacement seam

Add a small runtime registry that lets an extracted operation switch between
stock and candidate without rebuilding or forking the whole serving stack.
Start with only the boundaries demanded by current work:

- attention/KV;
- output projection and target-verification logits;
- quantized linear/fused epilogue;
- scheduler/graph boundary when it is directly measured.

Do not create a generic executor. If several important mechanisms later need
joint control over the same forward path, the accumulated seams become the
evidence for extracting a model-specific executor.

### 6. Model surgery and recovery runner

Use existing Hugging Face/PyTorch distributed training plus NVIDIA ModelOpt
where its pruning, distillation, QAT, speculative, or export paths fit.
Provide a thin project-local runner for:

- teacher activation/logit capture;
- a declared module replacement;
- short recovery or distillation;
- periodic recovery curves;
- checkpoint export into the real serving consumer;
- matched quality and endpoint evaluation.

Do not build a training framework. The first implementation should serve one
real Gemma intervention, such as hybrid attention placement. Generalize only
after a second mechanism reuses it.

### 7. Queryable evidence files

Keep files as the source of truth. Standardize only a small event schema and
store tabular traces as Parquet/JSONL. Query them with embedded DuckDB or
Python; do not deploy a database service, dashboard, or telemetry backend.

Every material run should be understandable from:

- `metadata.json`
- `metrics.json`
- raw stdout/stderr
- raw responses or tensor trace when selected
- profiler/compiler artifacts when selected

Enhance `grad-profile capture --tier baseline` to collect common metadata
automatically rather than introducing another required command.

### 8. Warm hardware workspaces

The resource substrate should provide retained, patchable workspaces rather
than more lifecycle logic:

- H200/H100 for Hopper production work;
- B200 for CuTe DSL, tensor memory, FP4, and Blackwell pipeline research;
- one current AMD accelerator with root profiling access;
- persistent checkpoints, source trees, images, JIT caches, and compiler
  toolchains;
- native Nsight/CUPTI, ROCm profilers, `cuobjdump`/`nvdisasm`,
  compute-sanitizer, `nvbandwidth`, and NCCL/RCCL tests.

The existing GPU pool, watchdog, and spend accounting remain the only
mandatory resource controls.

## Kernel-language policy

Do not install or prompt every researcher with every kernel framework.
Select one implementation layer from the physical need:

- Triton for rapid elementwise, reduction, layout, and moderate custom-op work;
- CuTe DSL/CUTLASS for Hopper/Blackwell tensor-core, TMA, TMEM, FP8/FP4, and
  pipeline-level control;
- FlashInfer JIT and benchmarks for attention, KV, MoE, sampling, and serving
  integration with strong incumbents;
- TileLang when the same research question genuinely needs NVIDIA/AMD
  portability;
- ThunderKittens as a source and optional substrate for tile/megakernel or
  multi-GPU work, not a universal dependency;
- native CUDA/HIP when a DSL hides the mechanism under study.

Preserve compiler output and allow the agent to move down a level when the
current abstraction prevents the design.

## Tool acquisition policy

Do not equate "available to researchers" with "installed in every image" or
"wrapped by the harness." Maintain a small catalog with three dispositions:

- **base image:** cheap, stable tools useful in almost every campaign;
- **route bundle:** pinned into a retained workspace when a hypothesis needs
  that research route;
- **reference/on demand:** source material or a temporary dependency, not part
  of the standing lab.

Before building a capability, search primary project repositories and official
CLIs. Adopt a tool when it owns a difficult generic mechanism; add a thin
adapter only for lab-specific identity, paired comparison, artifact retention,
or dollars/token. Pin a revision and preserve the upstream raw output. Do not
fork an upstream project until a measured production blocker cannot be fixed
through its public extension seams.

### Base image

| Capability | Existing tool | Lab-owned surface |
| --- | --- | --- |
| GPU/service telemetry | DCGM/NVML on NVIDIA; AMD SMI on AMD; runtime metrics | capture identity, request/model joins, cost normalization |
| Timeline and semantic ranges | PyTorch Profiler/Kineto, NVTX, Nsight Systems; ROCm Systems Profiler | `grad-profile` capture and normalized joins |
| Kernel diagnosis and safety | Nsight Compute, Compute Sanitizer, `cuobjdump`, `nvdisasm`; ROCm Compute Profiler | selected-range invocation and artifact retention |
| Artifact inspection | Perfetto Trace Processor/UI, DuckDB over Parquet/JSONL | small shared schemas and saved queries, not a service |
| Build and environment speed | `uv`, Ninja, local `sccache`, retained JIT/compiler caches | image pinning and cache identity |
| Model/checkpoint acquisition | Hugging Face `hf download` with revisions and shared cache | manifest records revision, files, and digest |

`sccache` supports `nvcc` and `hipcc`, so it is worth trialling on repeated
C++/CUDA/HIP builds in the retained workspace. It must gracefully fall back to
the compiler and expose cache-hit statistics; it must not become another build
failure boundary. Triton, CuTe JIT, PyTorch, and runtime caches remain native
and persistent rather than being copied into a new lab cache service.

### Route bundles

| Research route | Adopt or evaluate | Boundary |
| --- | --- | --- |
| Endpoint load and paired replay | Evaluate AIPerf and GuideLLM against one existing campaign fixture; retain one | The paired runner owns arm identity, raw responses, candidate-path proof, and exact control/candidate comparison. Do not maintain two canonical load generators. |
| Exact-shape kernel work | CUTLASS Profiler/CuTe DSL, FlashInfer and FlashInfer-Bench, Triton/Proton; NVBench or TritonBench where useful | Reuse incumbent/reference/timing machinery; the lab adds production trace extraction, consumer-level correctness, and importance weight. |
| Quantization and model surgery | NVIDIA Model Optimizer, TorchAO, or vLLM LLM Compressor according to the target runtime/export path | Select one primary path per intervention. Do not force checkpoints through several converters. |
| Activation intervention | NNsight for offline PyTorch/Hugging Face exploration | Useful for scanning, capture, and interventions, including vLLM integration. It does not replace serving-path capture where optimized kernels, graphs, scheduler state, and KV ownership matter. |
| Quality and behavior | Exact public GPQA/Tau-Bench implementations; `lm-evaluation-harness` for supported static tasks; Inspect AI only when its tool/multi-turn machinery saves work | Pin prompts, templates, judge/scorer, dataset revision, and runtime request options. Run focused sentinels during performance exploration and broad suites only when promotion needs them. |
| Topology and collectives | `nvbandwidth`, `nccl-tests`; RCCL/ROCm equivalents | Calibrate once per machine/topology change, then reuse results. |
| Distributed serving | Dynamo, NIXL, AIPerf, AIConfigurator/DynoSim when disaggregation or multi-node placement is an active hypothesis | Reference or integrate their measured interfaces. Do not adopt a distributed platform merely to benchmark a single-GPU mechanism. |
| Trace analysis and simulation | Holistic Trace Analysis and Perfetto; Chakra only for a demonstrated counterfactual replay need | HTA is useful for Kineto trace diff/idle/overlap but is training-oriented. Chakra must earn its place with an inference replay fidelity test. |
| Cross-vendor kernels | TileLang and AITer/ROCm libraries | Load only for an AMD or portability project; do not weaken the NVIDIA incumbent comparison. |

AIPerf is the current NVIDIA successor to GenAI-Perf and already provides
deterministic raw/trace replay, traffic distributions, SLO/goodput metrics,
parameter search, DCGM integration, and structured exports. It is also a
multi-process system with more operational surface than the paired runner
needs. GuideLLM is a smaller SLO-aware alternative with sweep, saturation,
warmup, and structured reports. The lab should run both once against a retained
endpoint fixture, compare setup time, fidelity, failure behavior, and raw-event
coverage, and keep one as the generic load engine. This is a tool-selection
experiment, not a new platform project.

The existing
`GPU_PROFILING_ECOSYSTEM_DECISION_2026-07-15.md` remains the detailed collector
inventory. This plan changes the acquisition boundary, not that decision:
compose upstream tools and own only model-aware correlation and economics.

### Reference/on demand

Keep KernelBench, TritonBench, ThunderKittens, TileLang, FlashAttention,
KernelFoundry, recent papers, vendor sample kernels, and curated repositories
such as Wafer's performance-engineering resource map searchable from the
research skills. They are candidate and technique sources, not mandatory
dependencies or proof that an optimization transfers to the active model.

Do not add W&B, MLflow, Prometheus/Grafana, Kubernetes, a remote compilation
farm, a generic experiment tracker, or another provider manager to the core
lab. Upstream tools may optionally export to them, but repository artifacts and
the existing GPU pool remain sufficient until a measured bottleneck justifies
one.

## Agent and research-state changes

Shorten the role skills to stable judgment. Move detailed operational
recovery cases into optional references or tool help so they are loaded only
when encountered.

Keep a small number of durable mechanism programmes. Each mechanism owns its
source, causal model, log, and runs. A repair or second candidate stays in the
same mechanism.

Maintain one concise campaign bottleneck index with:

- qualified endpoint and economic denominator;
- non-overlapping wall-time attribution;
- current speed-of-light gap for important operations;
- retained changes;
- unresolved causal anomalies;
- active mechanisms and their next discriminator.

The index is a human/agent-readable orientation artifact, not a second
scheduler state.

## Reliable research loop

The intended loop is descriptive, not enforced:

1. Select a production-important mechanism from current telemetry.
2. Capture or extract the minimum evidence needed to reason physically.
3. Generate several causally distinct designs when the mechanism warrants it.
4. Evaluate them in the exact-shape workbench.
5. Inspect generated code and decisive counters for the strongest candidate.
6. Promote it through the replacement seam into a paired endpoint run.
7. If semantics differ unexpectedly, use the first-divergence microscope and
   repair in the same mechanism.
8. If the change requires model recovery, invoke the surgery runner.
9. Update the compact causal model and continue or change mechanism.

No step is a harness state and agents may skip, combine, or reorder them.

## Implementation plan

### Phase 0: simplify without disrupting live research

- Let the current DFlash and grouped-head owners finish.
- Stop creating audit, packet, readiness, repair, and successor projects for
  unchanged scientific questions.
- Move historical role-skill clauses to optional references.
- Introduce a compact campaign bottleneck index.

Success signal: materially smaller agent prompts and fewer director turns per
scientific result.

### Phase 1: build the missing correctness and integration instruments

- Extract the existing DFlash and grouped-head parsers into the paired endpoint
  runner.
- Implement the first-divergence schema and selective capture hooks at the
  speculative verification and output-head boundaries.
- Replay existing immutable DFlash and grouped-head artifacts offline as
  regression fixtures.

Success signal: the tools identify the known parser and accepted-prefix
divergences without a GPU or project transition.

### Phase 2: connect production traces to kernel iteration

- Add trace-to-reproducer extraction for one Gemma hot operation.
- Adapt the FlashInfer-Bench/KernelBench style evaluator rather than writing a
  large custom framework.
- Add speed-of-light and production-importance scoring.
- Exercise Triton and CuTe DSL candidates on the same extracted operation.

Success signal: edit-to-correct-component-result on a warm GPU is under
15 minutes and a failed candidate leaves an immediately useful causal result.

### Phase 3: endpoint replacement seam

- Integrate the first extracted hot op behind a stock/candidate switch.
- Run a same-resident paired endpoint comparison.
- Add another seam only when a second important mechanism needs it.

Success signal: a positive component reaches an endpoint comparison within
one researcher turn and without a custom lifecycle controller.

### Phase 4: model recovery

- Apply one measured architecture intervention.
- Use ModelOpt or a small PyTorch/Hugging Face recovery script.
- Export into the exact serving consumer and measure recovery-versus-cost.

Success signal: architecture candidates produce recovery curves and endpoint
economics instead of terminating as `quality_unsafe`.

### Phase 5: hardware diversity and distributed inference

- Reproduce the same exact-shape and endpoint contracts on B200 and AMD.
- Add topology, collective, and KV-transfer measurements only when the target
  model requires multiple accelerators.
- Extend the replacement seams rather than introducing another distributed
  simulator as the source of truth.

## What not to build

- another scheduler, supervisor, project database, or dashboard;
- a required experiment-specification DSL;
- a generic Gemma executor before hot-boundary evidence justifies it;
- a custom profiler that duplicates Nsight, CUPTI, PyTorch, or ROCm;
- a custom distributed training framework;
- an autonomous evolutionary kernel service before the evaluator is reliable;
- mandatory NCU, tensor capture, quality suite, or full endpoint evaluation on
  every experiment;
- a fixed validation ladder encoded in the harness.

## Monitoring, not gates

Track these to detect whether the substrate helps:

- percentage of paid experiments reaching the intended scientific operation;
- warm edit-to-component and component-to-endpoint time;
- useful GPU seconds divided by claimed GPU seconds;
- number of informed iterations per mechanism;
- production-weighted speed-of-light gap closed;
- endpoint cost change per GPU-day;
- director/supervisor time as a fraction of total agent time;
- failures localized offline without a new GPU run.

Do not make these thresholds scheduler admission rules.

## Source table

Retrieved 2026-07-25.

| Source | Date/revision | Evidence type | Relevant finding |
| --- | --- | --- | --- |
| [PyTorch profiler](https://docs.pytorch.org/docs/main/profiler) | updated 2026-05-11 | official documentation | Operator shapes, stacks, device activity, and graph-like execution traces can support replay and simulation without a new profiler stack. |
| [NVIDIA Nsight Compute](https://docs.nvidia.com/nsight-compute/NsightCompute/) and [Nsight Systems](https://docs.nvidia.com/nsight-systems/UserGuide/) | current documentation | official documentation | Native tools already provide kernel counters, CUDA graph profiling, memory allocation, timelines, and CLI capture; the lab should normalize rather than replace them. |
| [NVIDIA CUTLASS/CuTe DSL](https://github.com/NVIDIA/cutlass) | CUTLASS 4.5.x, 2026-05 | official source | CuTe DSL provides low-level Hopper/Blackwell control, FP8/FP4 support, and substantially faster compilation than C++ template workflows. |
| [FlashInfer](https://github.com/flashinfer-ai/flashinfer) and [FlashInfer-Bench](https://github.com/flashinfer-ai/flashinfer-bench) | current source, 2026 | official source | JIT editing, reference checks, CUPTI timing, multiple incumbent backends, production traces, NCU support, and agent interfaces provide reusable evaluator components. |
| [FlashAttention-4](https://arxiv.org/abs/2603.05451) | 2026-03-05 | research paper | Frontier work begins from hardware rooflines and redesigns algorithm/pipeline structure around the real limiting resources; fast CuTe compilation materially improves iteration. |
| [Harness Engineering for LLM-Driven GPU Kernel Generation](https://arxiv.org/abs/2607.17979) | 2026-07-20 | research paper and code | A small official-aligned evaluator plus profiler-backed agent reasoning works; agent-assisted optimization with expert context outperformed unconstrained full-agent work. |
| [Atrex-Bench](https://arxiv.org/abs/2607.14541) | 2026-07 | research paper | Production-trace operators, production importance weights, and anti-fallback correctness matter; generation volume does not predict quality and compute-bound kernels remain the largest agent weakness. |
| [SOL-ExecBench](https://arxiv.org/abs/2603.19173) | 2026-03-19 | research paper | Speedup over a mutable software baseline is insufficient; hardware speed-of-light bounds, clock control, cache control, isolation, and correctness protections provide a better optimization target. |
| [NVIDIA Model Optimizer](https://github.com/NVIDIA/Model-Optimizer) | current source, 2026 | official source | Existing quantization, QAT, pruning, NAS, distillation, speculative, and export paths should be reused instead of building a training framework. |
| [TorchAO](https://github.com/pytorch/ao) and [vLLM LLM Compressor](https://github.com/vllm-project/llm-compressor) | current source, 2026 | primary project source | Mature PyTorch- and vLLM-oriented quantization, QAT, sparsity, KV/attention quantization, and export paths provide route-specific alternatives to ModelOpt. |
| [AIPerf](https://github.com/ai-dynamo/aiperf) and [GuideLLM](https://github.com/vllm-project/guidellm) | current source, 2026 | primary project source | Both provide reusable endpoint load generation, traffic controls, SLO metrics, and structured reports; AIPerf additionally provides deterministic trace/raw replay and broad analysis but has a larger process surface. |
| [PyTorch Kineto](https://github.com/pytorch/kineto) and [Holistic Trace Analysis](https://github.com/facebookresearch/HolisticTraceAnalysis) | current source, 2026 | primary project source | Kineto supplies low-overhead PyTorch timeline tracing; HTA adds trace comparison, idle/launch/overlap analysis, and experimental counter analysis without replacing serving-path semantics. |
| [NNsight](https://github.com/ndif-team/nnsight) | current source, 2026 | primary project source | Offline model scanning, activation capture, and intervention can accelerate architecture research, but hook-based PyTorch execution is not sufficient evidence for optimized serving-path state. |
| [NVIDIA DCGM](https://github.com/NVIDIA/DCGM), [nvbandwidth](https://github.com/NVIDIA/nvbandwidth), and [NCCL tests](https://github.com/NVIDIA/nccl-tests) | current source, 2026 | official source | Continuous health/telemetry and reusable topology/collective calibration should come from vendor tools rather than custom probes. |
| [NVIDIA Compute Sanitizer](https://docs.nvidia.com/compute-sanitizer/ComputeSanitizer/index.html) and [CUDA binary utilities](https://docs.nvidia.com/cuda/cuda-binary-utilities/) | current documentation, 2026 | official documentation | Memory/race/synchronization diagnosis and PTX/cubin/SASS/resource inspection are route-specific kernel tools, not normal benchmark stages. |
| [Perfetto](https://github.com/google/perfetto) | current source, 2026 | primary project source | Its trace UI and SQL trace processor are useful viewers/query tools; they should not become a new canonical event store. |
| [`sccache`](https://github.com/mozilla/sccache), [`uv`](https://github.com/astral-sh/uv), and [Hugging Face `hf` CLI](https://github.com/huggingface/huggingface_hub) | current source, 2026 | primary project source | Existing compiler, dependency, and model-download caches can reduce warm iteration and repeated setup without a new lab service. |
| [`lm-evaluation-harness`](https://github.com/EleutherAI/lm-evaluation-harness), [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai), and [Tau-Bench](https://github.com/sierra-research/tau-bench) | current source, 2026 | primary project source | Reuse exact, revision-pinned task implementations and structured outputs instead of recreating evaluation logic; benchmark parity remains campaign-specific. |
| [Dynamo and NIXL](https://github.com/ai-dynamo) | current source, 2026 | official source | Distributed serving, KV transfer, placement search, and replay are available upstream and should be adopted only when a measured multi-node hypothesis requires them. |
| [ROCm Systems Profiler](https://rocm.docs.amd.com/projects/rocprofiler-systems/en/latest/index.html) and [ROCm Compute Profiler](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/how-to/profile/mode.html) | current documentation | official documentation | AMD has native timeline and counter tooling that can fit the same thin normalization contract. |
| [TileLang](https://github.com/tile-ai/tilelang) | v0.1.10, 2026-05 | primary project source | A tile DSL can provide NVIDIA/AMD portability with explicit layouts, pipelining, swizzling, and generated-source inspection when portability is part of the research question. |
| [ThunderKittens](https://github.com/HazyResearch/ThunderKittens) | 2.0, 2026-01 | primary project source | Tile primitives, warp-specialized pipelines, FP4/FP8, and megakernel examples are valuable references, but the project itself favors self-contained kernels over a large shared harness. |

## Uncertainty

The recent agent-kernel papers evaluate constrained operator suites and do not
prove end-to-end serving-research superiority. Their strongest speedups may
include weak supplied baselines or unusually favorable operators. The
production-trace and speed-of-light methodology is more transferable than the
headline speedup values.

The first-divergence microscope and replacement seam are inferred from this
campaign's failures rather than validated external products. They should be
built against existing immutable Gemma artifacts before being generalized.
