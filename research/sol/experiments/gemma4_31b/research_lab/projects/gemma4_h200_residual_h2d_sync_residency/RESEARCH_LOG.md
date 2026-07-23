# Research log

## 2026-07-23 — current-frontier synchronization trace admitted

Question: On the exact producer-fused H200 frontier, do repeated 8-byte or 16-byte H2D copies immediately precede workload-critical long stream synchronizations, and is any surviving path independently removable without changing model, cache, request, or sampling semantics?

Decision and hypothesis: run one current-frontier c32 Nsight trace before admitting any intervention. The discovery prior predicts 14×16-byte and 14×8-byte H2D predecessors, but it came from the rejected fixed-capacity metadata candidate. A current-frontier repeated path survives only if the new trace binds at least four long-sync predecessors to the same transfer/callchain/consumer semantics; absence or off-critical/candidate-specific behavior closes the lane.

Scope and quality gate: exact pinned Gemma 4 revision, SGLang v0.5.13 image/commit, dynamic FP8, fused QKV norm/RoPE, deferred local FP8 KV commit, pinned penalty transfer, host-required dense add, producer-fused SWA translation, and the frozen 32-request c32 workload. Require 32/32 sane outputs, exact `117728` uncached and `17120` cached prompt-token deltas, all retained path proofs, the profile SQLite, and invocation-state evidence. The trace uses CUDA/Python backtraces and binds runtime API, CPU thread, stream, source callchain, phase, and immediate same-stream GPU consumer.

Budget, timeout, and artifacts: cumulative authorization `$12`; prior spend `$0`; at most 90 claimed H200 minutes, three wall-clock hours, and 8 GiB retrieved artifacts. The bounded owner keeps claim/heartbeat/retrieval/release together, reserves 15 minutes for retrieval, and writes under `artifacts/residual-h2d-current-frontier-*`. Every hash-bound launcher, intervention, and 62.58-GB checkpoint byte was materialized read-only under this project before claim; remote staging reconciles size and SHA-256 and transfers only missing or mismatched files.

## 2026-07-23 — source-bound pair and prediction close

Measured trace: the exact c32 frontier completed 32/32 with exact cache accounting. Nsight attributed 29 long scheduler-thread synchronizations totaling `4.71288894 s`. CUDA backtrace instrumentation emitted a base-name row and versioned runtime row with the same correlation ID; the initial analyzer mistakenly treated that alias as the predecessor and reported absence. Skipping same-correlation aliases recovered the scope-matched signature: 14×16-byte and 14×8-byte `cudaMemcpyAsync` operations on thread `sglang::schedul` / global TID `281477845614763`, CUDA stream 37, immediately consumed by `write_req_to_token_pool_triton`.

Source binding and intervention: pinned SGLang commit `28b095c…` constructs a transient `uint64` device tensor from one prefix pointer per newly admitted request in `mem_cache.common.write_cache_indices`, then passes it unchanged to `write_req_to_token_pool_triton`. The frozen intervention preserved values, dtype, shape, order, consumer grid, cache, and sampling semantics while constructing the host tensor in pinned memory and transferring it non-blocking. Candidate audits proved 64 runtime invocations at one- or two-pointer geometry plus the unchanged retained stack.

Profiler-off pair: both arms completed 32/32 and reproduced `117728` uncached plus `17120` cached prompt tokens. Control measured `0.6774429486 s/request`; candidate measured `0.6768880493 s/request`, a `0.0819109%` reduction. The candidate remained above the `0.6381105231 s/request` economic ceiling.

Prediction and decision: the candidate trace removed the exact source-bound `write_req_to_token_pool_triton` predecessor groups (`28 -> 0`), but a distinct 14×8-byte H2D group immediately consumed by `vectorized_elementwise_kernel` remained. Long-sync count stayed `29`; cumulative long-sync duration changed only from `4.71288894 s` to `4.705011568 s` (`0.1671%`). Close `pinned_async_prefix_pointer_h2d`: it moved the immediate blocking predecessor without removing the synchronization and delivered no material endpoint gain. Do not replay this intervention.

Provider accounting: first trace `545.9849436 s` / `$0.3730895080`; pair plus prediction `461.4112663 s` / `$0.3152973626`; cumulative `$0.6883868705` against the `$12` reservation. The owner retrieved both compact terminals and SQLite reports before releasing `h200-sync-linear-e00vhh6h29fj68x91g` ready and warm.
