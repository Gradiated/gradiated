---
name: kernel-research
description: "Design, debug, integrate, optimize, and measure production GPU kernels for CUDA, Triton, ROCm/HIP, quantized inference, and serving runtimes. Use for exact-shape kernel work, attention/KV-cache operations, FP8/INT8 paths, fusion, launch/tile tuning, correctness failures, vLLM custom ops, TensorRT plugins, or kernel-level accelerator analysis."
---

# Kernel research

Produce a correct, exact-consumer GPU result and improve the campaign endpoint—not merely an attractive standalone kernel. Use the target model geometry, production workload, runtime source, and accelerator as the optimization scope.

Read [references/tensormux-kernel-playbook.md](references/tensormux-kernel-playbook.md) for the relevant task before designing the candidate. It distills the TensorMux kernel-skills library and records its source pin and license.

## Bind the real problem

Establish the exact operation, prefill/decode phase, shapes, strides/layouts, dtypes and scale conventions, target GPU, current producer and consumer symbols, baseline implementation, and whole-request relevance. Trace the output into its actual downstream consumer. A synthetic tensor with a convenient layout is not representative when the production consumer expects another layout or quantization contract.

Check whether current cuBLAS/cuBLASLt, CUTLASS, FlashAttention, FlashInfer, vLLM, SGLang, TensorRT-LLM, Triton, or ROCm already supports the operation. Prefer adapting a proven implementation. Write a custom kernel only when the exact shape or semantics are unsupported, or telemetry shows a credible material gap.

## Form a physical hypothesis

Calculate useful FLOPs, compulsory bytes, arithmetic intensity, grid waves, tail waste, and the likely roofline regime. Combine these with measured registers/thread, spills, shared memory, occupancy, tensor activity, L2/DRAM traffic, and stall reasons. Distinguish prefill from decode; they commonly require different decompositions.

Name one causal change and the counter movement it predicts. Occupancy is not an objective by itself: never cap registers, shrink tiles, add stages, or increase warps merely to improve an occupancy number. Extra spills, recomputation, synchronization, or memory traffic may cost more than the residency gain.

## Establish correctness through execution

Use the actual producer and consumer in a fresh process. Compare against a high-precision or known-good reference, consume every candidate output, and characterize error rather than relying only on a pass boolean. Cover the production shape plus a few discriminating boundary, odd, empty/padded, and extreme-value cases. For quantized paths, verify scale granularity, zero handling, saturation, accumulation precision, layout, and dequantized error.

Make the first tiny target-GPU call the discovery smoke test. Repair ordinary compile, API, layout, or integration defects in the retained claimed session and continue. Owner failure handlers must distinguish a recoverable integration exit from a scientific, unsafe, or lifecycle terminal; do not release the claim on every nonzero exit when the researcher can patch and rerun before the deadline. Do not construct a long readiness ladder before CUDA execution, and do not time a candidate whose output has not reached the real consumer.

Classify build architecture fanout by the loaded path. Extra unused cubins, PTX, or objects for other accelerators are a build-efficiency defect, not a correctness failure, when the required target object and entrypoint exist and loaded-library identity plus dispatch can be proved. On a claimed mutable bench, adopt the installed artifact, run the tiny correctness smoke, and measure before narrowing the build. Do not release or cold-rebuild solely because unreachable objects target other architectures.

When a bounded or one-shot program invokes multiple CUDA arms, make fault attribution execution-equivalent before the timed sweep: synchronize after each arm's first untimed call and persist a compact completion marker tied to that arm. Keep these diagnostic synchronizations outside reported timing. A single synchronization after several asynchronous stock and candidate launches cannot identify the failing arm and must not be used to classify the candidate.
When one program measures independent consumer families sequentially, atomically checkpoint each family's completed timing and oracle rows before entering the next family. Each checkpoint must also carry the stage's expected-row ledger and prove that every required baseline, candidate, shape, unit, and numerical-oracle field is present; the program must not classify the overall generation as interpretable while any required stage is incomplete. A later consumer exception must preserve complete rows and make only the failed or incomplete family eligible for repair; first-call completion markers and unpaired timings are diagnostic evidence, not substitutes for the contracted measurements.

## Implement and measure

Choose tile, warp, stage, launch, memory, and work-partition candidates from the physical model. Constrain tuning to architecturally legal configurations and representative production shapes. Treat prefill and decode as separate keys when their geometry differs.

Benchmark profiler-off with warm caches and enough repetitions to report a distribution and margin over noise. Exclude compilation and autotuning from steady-state latency. Then collect only the counters needed to test the causal hypothesis. Preserve compiler metadata such as registers, shared memory, spills, and generated-code identity.

State whether each timed invocation processes one request, one token, or a concurrent batch. For a batch-level kernel, project endpoint savings as `delta_per_call * calls_per_batch / completed_requests`; do not multiply by batch call count and label the result seconds per request without dividing by the measured batch cardinality. Keep the unnormalized batch-total bound alongside the normalized request bound so the unit conversion is auditable.

Promote a component winner immediately into the actual runtime and workload. Verify CUDA-graph behavior, dynamic shapes, paged KV and GQA/MQA indexing, streams and synchronization, tensor parallelism, output layout, and runtime serialization as applicable. Judge success by endpoint time, throughput, energy, and price-normalized cost; component speedups do not transfer automatically.

## Iterate without ceremony

Revise the causal model after each result. A negative candidate closes that mechanism, not kernel research. Change decomposition or abstraction level when evidence warrants it. Keep the handoff to the hypothesis, implementation, exact evidence, interpretation, and next experiment; avoid a checklist report.

Record at minimum the exact source/runtime/hardware identity, production geometry, baseline and candidate warm timings, numerical result, candidate-path proof, relevant compiler/counter changes, endpoint effect when promoted, and artifact paths.
