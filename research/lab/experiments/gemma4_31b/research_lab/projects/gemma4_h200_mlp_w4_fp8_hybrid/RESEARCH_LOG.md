# Research log

## 2026-07-23 — exact group-128 W4 decode MLP

Decision: reject this intervention at the component gate. Do not run coherence or the c32 endpoint pair.

Hypothesis and scope: replace only decode MLP gate/up and down projections with the pinned SGLang AWQ-Marlin W4A16 group-128 consumer. Retain current FP8 everywhere else and retain the current path for prefill. Test only the admitted real-weight shapes and representation; no format, group-size, kernel, or workload sweep.

Inputs: after the campaign reservation became durable, the source W4 checkpoint was first admitted project-locally. Because the retained bench had insufficient disk for a second full 19.2 GB copy, an exact MLP-only immutable snapshot was derived from those admitted bytes before GPU execution: 540 tensors, 10,810,990,320 bytes, SHA256 `2e080adb1cd48b02ee17d915977fa0d6124610590e1edcbc39dc26e843e27153`. The layer-0 component snapshot is 180,183,144 bytes, SHA256 `871a79d70b4fe23a5b036a765a129556ff2b4a2affc86606e843dbae215e04f8`. This narrowed only staged bytes, not the intervention.

Measured correctness: the real AWQ-Marlin consumer produced finite, nontrivial complete MLP outputs for M=1,2,4,8,12,16,24,32. Relative L2 versus dequantized W4 was at most 0.0008862 and cosine similarity was at least 0.99999964. The candidate path and expected symbols were present.

Measured profiler-off timing: at the endpoint-bound M32 geometry, current FP8 was 0.120192 ms and W4 was 0.130416 ms by warm CUDA-event p50. W4 was 8.51% slower (`0.92160x` speedup). Across 60 layers, 357 post-first-token decode steps, and 32 completed requests, the call-weighted bound is −0.006844 s/request or −1.014%, below the preregistered +3% promotion threshold. W4 was faster for M=1 through M=16 but lost at M=24 and M=32; the admitted endpoint workload binds to M32.

Measured causal counters: the exact c32 Nsight Compute basic set was collected after a harness-ordering defect had skipped profiling on component rejection. This repair replayed no timing arm and invoked no endpoint. W4 reduced immutable MLP tensor bytes by 48.05% and reduced the chain from five kernels to three, but its two Marlin kernels each used 200 registers/thread, 233,472 shared-memory bytes/block, a 132-block grid on 132 SMs, and one wave/SM. Duration-weighted DRAM throughput fell from 66.13% for the FP8 chain to 29.72% for W4, while SM throughput rose from 14.62% to 38.80%. The dequantizing, resource-heavy Marlin path therefore failed to exploit H200 bandwidth as effectively as the FP8 CUTLASS path at M32.

Quality caveat: kernel correctness is against the real W4 representation. The dequantized W4 checkpoint and current FP8 representation differed substantially (M32 relative L2 1.2048, cosine −0.0020), so an endpoint quality claim would have required the coherence gate even if performance promoted. Performance did not promote, so all three coherence prompts and both endpoint arms remained uninvoked by contract.

Operations: a post-science owner defect used obsolete pool-update arguments, but compact component terminals and raw diagnostics were retrieved before release. The counter-only repair used the supported JSON-file release interface, retrieved both raw NCU CSVs and invocation markers, updated resident contents, and released `h200-sync-linear-e00vhh6h29fj68x91g` ready. Conservative cumulative exposure is $0.7567693979 of the reserved $12.

Artifacts: `FINAL_TERMINAL.json`, `CAUSAL_COUNTERS.json`, `GPU_INPUT_MANIFEST.json`, `artifacts/gemma4-w4hybrid-repair-20260723t062229z/result/component/TERMINAL.json`, and `artifacts/gemma4-w4hybrid-counters-20260723t063600z/result/`.
