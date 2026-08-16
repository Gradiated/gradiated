# Decode scheduler task graph

## Question

Can one source-complete device/host task-graph boundary remove a meaningful
fraction of the exact Gemma 4 c32 decode scheduler gaps without misclassifying
dependent GPU synchronization as removable work?

## Why it matters

The campaign must reduce the locked qualified service time from
`0.625149101968745` to at most `0.500119281574996 s/request`. The exact retained
profile assigns `1.151088036 s` of a 32-request window to scheduler gaps,
including `0.766971497 s` in decode, while synchronization is separately
assigned and must remain excluded because it represents dependent model-step
completion. This is materially distinct from the completed QKV-norm/RoPE to
E5M2-cache epilogue and can stack with it if the real source boundary is
removable.

The profile is from an older scope-matched retained runtime control
(`0.7051819141250064 s/request`), so it is a discovery prior rather than a
transferable endpoint claim. Any complete bound must state that scope
discontinuity and re-anchor to the locked qualified denominator.

## Evidence

- `../gemma4_h200_dense_fp8_linear_schedule/inputs/evidence/ATTRIBUTION.json`
  at SHA-256
  `f841db590dbe6f2e6b4fb91048e8132c3807f0321310e1e0b70a3957ac99ab48`.
- `../gemma4_h200_fixed_floor_crossop_executor/FIXED_FLOOR_CROSSOP_OFFLINE_TERMINAL.json`
  at SHA-256
  `33f88a6cf747a1545a55bf712d999bf8f2a55d3b1aab97e7a16ecafa20c17b7a`;
  this closes only the selected QKV/cache boundary and queues its positive
  component consumer.
- Exact model: `google/gemma-4-31B-it`, revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Target runtime scope: pinned SGLang v0.5.13, exact c32 OpenRouter-mix
  workload, NVIDIA H200 SM90.

## Scope

Use `$kernel-research`. Within 75 wall-clock minutes:

1. Trace the measured decode `scheduler_gap` intervals to the exact current
   producer/consumer and runtime symbols. Keep `synchronization` excluded.
2. Select one causal intervention only: for example a bounded device-side
   replay/task graph, persistent step dispatcher, or equivalent source-level
   boundary justified by the trace. Do not run a flag sweep.
3. Implement the intervention from its production input through the first
   decision-bearing consumer. Bind exact decode/prefill phase, shapes,
   streams, cache/request ownership, dtypes, and graph-dynamic invariants.
4. Derive compulsory launches/bytes, predicted eliminated host gaps, resource
   limits, and a complete-request bound against both the measured profile
   scope and locked qualified denominator.
5. Persist a target-H200 exact-consumer command if the source is complete;
   otherwise return typed `none`.

Do not claim a GPU, use SSH or provider APIs, open an endpoint, copy checkpoint
shards, treat synchronization as free/removable, or open a second candidate.

## Result that changes the portfolio

Persist `DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json` with direct hashes,
the exact source path and physical model, correctness and ownership contract,
complete bound, and one real H200 consumer command or typed `none`. A
source-complete candidate with a positive bound becomes eligible for one
later exact component measurement; otherwise this task-graph realization
closes and the next independent mechanism must change abstraction level.

## Director H200 continuation — 2026-07-27

The source-complete positive terminal is admitted for one checkpoint-free H200
component measurement under
`DIRECTOR_DECODE_SCHEDULER_H200_COMPONENT_REQUEST_20260727T0323Z.json`.
Implement only the cold-bench durable owner named there; do not claim, contact
the provider, or run CUDA until the exact reservation and a later live-bench
binding are durable. The component remains the same scientific question.
