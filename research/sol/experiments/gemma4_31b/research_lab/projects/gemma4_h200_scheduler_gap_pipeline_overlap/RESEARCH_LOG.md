# Research log

## 2026-07-23 — source binding complete; measurement gated by metadata iteration 2

Question: which exact source path owns the largest repeated scheduler-gap class, and what single overlap intervention can remove its serialization without changing request, sampling, cache, or workload semantics?

Action: verified the bound trace and sources, reconstructed scheduler-gap interval unions from the supplied SQLite trace, ranked consecutive same-stream kernel pairs, inspected the pinned v0.5.13 overlap source, and froze one schedule-stream forward-penalty-snapshot intervention. A pre-science claim was released ready immediately after the named priority dependency was checked and found not to have an iteration-2 terminal or resident-state handoff. No endpoint, trace, CUDA candidate, continuous-decode, flag-sweep, or geometry-changing scientific invocation ran.

Evidence: `GAP_SOURCE_BINDING.json` measures 358 same-stream gaps from the one-block `index_elementwise_kernel` to the 8,192-block float32 dense logits add, totaling `0.643528382 s`, median `1.7780405 ms`, maximum `5.038378 ms`, and 56.3261% of all `1.142505439 s` scheduler-gap time. Exact count and geometry bind the consumer to the retained min-new-tokens dense add. Pinned source inspection binds `Scheduler.run_batch -> Scheduler._forward_isolation -> SamplingBatchInfo.copy_for_forward -> SamplingBatchInfo.update_penalties -> BatchedPenalizerOrchestrator.accumulate_additive_penalties -> BatchedMinNewTokensPenalizer._apply -> Tensor.add_`.

Interpretation: the forward-only penalty buffer is currently produced after entering `forward_stream_ctx`. `FROZEN_INTERVENTION.json` moves only that snapshot production to `schedule_stream`; the existing later `forward_stream.wait_stream(schedule_stream)` supplies the happens-before edge, and the existing two-iteration overlap ring pins the substituted tensors. The causal prediction is a strict reduction in the 358 matched interval-union gaps with no new synchronization predecessor.

Spend and next move: the pre-science claim lasted `339.669152 s` at `$2.46/hour`, conservatively assigned as `$0.232107253867`; scientific invocation state is false. Wait for `gemma4_h200_flashinfer_metadata_scalar_elimination` iteration 2 to persist its scientific terminal and warm handoff, then materialize admitted bytes project-locally and execute exactly the frozen c32 pair plus minimum candidate trace.
