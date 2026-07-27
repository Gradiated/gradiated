# Research log

## 2026-07-27T03:57:07Z — source-complete policy; exact c32 negative

- Question: can one blind attained-output-service policy change real CUDA-graph padding or transitions versus FIFO on the bound c32 trace?
- Action: bound the exact runner, workload, qualified terminal, current server log, and pinned SGLang sources; implemented `least_attained_service_stable_fifo_v1`, its stock-FIFO comparator, a fail-closed source installer, and a fixed-record observer at `CudaGraphRunner.replay_prepare`; ran the offline consumer once after one manifest-path repair.
- Evidence: the runner releases all 32 requests through one barrier; all prompts are 4,214 tokens, all attained counters start at zero, and every request is forced to 358 output tokens. Candidate and FIFO admission orders are both `[0..31]`. Current graph buckets are `[1,2,3,4,5,6,7,8,10,12,...,32]`; compulsory output work is 11,456 active row-steps. Exact candidate-minus-FIFO deltas are zero active work, padding, transitions, and removed scheduler/graph operations. Absolute qualified padding is honestly bounded `[0,1272]` because the retained endpoint lacks per-forward `raw_bs`.
- Interpretation: typed negative `simultaneous_homogeneous_c32_fifo_parity_no_causal_graph_change`. The candidate adds one host sort and removes no device work, so its best-case derived planning cost remains `$0.13715625/M` versus the `$0.109725/M` target.
- Next: close this trace; reopen only with content-addressed heterogeneous arrivals or completions. No GPU command is warranted or authorized.

Terminal: `ATTAINED_SERVICE_GRAPH_BATCHING_OFFLINE_TERMINAL.json` (`sha256:e9564f7fe8ad570a706f150e645885984117adee42b43742096a6baf2df0b0e4`).
