# Research log

## 2026-07-27 — one-step decode metadata task graph

Question: Can one source-complete device/host boundary remove a credible part
of the measured `0.766971497 s` decode scheduler gap without treating dependent
synchronization as removable?

Action: Reconstructed the exact mutually exclusive profile intervals from the
bound SQLite, traced the pinned overlap loop through
`update_running_batch -> ScheduleBatch.prepare_for_decode -> alloc_for_decode`,
and selected one candidate only. The implementation leaves eviction and KV-slot
selection on the host, then replaces four ordered device tasks—slot cast,
`req_to_token` publication, `seq_lens + 1`, and `orig_seq_lens + 1`—with one
c32 Triton task and a two-buffer overlap lifetime. A hash-gated installer was
exercised against the observed retained v0.5.13 source, and the real H200
component command uses SGLang's production request pool and token-slot
allocator.

Evidence: Measured trace reconstruction exactly recovers the decode scheduler
gap and finds 714 repeated one-block length-update gap boundaries. Their raw
overlap contains cross-stream outliers, so the derived bound caps each interval
at the measured `26.814 us` median and applies a further 50% realization
haircut. This predicts `0.00764219 s` per 32-request window, or
`0.0002388184375 s/request`. Re-anchored to the locked qualified denominator,
the bound is `0.624910283531245 s/request`, only `0.038202%` lower and well
above the `0.500119281574996` target. Even ideal removal of all measured decode
scheduler gap reaches only `0.601181242687495 s/request`. These are derived
bounds from older scope-matched telemetry, not endpoint measurements.

Interpretation: The task is source-complete and has a positive, stackable
component hypothesis, but it is economically immaterial alone. Synchronization,
host sampling/result boundaries, allocator ownership, request order, and model
kernels remain unchanged and receive zero savings credit. The offline terminal
is `DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json`; no GPU, SSH, endpoint,
checkpoint shard, or provider action occurred. A later authorized H200
component should run only the terminal's hash-bound command and reject on any
mapping/length/ownership mismatch or non-positive warm median.
