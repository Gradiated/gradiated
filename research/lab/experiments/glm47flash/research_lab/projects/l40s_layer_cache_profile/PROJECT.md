# L40S layer and cache profile

## Question

Can we attribute shared-memory, L1, L2, and HBM behavior to a representative GLM-4.7 Flash layer/component on L40S, and does measured cache traffic or SM underfill support the existing 64-to-16-expert co-design opportunity?

## Why now

The campaign has endpoint throughput, power, memory, and operator traces, but it does not yet have successful L1/L2/HBM performance-counter evidence tied to model geometry. The strongest open model/chip hypothesis is that 64-way routing creates small grouped-GEMM shapes and an approximately 324 MiB sparse layer that cannot reside in the 96 MiB L2, while a 16-expert layer is approximately 81 MiB and raises expected nonempty expert work. This project should measure that mechanism instead of adding a general observability framework.

## Research scope

Deliver decision-relevant measured evidence in this turn. Start with the cheapest target check on a Nebius L40S: locate Nsight Compute, record tool/driver/GPU versions, and run a tiny deterministic CUDA or PyTorch kernel to verify that performance counters are permitted and identify the supported metric/section names. Do not transfer the checkpoint or spend time instrumenting the full server before this check.

If counters are available, continue in the same allocation to the smallest executable exact-shape proxy for the current GLM-4.7 Flash MoE decode geometry. Compare stock 64 experts/top-4 with a synthetic 16-expert/top-4 geometry while holding routed work, precision, token geometry, warmup, and repetitions as comparable as the available kernel permits. Prefer existing campaign scripts and installed runtime components over building a new framework. Use NVTX ranges when they materially improve attribution, but kernel names plus exact input shapes are acceptable.

Capture the raw `.ncu-rep` and a compact machine-readable summary containing, where supported: kernel/grid/block and grouped-GEMM shape; static/dynamic shared memory; registers and achieved occupancy; active/eligible warps and major stall classes; L1 requests/hit rate/bytes; L2 sectors, hit rate, read/write bytes, and misses reaching device memory; HBM read/write bytes and bandwidth; Tensor Core or relevant instruction utilization; kernel duration; active-expert/group-size distribution; and whether profiler replay changes timing. Use the target's supported Nsight Compute sections rather than repeatedly retrying hard-coded metric names.

If the exact production grouped-GEMM is not callable without the checkpoint, use the closest exact-shape executable proxy and label the result synthetic component evidence. If counters are denied, retain the exact typed error, test at most one materially different safe permission/tool route, and close or redirect; do not spend the turn repairing generic observability. Existing PyTorch/Systems traces may be used only to improve layer attribution, not as a substitute for cache counters.

The profiler should answer which data crosses L2/HBM by kernel or range and how much; do not claim it observes the identities of individual cache lines or tensor values. Nsight replay timing is diagnostic and must not be used as endpoint throughput.

## Provider contract

This project may own one Nebius L40S diagnostic allocation only when authenticated inventory is empty and no other project owns a provider mutation. Maximum metered experiment spend is `$0.40`, maximum allocation lifetime is `1,200` seconds, and cleanup must verify zero project-owned instances and disks. A live provider owner means wait or complete zero-cost preparation, not race it. Do not expose credentials.

## Decision

Return one of:

1. measured counter evidence that supports or falsifies a specific model/chip intervention and names the next cheapest endpoint falsifier;
2. a measured profile showing another kernel/layer is the dominant cache or occupancy opportunity; or
3. a typed target-provider counter limitation after at most two distinct routes, with a concrete alternate profiling venue/tool.

Tool installation, permission probing, scripts, and documentation without one of those outcomes are not completion. Keep the research log to the result, evidence paths, interpretation, and next action.
