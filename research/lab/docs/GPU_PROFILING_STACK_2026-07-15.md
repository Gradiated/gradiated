# GPU profiling stack for model–chip co-design

Date: 2026-07-15  
Decision: use framework semantics plus vendor profilers; do not build a new low-level profiler.

## Decision

Nsight is the right source of NVIDIA hardware truth, but it is not a complete model profiler. Use a small, composable stack:

1. **Continuous, low-overhead telemetry:** DCGM/NVML plus serving counters for power, clocks, utilization, memory occupancy, throughput, latency, batch geometry, and request shape.
2. **Model semantics and allocation ownership:** PyTorch Profiler and PyTorch CUDA memory snapshots, annotated with model/module/routing context.
3. **Whole-request timeline:** Nsight Systems with NVTX ranges around request, prefill/decode, layer, attention, MoE routing, expert GEMMs, collectives, and custom kernels.
4. **Selected-kernel hardware analysis:** Nsight Compute for only the important ranges/kernels, using roofline, memory workload, occupancy, scheduler/warp-state, and source-counter sections.

This division is deliberate. No single current tool clearly and reliably answers all of these questions, and Linux CPU profilers such as `perf` or eBPF do not expose detailed NVIDIA SM/cache behavior.

The failed Nebius L40S counter capture was a venue/driver-access failure, not evidence that Nsight is the wrong profiler. Exact Nsight Compute counter work requires a host where performance-counter access is available.

## What each tool can establish

| Question | Primary tool | Evidence produced | Important limitation |
|---|---|---|---|
| Which model operation owns time? | PyTorch Profiler | operator/module time, shapes, stacks, device kernels | framework overhead and attribution can become ambiguous after fusion/compilation |
| Who allocated memory, when, and why is memory fragmented? | PyTorch CUDA memory snapshot | allocation/free/OOM stacks, allocator segments and blocks, live allocations | sees PyTorch allocator memory, not all direct CUDA/NCCL allocations |
| When did CUDA allocations, copies, launches, gaps, and synchronization occur? | Nsight Systems | CPU/GPU timeline, CUDA API, memory events, kernels, NVTX projection | timeline collection can add overhead; it does not expose full per-kernel cache-counter detail |
| What moved through L1/L2/HBM and where are cache misses or bandwidth limits? | Nsight Compute | cache hit/miss behavior, requests, transfers, throughput, roofline ceilings | replay can require several passes and perturb caches/timing |
| Why is a kernel below peak? | Nsight Compute | occupancy, register/shared-memory limits, warp stalls, scheduler activity, source/SASS counters | analyze selected kernels, not every kernel in every production request |
| Is the GPU healthy and busy over hours? | DCGM/NVML | device-wide SM/Tensor/DRAM activity, power, clocks, thermals | coarse and device-wide; it cannot attribute behavior to a layer or kernel |

## Memory vocabulary

Researchers must keep these measurements separate:

- **Allocated/reserved bytes:** allocator ownership and fragmentation, obtained from PyTorch memory history/snapshots.
- **Live device memory:** total bytes currently resident, cross-checked against device/NVML memory usage because non-PyTorch allocations may be invisible to the PyTorch allocator.
- **Memory operations over time:** allocations, frees, copies, page migrations, and launch timing, obtained from Nsight Systems.
- **Memory traffic:** bytes actually read/written at L1, L2, and device memory during kernel execution, obtained from Nsight Compute counters.
- **Working-set fit:** an inference from traffic, hit rates, reuse, tensor sizes, and phase/layer boundaries—not from allocated bytes alone.

For the GLM-4.7 Flash L40S campaign, the decisive questions are whether expert weights or activations reuse L2, whether grouped expert GEMMs are Tensor Core/occupancy limited, and how much HBM traffic each generated token induces. Allocator snapshots cannot answer those questions by themselves.

## FLOP vocabulary

Record four distinct quantities rather than one ambiguous `FLOPs` field:

1. **Algorithmic FLOPs:** derived from exact runtime tensor shapes, active experts, sequence geometry, and operation definitions.
2. **Estimated framework FLOPs:** optional output from PyTorch or DeepSpeed profilers. PyTorch's built-in estimator covers only matrix multiplication and 2-D convolution, so it is incomplete for MoE routing, custom fused operations, and many Triton kernels.
3. **Executed instructions/work:** vendor counter evidence from Nsight Compute, separated by precision and Tensor/Core pipeline where available.
4. **Achieved FLOP/s and percent of roofline:** measured kernel time combined with the appropriate work definition and roofline ceiling.

For this lab, exact model-aware analytical equations are the canonical algorithmic-FLOP source. Framework estimators are a convenience check; hardware counters validate what the compiled kernels actually executed.

## Minimal capture sequence

Use the following bounded sequence for a new optimization candidate:

1. Run an unprofiled, warmed control and candidate using the same workload; this is the latency, throughput, energy, and cost truth.
2. Run one semantic PyTorch profile and memory snapshot on a small representative window.
3. Run one Nsight Systems timeline with NVTX and CUDA memory tracking when allocation timing is relevant.
4. Rank kernels/ranges by total time and optimization relevance.
5. Run Nsight Compute only on the top 5–20 kernels or selected NVTX ranges. Preserve the raw `.ncu-rep`; parse the report rather than scraping terminal text.
6. Re-run the unprofiled control and candidate after profiling. Nsight replay timings are diagnostic and must not be used as service throughput.

Do not collect every metric on every experiment. Deep profiling is triggered by a concrete bottleneck question or a result worth explaining.

## Common normalized record

Build only a thin normalizer over existing artifacts. Each layer/range/kernel record should support:

- model, commit, hardware, clocks/power cap, runtime, dtype/quantization, workload, phase, batch/concurrency, context/output lengths;
- request/range/module/layer/kernel identity and exact tensor shapes;
- parameters read, live/reserved activation bytes, analytical FLOPs, active-expert/routing counts;
- kernel duration, launch count, achieved occupancy, registers/thread, shared memory/block, warp-stall distribution;
- L1/L2/device-memory read/write bytes and hit rates where counters support them;
- Tensor/Core utilization, arithmetic intensity, achieved throughput, and percent of the applicable roofline;
- artifact links to the raw PyTorch trace/snapshot, `.nsys-rep` or exported SQLite, `.ncu-rep`, profiler command, and adjacent unprofiled benchmark.

NVTX is the join key between model semantics and vendor timelines. Keep the range vocabulary stable across NVIDIA and AMD runs.

## Automation boundary

Nsight Compute provides a Python report interface for reading `.ncu-rep` files, and Nsight Systems exports reports/SQLite and has Python recipes. Use those interfaces to generate comparison tables and bottleneck summaries.

CUPTI is the low-level NVIDIA API underneath profiler capabilities. It is appropriate only if the lab later needs a selective always-on collector that the existing tools cannot provide. Starting with CUPTI would add substantial tool-building work without making today’s analyses clearer.

DCGM is appropriate for continuous device-level sampling, but its profiling metric groups can conflict with other counter users. Pause or disable conflicting DCGM profiling fields during Nsight Compute captures, then restore them.

## AMD parity

Keep the semantic and normalized schemas vendor-neutral. On AMD:

- retain framework profiling and allocation instrumentation;
- use ROCTx in place of NVTX for semantic ranges;
- use `rocprofv3` for traces/counters;
- use ROCm Compute Profiler for speed-of-light, memory charts, and hierarchical L1/LDS/L2/HBM rooflines.

Do not compare nominal counter names blindly across vendors. Normalize to questions such as bytes transferred, achieved bandwidth, cache reuse, occupancy/resource limit, and percent of an architecture-specific ceiling.

## Evidence and limitations

All capability claims below are vendor/framework documentation unless noted.

| Source | Relevant evidence | Retrieved |
|---|---|---|
| [NVIDIA Nsight Compute](https://docs.nvidia.com/nsight-compute/NsightCompute/index.html) | memory-workload analysis, occupancy, rooflines, source counters | 2026-07-15 |
| [Nsight Compute Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html) | metric interpretation, cache/memory analysis, replay behavior | 2026-07-15 |
| [Nsight Compute Python Report Interface](https://docs.nvidia.com/nsight-compute/PythonReportInterface/index.html) | structured access to ranges, actions, metrics, source, and SASS in reports | 2026-07-15 |
| [NVIDIA Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html) | CUDA timeline, NVTX projection, CUDA memory-usage collection and overhead | 2026-07-15 |
| [PyTorch Profiler](https://docs.pytorch.org/docs/2.12/profiler.html) | operator/module/device profiling, memory, stacks, shapes, limited FLOP estimation | 2026-07-15 |
| [PyTorch CUDA memory snapshots](https://docs.pytorch.org/docs/stable/torch_cuda_memory.html) | allocator history, memory visualization, allocation provenance, non-PyTorch blind spots | 2026-07-15 |
| [DeepSpeed FLOPs Profiler](https://deepspeed.readthedocs.io/en/latest/flops-profiler.html) | module-level parameter, latency, MAC, and FLOP estimates | 2026-07-15 |
| [NVIDIA CUPTI overview](https://docs.nvidia.com/cupti/overview/overview.html) | low-level activity, callback, range, PC-sampling, SASS, and PM-sampling APIs | 2026-07-15 |
| [NVIDIA DCGM feature overview](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html) | continuous device-level profiling fields and sampling constraints | 2026-07-15 |
| [NVIDIA DCGM profiling API](https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-profiling.html) | profiling metric-group conflicts and restoration after other profiling tools | 2026-07-15 |
| [ROCm Compute Profiler](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/develop/what-is-rocprof-compute.html) | AMD speed-of-light, memory-chart, and hierarchical roofline analysis | 2026-07-15 |
| [rocprofv3](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/how-to/using-rocprofv3.html) | AMD traces and multi-pass performance-counter collection | 2026-07-15 |

## Bottom line

Use Nsight; it is the right deep NVIDIA profiler. Make it understandable by joining it to model-aware NVTX ranges, PyTorch allocation history, and exact model equations. The useful lab investment is a thin normalization and comparison layer over those artifacts—not another profiler.
