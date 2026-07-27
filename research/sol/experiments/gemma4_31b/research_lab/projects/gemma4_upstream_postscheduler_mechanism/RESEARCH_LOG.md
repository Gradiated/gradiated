# Research log

## 2026-07-27T04:13Z — bounded upstream screen returns typed none

Question: does one current official SGLang change expose a nonduplicate mechanism on the locked Gemma 4 31B c32 path?

Action: inspected exactly three official merged PRs. Rejected PR #30924 because whole-row dynamic FP8 bypasses its group kernel and PR #30540 because its attention backend rejects d256/d512 sliding-window Gemma geometry. Selected PR #31487 before implementation and compiled its exact `PrefillCudaGraphRunner.can_run_graph` body from commit `6c6175f` into a focused offline consumer.

Evidence: the exact upstream 2x padding guard passed four boundary checks, but the locked v0.5.13 tree contains neither the prefill graph runner nor its config type, and the exact launch exposes only legacy decode CUDA graphs. Activated work and the complete locked-request bound are therefore exactly zero. One initial annotation-binding harness failure occurred before the consumer call; binding the inert type annotation and rerunning only that invalid operation produced `artifacts/OFFLINE_CHECKS.json`.

Interpretation: typed `none`. A current-main prefill-graph run would be an excluded generic runtime replacement, not a consumer of this locked intervention. No GPU command is nominated, no spend was incurred, and no kernel candidate was selected.

Next: close this exact screen. Reopen only for a new source revision that reaches the real dense whole-row FP8 or d256/d512 hybrid-attention producer, or after explicit admission of a current-runtime rebase.
