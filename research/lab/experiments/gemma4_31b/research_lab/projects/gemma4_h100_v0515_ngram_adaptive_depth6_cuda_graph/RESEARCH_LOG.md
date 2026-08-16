# Research log

## 2026-07-25 15:55Z — fresh endpoint controller running

Verified the fresh endpoint binding and all nine bound path hashes, read the
current H100 identity, and claimed the released warm bench once. Constructed
and novelty-checked the immutable 791-request workload at indices
`62000..62790`; its workload SHA-256 is
`5ab280c171326db1c454e924b3db2e06ba47db09f3775dcc427d625b50f6f300`.

The durable controller is live at the recorded `OWNER_STATE.json` PID and has
started the fixed-depth-12 control server. It will run control, stop it, run
the adaptive exact-dual-graph candidate with the nine source overlays, compare
normalized outputs, retrieve telemetry/logs, persist the typed result and
terminal, and release the warm H100. No prior endpoint workload or timing was
replayed.

## 2026-07-25 15:38Z — exact H100 depth-6 component measured

**Question.** Does exact batch-8/depth-6 CUDA-graph execution preserve the
producer-to-settlement contract and reduce component latency versus identical
eager execution?

**Action.** Claimed the released warm H100 once and ran the bound project-local
runner in the pinned v0.5.15 image. The canonical continuation alternated 200
eager and 200 exact graph samples at 48 target rows after graph capture and
warmup. It exercised the native-depth-6 producer contract, exact target
metadata, greedy acceptance, KV movement, scheduler settlement, ragged
ownership, and a 7→8→7 guard.

**Evidence.** H100 CUDA replay had zero maximum absolute error and identical
accepted token IDs. Eager median was `0.06164800003170967 ms`; exact graph
median was `0.016063999384641647 ms`; paired median delta was
`-0.04531200136989355 ms` (`-73.94%` component scope). Result and trace are
retrieved and hash-bound in `ADAPTIVE_DEPTH6_H100_COMPONENT_TERMINAL.json`.
Five invalid launcher/observer attempts are preserved and were not counted as
independent samples; the final retry repaired only their defects.

**Interpretation.** The exact depth-6 component path passed on H100. The GPU
timing is a component measurement using exact 48-row geometry; it is not an
endpoint, quality, or economic claim.

**Next.** Release the unoccupied warm bench as `available`; retain the result,
terminal, trace, and invalid-attempt diagnostics.

## 2026-07-25 15:22Z — predecessor still owns H100; readiness revalidated

The supplied inventory continues to show `h100-v0515-packed-endpoint-200g-e00y7ay83sma59j0hz`
claimed by `gemma4_h100_v0515_ngram_verify_launch_pipeline` (priority 8500).
Revalidated `DIRECTOR_H100_COMPONENT_BINDING.json` and all four bound hashes;
the local readiness artifact remains valid and binds the exact batch-8/depth-6
eager-versus-graph contract. No inventory lookup, claim, provider action,
endpoint request, or scientific sample was made. Return until the predecessor
releases the bench.

## 2026-07-25 15:11Z — H100 component mechanically verified and queued

**Question.** Is the exact depth-6 CUDA-graph component ready to run on the
bound H100 without disturbing the priority-8500 endpoint lane?

**Action.** Verified `DIRECTOR_H100_COMPONENT_BINDING.json` and all four bound
input hashes. The pinned runtime, official image, source manifest, offline
fixtures, and exact batch-8/depth-6 two-arm contract are materialized locally
in the project. No inventory lookup, bench claim, provider action, checkpoint
load, or endpoint request was performed because the preferred bench remains
owned by priority-8500.

**Evidence.** `ADAPTIVE_DEPTH6_H100_COMPONENT_READINESS.json` records the
immutable identities and the required 200 alternating samples per arm,
producer-to-settlement correctness path, short trace, and 7→8→7 guard.

**Interpretation.** This is a readiness boundary, not a scientific result;
there is no latency, endpoint, or economic claim and actual spend remains
`$0.00`.

**Next.** After the predecessor releases, read the current inventory identity,
claim once, run only the bound component comparison, persist the result and
terminal, and release by 17:50Z. Do not wait or poll in this turn.

## 2026-07-25 14:59Z — exact depth-6 graph source complete

**Question.** Can the frozen depth-6-at-batch-eight-or-more NGRAM path own an
exact CUDA graph without padding, stale metadata, graph-key aliasing, or
ownership/KV risk?

**Action.** Verified `DIRECTOR_BINDING.json` and all five bound hashes against
clean SGLang v0.5.15 commit `f63458b5beaceabbd9d749b9fc956370e1b649e6`.
Traced graph identity, the shared capture pool, static replay buffers, Triton
target-verify metadata, dual native producers, ragged result carriers,
scheduler stride, and KV movement. Materialized and patched a project-local
source snapshot: speculative depth is part of `ShapeKey`; capture and replay
use exact `batch * active_depth` slices; Triton derives query/mask geometry
from active depth; producer buffers are native depth-12/depth-6 banks; result
filter/merge uses ragged offsets.

**Evidence.** The deterministic suite passed twice with byte-identical SHA-256
`f19e6f6bbfc4043b8e83e762ceef975f207a48bdc12c5c2cb214f23b82b30ae9`.
It exercised typed production graph keys and the actual patched ragged-carrier
methods, plus 7→8→7 keys `(7,12,84) → (8,6,48) → (7,12,84)`,
permutations, cancellation/completion, empty/partial matches, and slot reuse.
Wrong depth, depth-12 padding, token/position/mask shape, ownership,
completion, and live-slot mutations failed closed. Two pre-result observer
defects (Python 3.13 import registration and absent local PyTorch) are retained
as invalid attempts; neither entered CUDA or produced a decision-bearing
sample.

**Interpretation.** Classify `source_complete_h100_component_ready`. The exact
depth-6 graph is source-feasible with one capacity allocation and the existing
shared graph pool because graph identity and captured metadata are
depth-specific. This is source-backed plus deterministic offline state
evidence, not target-GPU execution.

**Next.** After the higher-priority retained endpoint lane releases a
compatible H100, run one short exact graph-versus-eager component from the
immutable source manifest. No provider, GPU, checkpoint, endpoint request,
latency claim, economic claim, or spend occurred in this project.

## 2026-07-25 fresh endpoint repair boundary

The frozen workload `62000..62790` was reused without checkpoint restaging.
The first control owner submitted 791 rows but lost the stock server after
128 completions. One authorized localized retry (finite-safe telemetry and a
32-client cap) again submitted 791 and completed only 128 before the same FP8
`RuntimeError: Error Internal`/SIGQUIT boundary at fresh index 62128. Raw rows
and server logs are retained under `artifacts/fresh-endpoint/`; retry hashes
are recorded in `ADAPTIVE_DEPTH6_FRESH_ENDPOINT_ATTEMPT2_INVALID.json`.

The candidate was never started and no complete control exists, so these are
invalid attempts rather than endpoint or economic evidence. `REPAIR_READY.json`
is persisted through the shared repair handshake with deadline
`2026-07-25T17:40:00Z`; retain the H100 claim, warm state, workload, and
checkpoint for director repair and do not replay control or run the candidate
without explicit authorization.

## 2026-07-25 stock assert localization boundary

**Question.** Localize the deterministic stock failure at consumed request
62128, then admit a new 63000..63790 endpoint pair only if stock A/A passes.

**Action and evidence.** Verified the new localization binding and every
bound hash. Retained the H100 claim and launched a durable owner. Both the
initial owner and its one allowed immediate retry failed before container
creation at the strict SSH host-key namespace with exit 255:
`No ED25519 host key is known for 89.169.103.97`. No CUDA diagnostic, guard,
new workload, control, or candidate request started; neither consumed
791-request workload was replayed.

**Interpretation.** This is a typed pre-science controller identity boundary,
not evidence against stock runtime or adaptive depth. The bounded retry rule
prohibits further owner relaunches in this turn.

**Disposition.** Persisted
`ADAPTIVE_DEPTH6_STOCK_RUNTIME_INTEGRATION_TERMINAL.json`, stopped/verified no
experiment container was created, and released the idle H100 to `maintenance`
at 16:37Z. Actual project spend remains $0.40.

## 2026-07-25 canonical stock-runtime terminal

The request-62128 CUDA_LAUNCH_BLOCKING diagnostic and repaired stock A/A
guard for 62127..62129 completed successfully with the single admitted
`--triton-attention-num-kv-splits 1` launch repair. The fresh workload
63000..63790 was atomically constructed once and retained.

The first canonical control attempt was invalid because the controller omitted
the admitted repair; its complete raw boundary is preserved under
`artifacts/fresh-endpoint/retrieved-control-63000/`. The controller was
patched in place and the invalid control was rerun once with the repair
applied. It still failed deterministically at fresh index 63000: 791/791
requests failed, the server log contains a CUDA `vectorized_gather_kernel`
index-out-of-bounds assertion, and the candidate never started. No endpoint
or economic claim is made; neither consumed 791-request workload was
replayed.

Persisted `ADAPTIVE_DEPTH6_STOCK_RUNTIME_CANONICAL_TERMINAL.json` with the
raw result, request, telemetry, and server-log hashes. The server/container
was stopped and the H100 released to maintenance at 17:22Z. Conservative
project actual spend is `$2.20`.
