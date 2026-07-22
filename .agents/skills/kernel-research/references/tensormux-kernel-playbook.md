# TensorMux-derived kernel engineering playbook

## Source and scope

Derived and adapted from [tensormux/kernel-skills](https://github.com/tensormux/kernel-skills), commit `7b7337a123f8711aa8e3d0452351d8fd30dde4b7`, inspected 2026-07-22. Upstream is MIT licensed: copyright 2026 kernel-skills contributors. This reference condenses the parts relevant to model-inference research; consult upstream when a task needs its longer implementation examples.

The upstream library contains focused CUDA, Triton, inference, quantization, portability, correctness, and integration playbooks. Use this routing table instead of loading every topic:

| Problem | Relevant upstream playbooks |
| --- | --- |
| Registers, occupancy, launch geometry | `cuda/choose-launch-configuration`, `triton/optimize-triton-block-parameters` |
| HBM/L2/coalescing | `cuda/optimize-global-memory-access` |
| Shared-memory reuse or bank conflicts | `cuda/optimize-shared-memory-tiling` |
| Tiling and split/persistent work | `patterns/choose-tile-size-and-work-partitioning` |
| Elementwise or epilogue fusion | `patterns/fuse-elementwise-ops` |
| Attention and paged KV | `triton/write-triton-attention-kernel`, `inference/write-triton-kv-cache-append-kernel` |
| Prefill versus decode | `inference/optimize-prefill-vs-decode-kernels` |
| FP8/INT8 representation | `quantization/write-fp8-kernel`, `quantization/debug-quantized-kernel-accuracy` |
| Runtime integration | `inference/write-vllm-custom-op-integration-plan`, `inference/write-tensorrt-plugin-integration-plan` |
| Correctness and test design | `cuda/debug-cuda-kernel-correctness`, `patterns/write-kernel-test-plan` |
| NVIDIA-to-AMD/Triton portability | `portability/port-cuda-kernel-to-hip`, `portability/port-cuda-kernel-to-triton` |

## Initial decision surface

Gather only facts that change the design:

- exact tensor dimensions, strides, alignment, contiguity, dtype, scale shape, and output contract;
- operation phase: prompt prefill, decode, cache append, sampling, or offline conversion;
- target architecture, SM/CU count, warp or wavefront width, register file, shared-memory capacity and carveout, L2, HBM bandwidth, tensor formats and supported instructions;
- current kernel symbol and launch geometry, registers/thread, shared memory/block, grid size/waves, and whether CUDA graphs or dynamic shapes constrain launch;
- baseline warm latency distribution and whole-request relevance;
- trusted numerical reference and tolerances.

Do not start from a fashionable optimization. Start from the cheapest experiment that can distinguish compute, memory, latency, launch, synchronization, or underfilled-grid limits.

## Roofline and phase classification

Estimate arithmetic intensity as useful FLOPs divided by compulsory bytes. Compare it with the target chip's compute-to-bandwidth ratio.

- Compute-bound: focus on tensor-core eligibility, instruction mix, accumulator use, math decomposition, and pipeline stalls. High occupancy may be unnecessary.
- Bandwidth-bound: focus on bytes removed, coalescing, vector width, cache reuse, layout, and fusion. Occupancy only needs to hide latency.
- Latency/launch-bound: fuse proven adjacent work, use CUDA graphs or persistent execution, or increase work per launch without creating a larger memory or register penalty.
- Underfilled grid: change work partitioning, split work, batch compatible shapes, or use persistent scheduling. A faster block cannot occupy idle SMs.

Prefill and decode are different workloads. Prefill usually has large M and greater tensor-core reuse; decode often has small M, weight/KV bandwidth pressure, and launch sensitivity. Do not transfer one tile, batch, or kernel family between them without measurement. Include phase in autotune keys and attribution.

## Launch, occupancy, and register rules

Compute resident blocks from the minimum of register, shared-memory, thread/warp, and hardware block limits. Use actual compiler or profiler register counts; source estimates are unreliable. Include grid waves and tail effects—high theoretical occupancy does not help when the grid is too small or badly imbalanced.

Treat compiler register caps and launch-bound hints as experiments with a cost, not free occupancy controls. Forced register reduction may spill to local memory and raise L2/DRAM traffic enough to overwhelm extra CTAs. Always measure spills and latency alongside occupancy. This rule directly applies to `maxnreg`, `__launch_bounds__`, Triton warp count, and tile reductions.

Prefer warp-multiple block sizes and map the innermost thread dimension to stride-1 memory. Check partial tiles, alignment, and whether changing block size increases tail waste. Persistent kernels are useful for repeated small or irregular work, but they add queue/termination and fairness complexity.

## Tiling and memory

For each candidate, estimate:

- shared memory per block, including every pipeline stage;
- accumulator and live-state register demand;
- expected resident blocks/warps;
- useful lanes in boundary tiles;
- grid waves across the device;
- bytes loaded/stored and expected reuse in shared memory or L2;
- vector-load alignment and bank-conflict risk.

Large tiles increase reuse but can collapse residency or spill. Small tiles increase waves and reduce live state but repeat loads and synchronization. Select candidates from this trade, then verify compiled resources and measured counters.

Use shared memory only when reuse amortizes loads or it enables a required inter-thread exchange. Pad or swizzle only after identifying bank conflicts. For a streaming one-pass kernel with no reuse, shared-memory tiling is usually unnecessary.

For multi-stage algorithms, account for intermediate writes, rereads, synchronization, and recomputation. Ensure the stage boundary actually ends the unwanted live range; syntactically splitting code does not guarantee the compiler shortens it.

## Fusion

Fuse when adjacent operations share a producer-consumer chain, the intermediate has no other consumer, and avoided traffic or launch overhead is material. Estimate unfused and fused bytes before implementation and include L2 residency in the estimate.

Reject or reconsider fusion when it introduces a reduction/synchronization boundary, changes layout incompatibly with the real consumer, raises register pressure enough to reduce throughput, or duplicates an existing compiler/library fusion. GEMM epilogue fusion should use the runtime's CUTLASS/cuBLASLt/TensorRT epilogue mechanism where possible.

Validate the fused output through the unchanged downstream consumer before timing. Explicitly bind dtype casts and quantization points; moving a cast or scale changes semantics.

## Attention and KV-cache invariants

For online-softmax attention, maintain running max, normalization sum, and output accumulator in sufficient precision. When the running max changes, rescale both the prior sum and output before adding the new tile. Apply causal and boundary masks before the max reduction. Invalid K positions must contribute `-inf` scores, while invalid V values contribute zero.

For GQA/MQA, derive KV head index from query head and group size; never replicate or stride K/V as if it had the query-head count unless the implementation explicitly materializes that representation.

For paged KV append, bind the exact cache layout, block size, slot mapping, source strides, scale convention, and CUDA-graph padding behavior. A negative slot must no-op before any load. Build and test slot mappings at block boundaries and across multiple requests. K/V volume in decode can be too small for kernel inner-loop optimization to matter; measure full decode-loop impact.

Use FlashAttention, FlashInfer, or a runtime-native kernel for standard supported semantics. A custom attention kernel is justified by unsupported model geometry, masking, layout, precision, or measured residual—not by generic interest.

## Quantized kernels

Bind format and scale semantics exactly: E4M3 versus E5M2, per-tensor/per-token/per-channel/per-block scaling, zero and nonfinite handling, saturation mode, scale dtype, accumulation dtype, and output dtype/layout.

For FP8, apply scale in higher precision before conversion and guard zero or tiny amax values. Keep accumulations at the precision required by the numerical contract. Distinguish weight representation from KV representation; “FP8 endpoint” is insufficiently specific.

Diagnose error spatially and by operation: saturation at range extremes, systematic row/column errors from wrong scale indexing, outliers from reduction order, and large relative errors near zero. Report max absolute error, relative L2, cosine or task-relevant metric, saturation fraction, and nonfinite count as appropriate. A self-authored encode/decode roundtrip does not prove compatibility with the runtime consumer.

## Correctness and boundary tests

Use the smallest failing case and classify its pattern before changing code. Check index formulas, strides, transpose/layout assumptions, shared-memory synchronization, warp masks, uninitialized state, and launch arguments.

The discovery set should be small but discriminating:

- the exact production shape and layout;
- just below, at, and just above important tile/block boundaries;
- odd or non-power-of-two dimensions where allowed;
- empty/padded/no-op slots and partial final tiles;
- extreme, zero, tiny, large, and nonfinite values when the operator contract allows them;
- deterministic repeats when races are plausible.

Use a known-good high-precision or library reference. Consume the complete output and synchronize timing correctly. Run compute-sanitizer or race checking only when evidence points to memory/race defects; it is not a prerequisite to every performance experiment.

## Benchmark and profiler contract

Compile/autotune first, then benchmark warm steady state with profiler disabled. Use enough warmups and repetitions to establish variance, median, and a robust percentile. Synchronize correctly with CUDA events or equivalent; do not include asynchronous enqueue time as kernel latency.

Benchmark exact production shapes, plus only the nearby shapes needed to understand robustness. Compare against the strongest supported library/runtime baseline. Report achieved bandwidth or FLOP/s only with the correct dtype-specific theoretical denominator and useful-work definition.

Use Nsight Compute, Nsight Systems, ROCm tools, or compiler metadata only after the baseline identifies the decision. Collect the smallest metric set that tests the hypothesis: registers/spills and occupancy; tensor or instruction activity; L1/L2/DRAM throughput and hit rates; eligible/issued warps and dominant stalls; grid waves; shared-memory conflicts; launch and synchronization gaps. Counter collection changes execution and is not endpoint timing.

## Runtime integration

For vLLM, SGLang, TensorRT-LLM, or another serving runtime, locate the exact model-runner call site and preserve:

- paged KV and cache-layout semantics;
- CUDA-graph capture and fixed/padded batch behavior;
- dynamic shapes and supported dtype dispatch;
- tensor/pipeline/expert parallel rank behavior;
- streams, events, and synchronization;
- workspace lifetime and allocator ownership;
- registration, serialization, engine rebuild, and fallback behavior;
- model/tool output semantics.

Keep a known-good fallback until the candidate proves itself. Integration is complete only when the runtime invokes the candidate under the exact workload and an endpoint measurement confirms the expected effect.

## Compact evidence handoff

Record:

1. exact source/runtime/driver/hardware identities;
2. operation, phase, shapes, strides/layouts, dtypes/scales, and consumer;
3. physical hypothesis and predicted counter movement;
4. baseline and candidate warm timing distributions;
5. correctness/error evidence and candidate-path proof;
6. compiled registers/shared memory/spills and decisive profiler counters;
7. endpoint effect, energy, and price-normalized effect when promoted;
8. what the result falsifies and the next distinct experiment.

Do not claim “optimal,” “bandwidth-bound,” “compute-bound,” or transferable endpoint gain without the corresponding measurement.

## Upstream license

MIT License

Copyright (c) 2026 kernel-skills contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
