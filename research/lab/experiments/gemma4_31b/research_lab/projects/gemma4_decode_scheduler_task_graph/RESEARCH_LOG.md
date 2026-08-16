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

## 2026-07-27 — cold H200 component owner

Action: Implemented `run_h200_decode_scheduler_component_owner.py` and bound
it to the admitted request, offline terminal, pinned SGLang image, and the
terminal's exact H200 command. It atomically claims only a later director-bound
bench, heartbeats the same claim, stages a small read-only project packet,
pulls the pinned image, retrieves `TERMINAL.json` and `INVOCATION_STATE.json`,
releases with `--expected-claimed-at`, and retains ordinary pre-science defects
through the shared hash-bound repair handshake.

Evidence: `--offline-check` passed Python compilation, AST parsing, request and
source digests, exact-command binding, no-checkpoint policy, image digest, and
the shared durable-owner/repair tools. `DECODE_SCHEDULER_H200_OWNER_READY.json`
records all direct hashes and command graph. No inventory mutation, SSH,
provider API, CUDA, endpoint, or checkpoint action occurred.

Next: Wait for a director-created, registered live H200 binding; this readiness
artifact is not a scientific result and does not authorize a claim.
