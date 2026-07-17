# GPU profiling ecosystem decision

Date: 2026-07-15  
Decision: compose established collectors and viewers; build only model-aware normalization, correlation, and economics.

## Question

Is there a popular open-source library that should own the research lab's GPU profiling, or should the lab build its own?

## Decision

There is no single repository that covers model ownership, dynamic MoE FLOPs, allocator lifetime, service scheduling, CUDA Graphs, L1/L2/HBM traffic, hardware stalls, energy, and dollars per token. Do not build a replacement profiler. Adopt the strongest existing component for each evidence layer and build a thin lab-specific integration over their stable artifacts.

The integration layer is strategically important because the useful research question is not merely “which kernel is slow?” It is “which model operation, request phase, tensor geometry, routing decision, and hardware resource caused the cost, and did an intervention improve delivered dollars per token?” No generic profiler has the lab's model and economic context.

This decision is falsified if a maintained tool is demonstrated on the lab's serving workload to ingest PyTorch/Kineto, Nsight Systems, Nsight Compute, allocator, energy, and serving artifacts while preserving model/range identity and producing the required per-token comparison schema. None of the reviewed tools currently claims that scope.

## Adopt

| Component | Use | Why it belongs | Boundary |
|---|---|---|---|
| PyTorch Profiler / Kineto | operator, module, shape, stack, memory, and CUDA timeline collection | already integrated into PyTorch and supported by current serving runtimes | does not replace Nsight Compute hardware-counter analysis |
| PyTorch CUDA memory snapshots and `memory_viz` | allocation lifetime, fragmentation, allocator state, OOM provenance | clearest framework-owned memory view | cannot see every direct CUDA or NCCL allocation |
| SGLang profiling and layerwise NVTX | controlled serving captures and model-layer/tensor-shape semantics | the current GLM serving stack already exposes the profiling endpoint and `--enable-layerwise-nvtx-marker` | layerwise markers require a diagnostic non-CUDA-Graph run; production CUDA-Graph performance remains a separate control |
| vLLM profiler integration | controlled PyTorch or Nsight capture when vLLM is the tested runtime | supports server start/stop profiling, shapes, memory, stacks, FLOPs, Nsight capture, and continuous profiles | do not use profiler-on timing as benchmark truth |
| NVIDIA NVTX | stable semantic join key | supported by Nsight Systems and Nsight Compute; very small instrumentation surface | annotations must use a lab-owned vocabulary |
| Nsight Systems reports/SQLite and recipes | service timeline and programmatic summaries | vendor-supported CUDA/NVTX/OS analysis and structured export | not the source of deep cache-counter truth |
| Nsight Compute `.ncu-rep` Python interface | selected-kernel cache, roofline, occupancy, stalls, and source analysis | vendor-supported access to raw report metrics and hierarchy | requires performance-counter access and bounded replay |
| DCGM Exporter | continuous GPU health, activity, power, clocks, memory, and thermals | maintained NVIDIA Prometheus exporter; suitable for 24/7 fleet telemetry | device-level, not model-layer attribution; counter groups may conflict with deep profilers |

Kineto is already the implementation under PyTorch Profiler. Integrate through the public PyTorch interface rather than adding a separate libkineto dependency unless the lab later needs out-of-process signal-triggered collection.

## Adopt selectively

| Project | Appropriate role | Decision |
|---|---|---|
| Holistic Trace Analysis (HTA) | Kineto trace breakdown, idle/launch analysis, trace comparison, distributed overlap | evaluate as a parser/analysis dependency; useful but training-oriented and its CUPTI counter path is explicitly experimental |
| Perfetto | local browser UI for large Chrome/Kineto traces and SQL/Python trace analysis | use as a viewer and query engine, not as the canonical data model |
| Zeus | bounded energy measurement around an experiment or request phase, including NVIDIA and AMD | use where energy/token matters or DCGM sampling is insufficient; do not duplicate continuous telemetry unnecessarily |
| Triton Proton | Python/Triton context, kernel metrics, PC sampling, and intra-kernel instrumentation for custom Triton kernels | activate for custom Triton-kernel projects; it is not a whole-service profiler |
| NVIDIA NVBench | reproducible CUDA kernel parameter sweeps, cold/batch timing, and bandwidth reporting | use for custom CUDA kernel microbenchmarks |
| TritonBench | reusable PyTorch/Triton operator inputs and performance comparisons | use when a candidate can be isolated as an operator; do not transfer operator results directly to service cost |
| NVIDIA `nvbandwidth` | measured host/device and peer bandwidth capability | run once per new machine topology or after a material driver/topology change |

## Do not make canonical

- Generic FLOP counters such as THOP, ptflops, or static graph counters are useful checks but are not canonical for dynamic MoE execution, fused kernels, sparsity, or runtime routing. The lab should derive algorithmic work from exact shapes and active experts, then validate compiled work with hardware evidence.
- Triton Model Analyzer is valuable for Triton Inference Server configuration search. It does not own SGLang/vLLM internals or deep kernel/cache analysis, so adopting Triton Server merely to use it would distort the serving decision.
- Raw CUPTI should not be the starting point. Kineto, Nsight, HTA, and Proton already consume CUPTI for their respective purposes. A custom CUPTI collector is justified only by a concrete always-on signal that cannot be obtained otherwise.
- Small roofline plotting repositories should not become evidence infrastructure when Nsight Compute already provides architecture-aware hierarchical rooflines and raw report access.

## What the lab should build

Build one small vendor-neutral profiling package, not another profiler. Its responsibilities are:

1. **Capture specification:** model/runtime/hardware identity, workload, phase, warmup, profile window, profiler settings, expected artifacts, and adjacent unprofiled control.
2. **Semantic vocabulary:** request, prefill, decode iteration, layer, attention, router, expert group/GEMM, collective, KV operation, sampler, and scheduler ranges, with stable IDs and tensor/routing metadata.
3. **Artifact adapters:** parse PyTorch/Kineto JSON, PyTorch memory snapshots, Nsight Systems SQLite/reports, Nsight Compute reports, DCGM/Zeus time series, and serving benchmark output without discarding raw files.
4. **Model-aware work model:** exact algorithmic FLOPs and expected tensor bytes from runtime shapes, dtype, sparsity, active experts, and routing—not a generic static model count.
5. **Correlation:** join request/range/module/layer/kernel records using semantic IDs, timestamps, process/rank/device, CUDA correlation IDs, and kernel identity.
6. **Comparison:** produce control-versus-candidate deltas for time, HBM/L2/L1 traffic, occupancy, stalls, energy/token, throughput, SLOs, and committed-cost dollars/token, with profiler overhead clearly separated.
7. **Research summary:** automatically rank the top cost centers, regressions, unexplained time, and likely limiting resources while linking every claim to the raw artifacts.

Use Parquet or similarly queryable typed tables for normalized events and JSON for the run manifest/summary. Preserve the native reports because parsers and interpretations will improve.

## Immediate implementation order

1. Use SGLang's built-in profiling control and layerwise NVTX for the next non-CUDA-Graph semantic diagnostic; do not add another bespoke layer wrapper.
2. Preserve an adjacent production-geometry, profiler-off CUDA-Graph control for throughput and cost.
3. Parse Nsight Systems SQLite plus PyTorch/Kineto output into the common layer/range/kernel schema.
4. Once a counter-capable host is available, add the Nsight Compute report adapter and profile only the selected critical kernels/ranges.
5. Add DCGM Exporter for the long-running factory and Zeus only where bounded energy attribution adds information.
6. Trial HTA on one captured trace. Keep it if its breakdown/trace-diff APIs save work; do not bend the lab schema around it.
7. Add Proton, NVBench, or TritonBench only when a research project reaches custom-kernel work.

## Best-in-class gap audit

The selected collectors are sufficient for best-in-class measurement, but the lab still needs the following interpretation and calibration capabilities. These are core because they directly change which model, kernel, serving, or hardware intervention should be tried next.

### Exact model shape and routing truth

For every profiled request phase, preserve the actual tensor dimensions, strides/layouts, dtype/quantization, sequence geometry, active experts, tokens per expert, routing imbalance, padding, and expert residency/movement. For MoE inference, nominal model FLOPs and average top-k are not enough: the realized expert batch shapes determine Tensor Core efficiency, memory reuse, and whether a chip is a good fit.

This semantic record should also identify tensor producer/consumer dependencies and lifetimes. The analysis must calculate the critical path and overlap rather than summing overlapping kernel durations.

### Per-chip shape-performance atlas

Create a reusable measured atlas for the exact operation shapes emitted by each model on each candidate chip:

- dense GEMM/GEMV and grouped-MoE GEMM by dtype, layout, batch/token geometry, tile/schedule, and library;
- attention/MLA, routing/top-k, normalization, quantize/dequantize, KV movement, and sampling kernels;
- achieved FLOP/s, HBM/L2 traffic, occupancy, energy, and launch cost;
- empirical HBM, host-device, peer, NVLink/PCIe, and collective bandwidth/latency;
- clock, power-cap, thermal, NUMA/CPU affinity, driver/runtime, and topology identity.

Use CUTLASS Profiler or the runtime's native operator benchmarks for NVIDIA GEMM shape search, `nvbandwidth` for memory/interconnect capability, and `nccl-tests` for collective behavior. Run calibration once per materially different machine/runtime topology and reuse it; do not put the full calibration suite in every experiment.

The atlas is what lets the director ask architectural questions such as whether a different expert width, head dimension, active-expert count, quantization block, tensor layout, or parallel partition would land on substantially better hardware geometry.

### Compiler and kernel provenance

Retain the exact compiled artifact identity and code-generation path for critical kernels: source/version, compile flags, specialization keys, Triton IR where applicable, PTX, cubin/SASS, registers, shared-memory allocation, grid/block geometry, and library/kernel selection. Nsight source/SASS correlation is actionable only when the relevant line information and generated artifacts are retained.

For new custom kernels, add a fast reference-output check to the microbenchmark and run NVIDIA Compute Sanitizer or the vendor equivalent when the implementation changes memory synchronization or addressing. Sanitizers and instruction-level instrumentation do not belong in normal timing runs.

### Hardware and topology controls

Always record actual clocks, power limit, throttling reasons, thermals, ECC/fault state, PCIe/NVLink topology, CPU/NUMA affinity, and competing processes. A nominally identical GPU SKU can otherwise produce misleading chip comparisons. DCGM/NVML covers much of the state; topology and bandwidth probes establish the machine-specific ceilings.

For multi-GPU and multi-node inference, retain communication volume and collective identity per phase and compare measured application communication against `nvbandwidth`, `nccl-tests`, and fabric baselines. This separates model/parallelism problems from placement or fabric problems.

### Attribution and perturbation coverage

Every deep report should state:

- percent of GPU busy time attributed to request, phase, layer, operation, and kernel;
- unattributed GPU and host critical-path time;
- whether CUDA Graph nodes preserve semantic attribution;
- profiler-on versus adjacent profiler-off throughput/latency/energy ratio;
- which counters required replay and whether cache/clock controls differ from production;
- time spent collecting and analyzing the profile.

This prevents a detailed-looking partial trace from being mistaken for complete understanding.

### Counterfactual execution graph

For later hardware and topology design-space exploration, evaluate exporting the normalized dependency graph to MLCommons Chakra. Chakra represents compute, memory, communication, dependencies, timing, and resource constraints for simulator/replay use. It is promising for counterfactual hardware studies, but is under active development and its documented flow is training-oriented. It should not block current target-GPU experiments or become the canonical raw artifact until one GLM inference trace demonstrates useful replay fidelity.

### Optional last-resort memory tracing

Nsight counters establish aggregate cache and memory behavior, not the identity of every individual address transaction. If a specific unresolved hypothesis requires address-level memory traces or dynamic SASS instrumentation, NVBit can supply custom instruction and memory-reference tracing. NVBit is an NVIDIA research prototype, adds instrumentation overhead, and should be used only on a tiny isolated kernel after ordinary Nsight evidence fails to discriminate the decision.

## Research-speed contract

Profiling should improve experiment cadence rather than becoming a gate before every run:

1. **Every experiment:** profiler-off service measurement plus low-frequency DCGM/NVML and serving telemetry. This is the performance and cost truth.
2. **New bottleneck or unexplained result:** one short Nsight Systems/PyTorch semantic capture containing only a few representative requests or decode iterations.
3. **Promising or ambiguous critical kernel:** one selected-range Nsight Compute capture using only the sections needed to answer the current bottleneck question.
4. **Kernel development:** isolated operator microbenchmark and compiler/codegen artifacts; deep instruction tracing or sanitizer runs only when warranted.

Do not run PyTorch Profiler, Nsight Systems, or Nsight Compute continuously. PyTorch/vLLM explicitly warns that profiling slows inference and large traces can take minutes to flush. Nsight Compute may replay kernels, save/restore memory, serialize launches, adjust clocks, and purge caches; its timings are diagnostic rather than service truth. The factory should retain the GPU and queue the short diagnostic captures next to the experiment so setup/checkpoint cost is not repeated.

Operational targets, to be measured rather than assumed:

- lightweight always-on collection does not materially change profiler-off throughput;
- deep profiling consumes a small minority of campaign GPU time;
- every deep capture names the decision it is intended to discriminate;
- automated parsing returns a bottleneck summary without a model manually reading entire trace files;
- the number of credible experiments per GPU-hour rises after adoption.

## Wafer GPU performance resource-map review

The Wafer resource repository at revision `42f0908908686e70de88ddd9cb5b62dc25e9c9da` (2026-04-27) does not provide profiler code or measured benchmark data; it is a curated curriculum that maps the field from GPU architecture through kernels, compilers, serving, automated kernel generation, AMD, and distributed systems. It therefore changes prioritization, not the collector decision.

The useful implications are:

- make exact-shape kernel measurement and iteration a first-class loop using CUTLASS/NVBench/TritonBench-style controls, rather than stopping at whole-service attribution;
- retain generated source and compiler/codegen provenance (Triton IR, PTX/SASS, HIP/HSACO metadata) because optimization can occur below the framework operation;
- expose AMD ROCm capture and readiness alongside NVIDIA tools from the beginning;
- include topology and collective calibration when model changes alter parallel mapping;
- treat LLM-generated or evolutionary kernels as candidate generators whose outputs must pass exact-shape correctness and profiler-off service controls, not as a separate evidence standard.

This review would falsify the current thin-integration approach only if one of its referenced systems supplied the complete model-semantic, service, hardware-counter, energy, and economic join required by the lab. The repository instead points to specialized components across those layers, reinforcing composition. Its performance numbers are references to external projects and are not adopted as evidence for this campaign.

## Popularity and maintenance snapshot

GitHub metadata was measured on 2026-07-15 with:

```sh
gh api repos/OWNER/REPO \
  --jq '[.full_name,.stargazers_count,.forks_count,.open_issues_count,.pushed_at,.archived,.license.spdx_id,.html_url] | @tsv'
```

Stars are an adoption signal, not technical evidence, and will change.

| Repository | Stars | Last push observed | Scope |
|---|---:|---|---|
| `google/perfetto` | 6,220 | 2026-07-15 | trace UI and SQL/Python analysis |
| `NVIDIA/dcgm-exporter` | 1,803 | 2026-07-15 | Prometheus GPU telemetry |
| `pytorch/kineto` | 972 | 2026-07-15 | PyTorch GPU tracing and metrics backend |
| `NVIDIA/nvbench` | 896 | 2026-07-14 | CUDA kernel benchmarking |
| `NVIDIA/nvbandwidth` | 729 | 2026-04-08 | topology bandwidth measurement |
| `NVIDIA/NVTX` | 543 | 2026-07-14 | semantic annotations |
| `facebookresearch/HolisticTraceAnalysis` | 535 | 2026-05-29 | Kineto trace analysis |
| `triton-inference-server/model_analyzer` | 519 | 2026-07-10 | Triton Server configuration search |
| `ml-energy/zeus` | 368 | 2026-07-07 | energy measurement and optimization |
| `meta-pytorch/tritonbench` | 361 | 2026-07-15 | PyTorch/Triton operator benchmarks |

Triton Proton is developed within the much larger `triton-lang/triton` repository rather than as a standalone project.

## Sources

| Source | Evidence used | Type | Retrieved |
|---|---|---|---|
| [PyTorch Kineto](https://github.com/pytorch/kineto) | PyTorch Profiler backend, low-overhead GPU timeline, external-tool integration | project-maintainer reported | 2026-07-15 |
| [Holistic Trace Analysis](https://github.com/facebookresearch/HolisticTraceAnalysis) | temporal/kernel/idle breakdown, trace comparison, experimental CUPTI counter analysis | project-maintainer reported | 2026-07-15 |
| [SGLang benchmark and profiling guide](https://github.com/sgl-project/sglang/blob/main/docs/developer_guide/benchmark_and_profiling.md) | controlled profiling, layerwise NVTX, tensor shapes, CUDA-Graph caveat, benchmark levels | project-maintainer reported | 2026-07-15 |
| [vLLM profiling guide](https://docs.vllm.ai/en/latest/contributing/profiling/) | PyTorch/Nsight capture, profiling configuration, continuous traces, overhead warning | project-maintainer reported | 2026-07-15 |
| [NVIDIA NVTX](https://github.com/NVIDIA/NVTX) | semantic ranges supported by Nsight Systems and Compute | vendor-reported | 2026-07-15 |
| [Nsight Compute Python Report Interface](https://docs.nvidia.com/nsight-compute/PythonReportInterface/index.html) | structured `.ncu-rep` access | vendor-reported | 2026-07-15 |
| [Nsight Systems analysis guide](https://docs.nvidia.com/nsight-systems/AnalysisGuide/index.html) | CLI reports, NVTX-qualified kernel summaries, CUDA correlation fields | vendor-reported | 2026-07-15 |
| [NVIDIA DCGM Exporter](https://github.com/NVIDIA/dcgm-exporter) | Prometheus export over DCGM | vendor-reported | 2026-07-15 |
| [Zeus](https://github.com/ml-energy/zeus) | programmatic/CLI energy measurement, NVIDIA/AMD and other-device support | project-maintainer reported | 2026-07-15 |
| [Perfetto](https://github.com/google/perfetto) | large-trace UI and SQL/Python analysis | project-maintainer reported | 2026-07-15 |
| [Triton Proton](https://github.com/triton-lang/triton/tree/main/third_party/proton) | Triton context, kernel metrics, PC sampling, instrumentation | project-maintainer reported | 2026-07-15 |
| [NVIDIA NVBench](https://github.com/NVIDIA/nvbench) | CUDA parameter sweeps, timing, bandwidth, cache-state controls | vendor-reported | 2026-07-15 |
| [NVIDIA nvbandwidth](https://github.com/NVIDIA/nvbandwidth) | GPU topology bandwidth measurement | vendor-reported | 2026-07-15 |
| [Triton Model Analyzer](https://github.com/triton-inference-server/model_analyzer) | Triton Server configuration search, reports, QoS constraints | vendor-reported | 2026-07-15 |
| [NVIDIA CUTLASS](https://github.com/NVIDIA/cutlass) | exact-shape GEMM kernel profiling, verification, parameter search, bytes, FLOPs, bandwidth, and throughput | vendor-reported | 2026-07-15 |
| [NVIDIA NCCL tests](https://github.com/NVIDIA/nccl-tests) | collective correctness, latency, algorithm/bus bandwidth, topology partitions, CUDA Graph and JSON support | vendor-reported | 2026-07-15 |
| [NCCL performance and tuning](https://docs.nvidia.com/deeplearning/nccl/archives/nccl_2307/user-guide/docs/troubleshooting/performance_and_tuning.html) | topology, `nvbandwidth`, fabric isolation, affinity, and NCCL tuning guidance | vendor-reported | 2026-07-15 |
| [MLCommons Chakra](https://github.com/mlcommons/chakra) | graph representation of compute, memory, communication, dependencies, timing, and resource constraints | project-maintainer reported | 2026-07-15 |
| [Chakra trace collection and simulation](https://github.com/mlcommons/chakra/wiki/Chakra-Execution-Trace-Collection-%E2%80%90-A-Comprehensive-Guide-on-Merging-PyTorch-and-Kineto-Traces) | PyTorch execution/Kineto trace joining and simulator conversion | project-maintainer reported | 2026-07-15 |
| [NVIDIA NVBit](https://github.com/NVlabs/NVBit) | dynamic SASS instrumentation, instruction and memory-reference tracing; research-prototype status and overhead | vendor-reported | 2026-07-15 |
| [Nsight Compute Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html) | counter replay, collection overhead, serialization, clock and cache controls | vendor-reported | 2026-07-15 |
| [NVIDIA Compute Sanitizer](https://docs.nvidia.com/compute-sanitizer/ComputeSanitizer/index.html) | memory, race, initialization, and synchronization correctness checks for CUDA kernels | vendor-reported | 2026-07-15 |
| [Wafer GPU performance engineering resources](https://github.com/wafer-ai/gpu-perf-engineering-resources/tree/42f0908908686e70de88ddd9cb5b62dc25e9c9da) | revision `42f0908`; field coverage map spanning architecture, kernels, compilers, profiling, AMD, serving, generated kernels, and distributed systems; no native profiler implementation or campaign measurement | project-maintainer curated index | 2026-07-15 |

## Bottom line

Reuse almost all collection and visualization. Own the semantic schema, exact model work equations, artifact joins, comparison logic, and dollars-per-token interpretation. That is the smallest build and the part most likely to improve research quality.
