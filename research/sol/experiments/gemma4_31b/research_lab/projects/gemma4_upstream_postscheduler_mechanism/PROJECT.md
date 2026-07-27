# Gemma 4 upstream post-scheduler mechanism

## Question

Does current primary-source runtime or kernel work expose one untested,
source-complete mechanism for the exact Gemma 4 31B c32 critical path after
queue ordering, fixed-c32 parent graphs, and the one-step scheduler task have
been settled?

## Why it matters

The exact H200 scheduler component removed 1,074 device tasks and reduced its
isolated boundary by `38.1165%`, but its conservative locked-request bound is
only `0.038202%`. Observable attained-service ordering is an exact negative on
the homogeneous c32 trace. Another scheduler policy cannot close the
`0.500119281574996 s/request` target. Paid authority is also below the recent
checkpoint-free H200 lifecycle cost, so the independent lane must discover
and implement a new source mechanism without consuming a GPU.

## Bound evidence

- `../gemma4_decode_scheduler_task_graph/DECODE_SCHEDULER_H200_FINAL_RESULT.json`
- `../gemma4_decode_scheduler_task_graph/DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json`
- `../gemma4_attained_service_graph_batching/ATTAINED_SERVICE_GRAPH_BATCHING_OFFLINE_TERMINAL.json`
- The closed project statuses for
  `gemma4_h200_static_c32_multitoken_decode_engine`,
  `gemma4_h200_decode_sync_graph_elimination`,
  `gemma4_h200_async_token_result_pipeline`,
  `gemma4_h200_operation_overlap_discriminator`, and
  `gemma4_h200_scheduler_gap_pipeline_overlap`.

These close only their exact mechanisms. Do not replay them or infer that all
current upstream opportunities are absent.

## Scope

Use `$evidence-research` for a bounded primary-source search. Inspect at most
three current official runtime/kernel candidates that touch the exact Gemma 4
hybrid-attention, dynamic-FP8, H200, or c32 production path. Exclude generic
runtime replacement, flag sweeps, another queue policy, another fixed-c32
parent graph, speculative decoding, vocabulary-head retrieval, blunt
layer/width deletion, and any mechanism already represented by the named
closed projects.

Choose one candidate before implementation. Trace it from the exact current
producer through its first decision-bearing consumer and implement the
smallest source-complete intervention or exact reproducer against pinned local
source. If the candidate is a kernel, use `$kernel-research` and bind exact
shapes, layouts, dtypes/scales, strongest baseline, correctness contract, and
predicted physical counter. Do not stop at a survey, patch sketch, observer,
launcher, or metadata hook. Return typed `none` if the primary sources expose
no nonduplicate mechanism with a credible exact-workload causal bound.

Work for at most 90 wall-clock minutes and `$0`. Do not claim a GPU, use SSH or
provider APIs, run CUDA or an endpoint, read checkpoint shards, copy model
files, or sweep candidates.

## Terminal

Persist `UPSTREAM_POSTSCHEDULER_MECHANISM_OFFLINE_TERMINAL.json` containing:

- primary-source URLs, revisions, retrieval time, and scope labels;
- direct local input and implementation hashes;
- the rejected candidate shortlist and the single selected mechanism;
- exact source/producer/consumer ownership and correctness contract;
- a physical model and complete locked-request bound with uncertainty;
- focused offline checks proving the intervention is source-complete; and
- one real current-runtime H200 consumer command or typed `none`.

A positive terminal prepares one materially new direct component falsifier for
a later authority decision. It does not reserve spend or authorize provider,
GPU, endpoint, or quality work.
