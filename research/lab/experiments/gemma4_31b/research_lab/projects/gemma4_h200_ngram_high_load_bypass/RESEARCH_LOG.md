# Research log

## 2026-07-24 — frozen high-load bypass launched

Question: can whole-step ordinary greedy target decode at eight or more
running requests preserve exact sparse-baseline semantics and improve the
request-870 production prefix?

Action: SHA-256 checked every `DIRECTOR_BINDING.json` reference and
materialized the consumed comparator, trace, installed runtime sources, and
sparse update under `bound_inputs/` before claim. Implemented the frozen
depth-12-below-eight/ordinary-decode-at-eight-or-more rule with explicit
match-state erasure on both transitions and stock non-speculative
`prepare_for_decode` ownership of one unique KV slot per high-load request.
No threshold, depth, or settled arm is replayed.

Evidence pending: PID-managed controller `174152` atomically claimed retained
bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` at
`2026-07-24T23:12:46Z`; its absolute state and artifact root are recorded in
`STATUS.json.active_session`. The owner will persist the request-870 terminal,
conditionally admit the sole full trajectory, retrieve exact outputs and
telemetry, and release by the frozen deadline—or retain the claim through the
repair handshake for an ordinary integration defect.

## 2026-07-24 — observer repair prepared; controller lifecycle boundary

Action: inspected only snapshot `55d4a2bacebf5528b88a33b9900b3be63f75e0183998c7ff152b7de36a4fe50a` and the startup/health/metrics path. The hash-bound `REPAIR_PACKET.metrics-persistence.tar` (`4a97181c49d3336687a22eb38299dd1d82834829b200b0d614a8d33fa43a0139`) atomically archives the incomplete pre-prefix output root, persists candidate rows and telemetry before the post-run metrics observer, and records post-run metrics unavailability without changing the comparator, threshold, NGRAM rule, candidate injection, or full-run gate. `REPAIR_REQUEST.json` binds that packet for the existing owner.

Evidence: `ATTEMPT_TERMINAL.json` records `prefix_persisted: false`; the container served health, requests, and periodic metrics before its final observer raised `ConnectionRefusedError`. At 23:33:21Z, controller PID `174152` was absent, its last heartbeat was 23:27:47Z, and the request remained unconsumed. The pool still reports the bench claimed by this project.

Interpretation and next move: this remains an invalid observer/harness attempt, not a settled candidate sample, but the durable controller required to apply the repair is no longer live. No replacement, release, or cold restart was performed. Conservative accrued exposure is `$0.865`; director lifecycle disposition is required before the retained owner-compatible prefix retry can run.

## 2026-07-24 — requeued prefix owner launched

Action: SHA-256 rechecked `REPAIR_PACKET.metrics-persistence.tar` as
`4a97181c49d3336687a22eb38299dd1d82834829b200b0d614a8d33fa43a0139`,
then started the existing bounded controller through `detached-owner` with
`CONTROLLER_OWNER_REPAIR.json` as its PID-managed owner state.

Evidence: the controller PID is `186454`; it atomically claimed
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc` at 23:38:31Z and recorded active
artifact root `artifacts/high-load-bypass-20260724t233831z`. Its runner
verifies the repair packet hash before claim and stages that packet, not the
original frozen packet.

Next move: the durable owner retries only the repaired candidate request-870
prefix, persists and retrieves its typed terminal, and conditionally runs the
unchanged full trajectory only if the exact-positive gate passes.

## 2026-07-24 — repaired prefix closes the bypass

Action: the fresh owner consumed the hash-bound repair packet, atomically
archived the prior incomplete output root, and persisted the repaired
candidate-only request-870 prefix before its metrics observer. The retrieved
terminal is snapshot
`c09b906cb9aee3fb68705ca9c7bbd4bbd11c45d3c685a4c01c3df2cdfcfc2103`;
`FINAL_TERMINAL.json` has SHA-256
`72ad47747a01b39a07e1e7b01732a97bad7bf8b6121581d768eede10b8a3f156`.

Evidence: 791 of 871 scheduled requests completed and exactly matched the
comparator for output tokens, finish reason, and usage. Eighty requests failed
from index 791 onward (initial HTTP 500s, then disconnects and connection
refusals). Candidate throughput was 5,984.38 tokens/s versus the comparator's
6,335.22 (-5.54%); planning cost was $0.150856/M versus $0.142501/M
(+5.86%). The prefix is therefore neither exact/failure-free nor positive.

Interpretation: this is a complete decision-bearing candidate sample, not an
observer failure. The project gate closes as
`semantic_divergence_prefix_gate_closed`; the 1,036-request trajectory was
not started and no arm may be replayed. The owner retrieved the terminal and
released the occupied server state to maintenance. Cumulative recorded
provider exposure is `$1.35113004025`.

## 2026-07-25 — threshold-transition repair running

Question: can the first size-8 transition execute ordinary greedy target
decode exactly without replaying the settled 791-request prefix?

Action: retrieved the retained server traceback before mutation. The failure
was a source-local shape contract: the first ordinary decode entered the
target worker with 36 NGRAM-shaped `input_ids` for an eight-request batch.
The frozen repair rebuilds exactly eight authoritative last-token inputs only
on bypass entry, keeps `spec_algorithm=NONE` and `spec_info=None` through
ordinary scheduler post-processing, and asserts `out_cache_loc`,
`req_to_token`, `accept_lens`, and match-state ownership. A PID-managed local
controller (`THRESHOLD_CONTROLLER.json`, PID 199997) claimed and heartbeats
the retained H200; its remote PID-managed worker began at 00:04:34Z.

Evidence pending: the worker runs one candidate-only eight-request component
with synchronous container-log capture. Only an exact component with at least
one bypass step and fewer target rows can start request 791 through 870; the
settled prefix and full endpoint remain forbidden.

## 2026-07-25 — timeout-corrected semantic component launched

Action: preserved snapshot `3c8e351f5f44c17aec46d613b6cbd352ce513c9476b1fd1099026fd21b79814d`
as an invalid observer attempt and changed only the semantic consumer timeout
to 120 seconds. The retry writes to a distinct remote output root, so the
timeout artifact remains immutable. Its durable local owner is
`THRESHOLD_TIMEOUT_CONTROLLER.json` (PID `204469`), its remote worker is PID
`208556`, and the H200 claim is heartbeating under the 00:50Z deadline.

Evidence pending: `REMOTE_STATE.json` at 00:13:08Z records both owner layers
live. The component remains the sole first arm; the suffix is still conditional
on 8/8 exact rows, zero request errors, real bypass steps, and reduced target
rows. The settled prefix and full endpoint remain unstarted.

## 2026-07-25 — metrics-guard launch blocked before remote invocation

Action: staged a source-local wrapper around `MetricsReporter.report_decode_stats`
which records zero speculative acceptance when `spec_num_forward_ct == 0`, then
attempted the existing detached outer owner. The owner atomically claimed the
named bench but failed before remote launch with `typed_provider_boundary:no_public_ip`.

Evidence: provider inspection records `state=STOPPED`, an empty public-IP
address, and no remote worker or CUDA invocation; see
`PROVIDER_STOPPED_DIAGNOSTIC.json` and `THRESHOLD_METRICS_GUARD_CONTROLLER.log`.
The claim is released to maintenance for director disposition. The metrics
snapshot, settled prefix, and all conditional gates remain unchanged.

## 2026-07-25 — awaiting director-owned H200 restore

Evidence: the shared pool still lists
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc` as `maintenance` with no claim at
00:23:40Z. The director has submitted restore operation
`computeoperation-e00wegqmd0egy3g99v` for the same instance and attached
ready disk, but has reserved verification of RUNNING state, public IP, and
return to `available` for a later lifecycle turn.

Next move: make no claim or provider mutation until that director transition;
then execute only the already-prepared metrics-guarded eight-request component.

## 2026-07-25 — restored-bench metrics component launched

Action: after the director returned the exact retained H200 to `available`,
started the existing detached outer controller with the prepared telemetry-only
guard. It claimed the registered bench once and opened a new immutable output
root; no settled prefix or endpoint was replayed.

Evidence pending: local PID `214806` is live with a successful 00:25:56Z
claim heartbeat, and `REMOTE_STATE.json` records the remote component worker
PID `2423` live at 00:26:06Z. The exact 8/8 component remains first; suffix
and full gates are unchanged.

## 2026-07-25 — SchedulerMetricsReporter repair launched

Action: replaced only the nonexistent `MetricsReporter` import and patch
target with pinned `SchedulerMetricsReporter`, then staged the same component
under a fresh immutable output root. The old exact-but-stock-NGRAM snapshot is
preserved.

Evidence pending: local PID `225024` is live with a successful 00:45:29Z
claim heartbeat; `REMOTE_STATE.json` records remote worker PID `7005` live at
00:45:38Z. No prefix or endpoint replay was admitted.

## 2026-07-25 — untouched fixed 1,036-request trajectory launched

Action: the passing component and suffix gate admitted the sole full arm.
The retained runner was narrowed to invoke only its existing `full-1036`
consumer, retaining comparator, request latency/slope, event, target-row, and
economics persistence while explicitly recording no prefix or suffix replay.

Evidence pending: local PID `231510` is live with a successful 00:52:56Z
heartbeat; `REMOTE_STATE.json` records remote worker PID `9496` live at
00:53:04Z. The owner will retrieve the typed terminal and release the bench.
