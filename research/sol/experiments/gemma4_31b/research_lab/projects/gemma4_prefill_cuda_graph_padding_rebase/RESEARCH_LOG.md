# Research log

## 2026-07-27T04:43Z — offline execution contract

Question: does the official prefill CUDA-graph padding guard activate on the
hash-bound Gemma 4 c32 workload after the minimum current-runtime rebase?

Action: bind official commit `6c6175fa…3a75`, execute its bucket generator,
padding selector, and `PrefillCudaGraphRunner.can_run_graph` method bodies from
their exact AST, then reconstruct every `ForwardBatch.input_ids` row from the
content-addressed workload, launch, cache accounting, and measured prefill
completion order. Compare the same source with padding factor `2` and the guard
disabled.

Quality gate: all official and workload hashes match; 32 request hashes join;
every request owns exactly 3,679 uncached rows; all raw, bucket, padding, route,
and total-row decisions reconcile; the known 2× boundary changes only when it
should. SLO: reduce the locked `0.625149101968745 s/request` toward
`0.500119281574996` without changing model, workload, token, position, cache,
quantization, attention, or output semantics.

Budget and terminal: 90 wall-clock minutes, `$0`, no GPU/CUDA/provider/SSH or
checkpoint-shard access. Persist
`PREFILL_GRAPH_PADDING_REBASE_OFFLINE_TERMINAL.json`; return typed `none` if
the exact workload never crosses the guard. No background session is needed.

## 2026-07-27T04:49Z — official rebase terminal

Evidence: the project-local official snapshot matches all 13 direct source
hashes at `6c6175fa…3a75`. The exact official AST produces capture buckets
through 2,048 and reproduces the known guard boundary (`3208→8192` rejected,
`4096→8192` accepted). The content-addressed workload, launch, and qualified
terminal hashes are respectively `7a05fa62…25d`, `a48f6910…1de`, and
`7090c0eb…9dd`.

Interpretation: 32 requests each own 3,679 uncached prompt rows. The current
scheduler's PP-only dynamic predictor is inactive at exact TP1/PP1, so the
2048 budget packs the 117,728 compulsory rows into 57 full forwards and one
992-row tail. Official buckets map them to 2,048 and 1,024. All 58 forwards
remain eligible with the 2× guard; guard-on and guard-off both process 117,728
compulsory plus 32 padded rows. The causal time and cost reduction intervals
are exactly `[0, 0]`; no row-count timing credit is taken.

Decision: `typed_none_exact_workload_guard_never_crosses`. A real H200
guard-on/off command is typed `none` because forming a differing route would
require changing the forbidden workload, chunk size, or buckets. Four focused
tests pass. No GPU, CUDA, provider, SSH, endpoint, or checkpoint shard was
touched; spend is `$0`.
