# Research log

## 2026-07-25 — source-bound causal result

Decision: promote one candidate, `request_local_verified_trunk`, to a single
candidate-only endpoint arm. Do not replay threshold-8 bypass, built-in
frequency mode, global breadth-one, or a settled scheduler/source arm.

Measured evidence:

- The hash-bound c32 tail terminal ended at speculative acceptance length
  `5.0`, rate `0.363636`, peak queue `41`, and elapsed time `776.618 s`.
  Request 32 is the sole semantic divergence: after 289 dominant tokens it
  emits the three-token transient `25627, 1767, 1154`, then returns to the
  dominant token. The first later low-acceptance observation is length
  `5.1887` with 32 running requests.
- The independent state-aging run has one divergence, request 790, which
  switches from the dominant token to token `3055`; acceptance falls at the
  same time despite a prior corpus reset. Its trie stayed small, closing
  capacity/aging as the primary cause.
- An exact C++ probe compiled against pinned SGLang commit
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2` reproduces four accepted drafts
  after the request-32 transient. Four drafts plus the verifier bonus exactly
  predicts the measured length `5.0`.
- Built-in frequency mode also accepts four drafts in the transient and
  persistent-alternate probes. Global max-breadth-one restores eleven after
  the transient but accepts zero when the persistent alternate is newest.
  Both global policies are rejected.

Interpretation: `NGRAMWorker._update_ngram_corpus` mixes every request's last
18 target-accepted tokens into one online trie. `Trie::buildRecency` gives
recent children fixed breadth entitlement without request ownership or a
support gate. One rare request therefore displaces the dominant continuation
for its peers. At c32, the fixed 12-row verifier magnifies length 5 versus 12
from approximately `29.83` to `71.60` target rounds per 358-token completion.
Every round traverses Gemma's 60 layers (50 local, 10 global) and the
262144-way LM head, explaining the growing service span and queue.

Candidate: retain a bounded per-request trie of only target-verified tokens.
Reserve its longest verified continuation as that request's next draft trunk,
then fill unused rows from the unchanged global recency tree. Keep depth 12
and the target verifier unchanged; fall back globally until a local
continuation exists, and erase local state through the existing finished-rid
cleanup. This differs materially from threshold bypass: no request leaves
NGRAM and all draft tokens remain target-verified.

Predicted counter change: unaffected requests remain near 11 accepted drafts
after the first rare branch; target verification rounds and rows per
completion fall by up to 58.3%, with fewer KV slot allocations and rejected
slot frees. The endpoint should peak below queue 30, drain to zero without
growing release drift, preserve 1036/1036 normalized semantics, and cost at
most `$0.14/M`.

Endpoint: exactly one candidate-only 1036-request full-arrival trajectory,
releasing every request at its bound `arrival_s`. Apply only the hash-bound
request-local verified-trunk overlay and retain the pinned image, model,
launch, c32, depth 12, and global BFS fallback. Persist per-request acceptance
around the first rare-output insertion, target forward/row counts, KV
allocation/free counts, peak/final queue, release drift, elapsed time, cost,
failures, and normalized semantic equality. No control replay.

Artifacts:

- `artifacts/causal-source-probe/RESULT.json` — causal chain, exact geometry,
  bound identities, source probes, and predictions.
- `artifacts/causal-source-probe/CANDIDATE_ARM.json` — minimal candidate-only
  endpoint contract.
- `artifacts/causal-source-probe/probe.jsonl` — exact C++ probe rows.
- `run_causal_analysis.py` and `ngram_tree_probe.cpp` — reproducible local
  analysis.

No GPU bench was claimed and no provider mutation occurred. Actual spend is
`$0.00`.

## 2026-07-25 — candidate endpoint dispatched

All six director-bound evidence identities and the immutable local launch,
semantic-row, and NGRAM-worker snapshot matched in
`DIRECTOR_BINDING_VERIFIED.json`. The durable controller atomically claimed
the retained H200 under the existing `$3` reservation.

Two pre-invocation integration defects were preserved as invalid attempts:
the first used an unprivileged Docker client; the repaired launch then exposed
one omitted hash-bound `requests.jsonl` input. Neither created a candidate
CUDA/request marker or an interpretable result. Both raw diagnostics and the
hash-bound repair record remain under `artifacts/full-arrival-20260725t032508z/`
and `artifacts/full-arrival-20260725t032620z/`. The complete bound input set
is now materialized project-locally and the same unconsumed candidate arm was
relaunched at `03:28Z` under
`artifacts/controller/RETRY_OWNER_STATE.json`; it owns claim heartbeats and
terminal retrieval through 04:20Z.

## 2026-07-25 — consumed endpoint: invalid candidate path

The sole candidate-only full-arrival endpoint completed all 1,036 requests in
`732.446450 s` at `$0.139602/M` with peak queue `9`, final queue `0`, and
stable individual release drift. Those transport/economic fields are measured,
but the candidate does not pass its endpoint contract: `overlay` is `null`,
`overlay_trace_rows` is `0`, and normalized semantics are false due to request
790. The terminal contains a candidate-start marker and complete response rows,
so this endpoint is consumed and must not be replayed.

Interpretation: the persisted result cannot establish a request-local verified
trunk effect—the required candidate-path proof is absent—and its semantic
failure fails the preregistered gate. This is an invalid integration outcome,
not evidence that the causal mechanism is ineffective. Conservative cumulative
provider exposure is `$0.5896552755` (from `OWNER_TERMINAL.json`), below the
reserved `$3`; the healthy loaded server is in maintenance for director
disposition. Any repair requires a separately authorized arm because the sole
endpoint is consumed.

## 2026-07-25 — activation defect localized; discriminator dispatched

Bound inspection of the retained container `/work/out` found neither
`OVERLAY_STATE.json` nor `request-local-ngram.jsonl`. The installed overlay
bytes matched the director hash, but Python imported Debian's
`/usr/lib/python3.12/sitecustomize.py` before the file placed in
`/usr/local/lib/python3.12/dist-packages`. The endpoint therefore never ran
the intervention; request 790's mismatch is not evidence of an
ownership/tree-mask/acceptance/cleanup defect.

The repair changes only this proven activation/telemetry path: install the
overlay at the effective startup location, fail closed on container-local
activation plus `worker_initialized`, and record request 790's draft tokens,
tree masks, accepted indices, ownership, corpus updates, and cleanup. Durable
owner `artifacts/controller/REPAIR_OWNER_STATE.json` is live and heartbeating
the claimed warm H200 through the 04:20Z bound. It restarted the retained
server and is running the unconsumed requests-0-through-790 sustained-load
discriminator; a full endpoint is conditional on exact semantics and positive
activation proof. No control or settled arm is replayed.

The first repaired restart then failed before science: SGLang passed
`server_args` by keyword, while the overlay indexed positional `a[0]`.
`artifacts/repair-localization-20260725t035415z/OWNER_EXCEPTION.json` binds
the traceback; no discriminator request ran. The constructor binding alone
was amended, a hash-bound `REPAIR_REQUEST.json` was recorded, and durable
same-claim owner `artifacts/controller/REPAIR_OWNER_RETRY_STATE.json` resumed
the still-unconsumed discriminator.

Activation subsequently passed fail closed. Three preserved request-start
attempts produced no interpretable rows and do not consume the discriminator:
the first exposed a reversed archive-copy helper, while the later server
crashes localized `request_local_tree_underfilled` first without owned local
state and then after the first verified update. The proven defect was
token-deduplicating union of repeated native BFS filler. Final unexecuted
overlay `d1b5926949729dcc36da61ccebb19ce858b003c28ea98c8f19efe30b56285b95`
uses exact native fallback until the rid owns verified state, then reserves
the local trunk and copies the earliest native BFS suffix with ancestry
remapped.

At 04:11:53Z, the remaining release window was shorter than request 790's
bound 548.742-second arrival plus completion, so another run could only be an
invalid partial attempt. The unoccupied crashed bench was released draining
to maintenance at 04:13:07Z. Activation is proved; the localization
discriminator and conditional full endpoint remain unconsumed. Conservative
cumulative exposure is `$1.08`.

## 2026-07-25 — rebound lifecycle dispatch

The rebound `DIRECTOR_BINDING.json` was mechanically reverified and the
project-local overlay again hashed to
`d1b5926949729dcc36da61ccebb19ce858b003c28ea98c8f19efe30b56285b95`.
One bounded outer controller, recorded in `STATUS.json.active_session`,
atomically claimed the retained H200 at 04:20:28Z and is heartbeating through
the 05:03Z release deadline. It has staged the bound overlay, restarted the
resident container, and persisted positive container-local overlay activation
evidence. The still-unconsumed 0-through-790 request-local discriminator is
the only active scientific arm; a full endpoint remains conditional on its
retrieved exact semantic result.

## 2026-07-25 — repaired discriminator: semantic reject

Measured result: the bounded 0-through-790 discriminator completed all 791
individual arrivals and retrieved a complete terminal at
`artifacts/repair-localization-20260725t042028z/out-discriminator-0-790-repair-localization-20260725t042028z/FINAL_TERMINAL.json`
(`a5046174…5430de6c`). Activation is positive: it names the admitted overlay
SHA-256 and records 3,078 overlay trace rows. There were zero request failures,
but normalized semantics are false: request 170 first changes from token
`51935` to `3055` at output token 38. The discriminator also reaches peak
queue 41 and `$0.300099/M`, above the retained gates.

Interpretation: this is a complete, decision-bearing candidate sample, not a
retrieval or activation defect. The conditional full endpoint is therefore
not admitted and neither this discriminator nor any settled arm may be
replayed. The owner retrieved the compact archive and released the loaded
server to maintenance at 04:41Z. Conservative cumulative project exposure is
`$1.9313543586132855`.
