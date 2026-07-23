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

## 2026-07-23 — successor server conflict; candidate absent

After priority-4500 completed and released the bench `available`, this project
rehash-verified its binding, atomically claimed the H200, and staged immutable
inputs. The worker stopped before `INVOCATION_STATE.json`, any candidate audit,
or CUDA capture existed: its remote terminal was
`incompatible_retained_server_owns_gpu`. Recovery immediately reclaimed the
same bench after the first owner mishandled that missing marker, then retrieved
the terminal, raw logs, container inspect, GPU process row, and hash-verified
archive before final release.

Measured external state: the healthy priority-4500 container
`gemma-fp8-tied-head-topology-settled` remained running on port 30001 with
`sglang::scheduler` PID 453000 using 122,176 MiB. Static-c32 may neither inherit
that tied-head representation nor stop another project's healthy server. The
supergraph component and endpoint therefore remain unstarted and unconsumed.
Total new claim exposure was 414.121 seconds / `$0.2829823789`, raising
cumulative project exposure to `$1.6283636378`. The bench was released to
maintenance with the exact retained process for director reuse/removal
disposition. The owner is patched so a future absent pre-invocation marker is
preserved under the live claim instead of causing release-before-retrieval.

## 2026-07-23 — dependency-supergraph topology reject

The director removed only the completed tied-head server and verified the
retained H200 empty. This project rehashed `DIRECTOR_BINDING.json` and recovery
archive `3e193c80d218fb9417cb1e5efea399ef9317a6bbae1e725467351ab41840c949`,
atomically claimed the same bench, staged the immutable inputs, and invoked the
scientifically unstarted dependency-supergraph component once.

Measured result: the candidate installed and emitted
`supergraph_capture_started` for the first seven-forward block. During active
parent stream capture, `runner.graphs[32].replay()` raised `RuntimeError:
Cannot prepare for replay during capturing stage`; PyTorch reported
`cudaStreamCaptureStatusActive`. The scheduler exited, and the final GPU sample
was 4 MiB at 0% utilization. The candidate CUDA path therefore executed and the
arm is consumed; this is not a candidate-absent integration attempt.

No component transitions were produced, so 704-token equality, 32-row
equality, finite outputs, byte-exact KV/position transitions, and the 3-versus-
21 boundary claim were not established. The quality gate failed closed and the
conditional endpoint did not start. The claim added 161.939 seconds /
`$0.1106586131`, bringing conservative cumulative project exposure to
`$1.7390222509`. The compact archive is
`f94fce3efa113c34c8d5a625e389b1280b4de44319e8f91731a436935d6bcd31`;
all terminal evidence was retrieved before the bench was released available.

Next: terminal for this admitted topology. Do not retry the consumed candidate.
A new arm would require director admission of a materially different mechanism
that does not nest an existing `torch.cuda.CUDAGraph.replay()` inside parent
capture.

## 2026-07-23 — final stream-ordered chain prepared; bench unavailable

Question: Can the admitted no-parent-capture topology retain the supergraph's
per-step token, position, sequence-length, KV-location, Triton metadata, child
graph replay, and finite argmax dependencies while synchronizing only at the
7/8/6 result boundaries?

Action: Preserved the hash-bound supergraph source and added a separate
stream-ordered wrapper. It uses stable device ping-pong token buffers and, on
the current CUDA stream, enqueues each complete bound step without
`torch.cuda.graph()` or an inter-step synchronization. The existing bounded
outer owner now stages the old source as an immutable template and the wrapper
as `sitecustomize.py`; it rehashes both `DIRECTOR_BINDING.json` and
`STREAM_ORDERED_CHAIN_BINDING.json` before claim. Python compilation, shell
syntax, and both rehashes passed.

Evidence: The one atomic claim attempt at 21:55:12Z did not obtain the H200.
The pool reports it was claimed at 21:53:34Z by
`gemma4_h200_fp8_tied_head_fused_greedy_top1` with a 22:53:34Z lease. No remote
worker, CUDA invocation, candidate audit, or provider exposure started; the
cumulative project exposure remains `$1.7390222509364175`.

Next: After the current claim releases, atomically claim the same empty H200
and run exactly one frozen 32x22 stream-ordered component. Its gate remains
704/704 finite exact token transitions, byte-exact KV, exact positions/request
ownership, and 3 versus 21 host boundaries; do not run the conditional endpoint
unless that component passes with a positive bound.

## 2026-07-23 — stream-ordered component reject

Question: Does the final no-parent-capture chain preserve the exact 32x22
decode transition while reducing host result boundaries from 21 to 3?

Action: The first two owner attempts were mechanically candidate-absent: a
root-owned stale `component-supergraph.runner` directory raised before the
workload submitted any request, then cleanup without `sudo` proved insufficient.
Both raw traces and archives were retrieved. The scoped stream launcher then
removed only those stale stage-local paths with `sudo`, and the unchanged
component executed once on the claimed H200.

Measured evidence: The fresh candidate executed 21 existing c32 child-graph
replays on one stream, produced finite outputs, and reached exactly three host
result synchronizations/boundaries versus the control's 21. The measured device
time was `454.451752 ms`; the scheduler-gap-only conservative bound was
`0.6286271699 s/request`. However, it matched only `171/704` greedy token IDs,
with `0/32` exact rows. Every `[7,8,6]` transition had unique locations and
finite outputs but failed token, position, request-map, and byte-exact KV
equality. The compact archive hash is
`b42fdcb277ea4420479d7541cee6444a53e48c6587623c63a0fc33b9755afda7`.

Interpretation: Removing the parent capture resolves PyTorch's topology error
and retains the boundary opportunity, but the stream-enqueued replay metadata
still is not semantically equivalent to host-stepped decode. The exact gate
failed; the conditional endpoint was not started. Total project exposure is
`$1.9820952597558386`. This admitted topology is consumed and terminal.

## 2026-07-23 — direct raw-forward parent-supergraph reject

Question: Can step-specific stable `ForwardBatch` and Triton metadata state make
one exact c32 `[7,8,6]` parent graph semantically equivalent to the fresh stock
oracle while retaining only three host result boundaries?

Action: Rehashed `DIRECT_MODEL_SUPERGRAPH_BINDING.json`, atomically retained the
assigned H200, and materialized all invocation bytes under this project before
staging. The candidate allocated one Triton attention backend per unrolled step,
ran the pinned out-of-graph and in-graph metadata initialization sequence, and
captured 21 direct `model.forward` calls with dependent finite greedy argmax.
Two pre-capture wiring defects—the missing official CUDA-graph padding default
and one stale attempt-local runner directory—were repaired under the same owner;
neither reached parent capture or a raw candidate forward.

Measured evidence: All exact 7-, 8-, and 6-forward graphs instantiated without a
memory topology failure. Minimum post-instantiation free H200 memory was
`20,510,474,240` bytes. The complete component was finite, used 21 raw forwards,
and produced 3 host result synchronizations/boundaries versus 21. Candidate
device time was `455.893845 ms`, and the inherited boundary-only conservative
bound was `0.6286271699 s/request`. Semantics failed: `144/704` token IDs
matched, `0/32` rows were exact, and every block failed byte-exact KV, position,
and request-map equality despite unique KV locations.

Interpretation: Replacing instantiated child graphs with the official raw
capture body resolves both nested-capture support and graph-memory concerns, but
does not make the host-owned multi-token state transition equivalent. The exact
component gate rejects this final static-c32 mechanism; the endpoint did not
start. The hash-verified archive is
`artifacts/static-c32-direct-model-20260723t2242z` with SHA-256
`66b9f37da04dc3f46287321b0ed2cfe439fe5f6ce1e6e3caeb9ccefb58183667`.
The scientific claim cost `$0.4638849714`. A 21.606-second corrective claim then
verified the healthy retained server (`gemma-static-c32-supergraph`, port 30001,
123,620 MiB HBM) and changed the mistaken available release to maintenance
without stopping it; that added `$0.0147639768`. Cumulative project exposure is
`$2.4607442080`.

Next: Terminal. Do not retry any consumed static-c32 arm or run the conditional
endpoint without a new director-admitted topology.
