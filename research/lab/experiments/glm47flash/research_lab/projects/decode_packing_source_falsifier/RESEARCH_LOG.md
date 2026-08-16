# Research log

## 2026-07-16 — Director opening handoff

- Attribution found that more live decode sequences explain c32's gain, but did not identify a scheduler change distinct from c32 itself.
- Audit the exact pinned scheduler and admit at most one intervention that conservatively compounds beyond the current `686.910`-tok/s frontier to `700.649`; otherwise close at `$0`.
- The live depth43 owner is out of scope. No CUDA, shared-code mutation, controller, or provider preparation.

## 2026-07-16 — Source-bound closure

- Question: is there one pinned-vLLM decode-packing intervention, distinct from higher client concurrency, with a conservative path above `700.649` tok/s?
- Action: bound the exact `vllm-0.15.0` V1 scheduler to the archive hash (`96f736…516a0`), inspected the archived c32 command/configuration, and compared the running-first/admission paths to the fixed 8k/1k c32 geometry.
- Evidence: c32 already uses `max_num_seqs=32`, `max_num_batched_tokens=65536`, chunked prefill, and asynchronous scheduling. The scheduler schedules running requests before waiting requests; all 32 ordinary decode requests need one token each, so the 65,536-token budget cannot limit a full c32 iteration. The measured c32 arm is saturated at 100% GPU utilization and yielded `686.910494` tok/s.
- Interpretation: policy and prefill changes cannot pack more decode work once c32 is at its admitted 32 sequence limit; increasing the token budget also cannot. Lookahead requires the excluded speculative path. No source-bound, semantics-preserving change has measured or source-proven non-overlapping wall-time leverage for the extra 2%.
- Result: `MECHANISM_CLOSE` at `$0`; artifact: `artifacts/DECODE_PACKING_SOURCE_DECISION_2026-07-16.json`.
