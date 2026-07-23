# Research log

## 2026-07-23 — director admission

The prior conditional-graph experiment proved the stock serving body returns to host-owned sampling, result processing, decode preparation, and batch mutation after every model graph. This project changes the serving topology for the campaign's forced-length, temperature-zero background workload: one fixed c32 executor keeps eight greedy steps on device and exposes the host only at block boundaries. The decision requires exact token/KV semantics and a positive whole-request bound before one endpoint; no result exists yet.

## 2026-07-23 — real-state fixed-c32 component reject

Question: Can one device-resident fixed-c32 executor run the exact two-eight-token-plus-six-token component with stock greedy semantics while reducing host scheduler boundaries?

Action: Rehashed and materialized the director-bound stack locally, atomically claimed the retained H200, and ran one stock and one candidate real-state c32 component. Pre-invocation wiring failures were repaired under one heartbeating owner. The candidate arm was invoked once; the 358-token control freeze and endpoint were never started.

Measured evidence: The candidate used replay blocks `[7, 8, 6]`, 21 model-graph replays, 3 host result synchronizations, and 3 decode boundaries versus 21 stock synchronizations/boundaries. All three KV transitions used unique 32-wide slot sets, and start/end positions matched stock. Candidate decode wall time was 5.195789 s versus 5.281932 s (ratio 0.983691), but only 72/704 token IDs matched, no row was exact, and the finite-output guard failed.

Protocol note: One valid stock 32x64 producer completed before its token-summary consumer was fixed. Repair quarantine logic then replayed that stock producer once before the sole candidate invocation; an earlier stale-server request was mechanically candidate-absent. This producer replay violates the single-producer repair rule and would independently forbid positive promotion. The negative candidate result remains conservative because the one candidate arm itself produced the token divergence and failed finite-output guard.

Interpretation: The topology and bookkeeping objective is mechanically attainable, but direct dependent replay is not semantically equivalent to stock host-stepped decode on this stack. The component quality gate rejects the lineage, so the apparently positive boundary/timing bound cannot authorize an endpoint.

Next: Terminal. Do not freeze a 32x358 control or run the endpoint. Any further work requires a newly admitted intervention rather than replaying this consumed fixed-c32 arm.

## 2026-07-23 — dependency-supergraph prepared; maintenance blocker

The renewed arm is implemented offline as a separate intervention. The old
direct-replay code and result remain untouched and are now hash-bound in
`DIRECTOR_BINDING.json`. The new fixed-shape executor captures each ordered
token, position, sequence-length, pre-reserved KV location, Triton attention
metadata refresh, child model replay, greedy argmax, and selected-logit finite
guard in one outer CUDA graph. For the component, a fresh stock oracle starts
from the same real state on each `[7, 8, 6]` decode block; the candidate then
overwrites the same slots and compares 704 IDs, positions, request ownership,
and every addressed KV byte. The worker freezes and runs the endpoint only if
that component is exact and its measured replay bound is positive.

No new scientific invocation started. The binding verifier, Python compilation,
shell syntax, and repository DevEx checks pass. Before a claim was attempted,
the shared inventory showed the only H200 in `maintenance`: priority-4500 had
found this project's consumed `gemma-static-c32` container holding 122,636 MiB
and port 30001, accepted no tied-head workload, and released for director
disposition. Pool policy makes maintenance benches unclaimable. Required next
step is director-authorized removal of only that terminal container, zero-GPU-
process verification, and a `gpu_pool ready` transition; the prepared arm can
then be rehashed, claimed, and invoked exactly once.
