# Research log

## 2026-07-24 — bind one executable DFlash route

Action: selected SGLang because PR #23000 is merged. Bound merge commit
`588d1f7bc9424201f89957e145f9d5af633a3eb8`, draft revision
`eabd648301ce28583cc14757912e5e0f84e152e1`, Dockerfile/dependency hashes, and
the DFlash worker/Triton source hashes in `DRAFT_RUNTIME_BINDING.json`. Added a
project-local AR/DFlash workload consumer, reconciler, and remote build/run
script. `bash -n`, `py_compile`, and binding-schema validation passed.

Evidence: the source registers `DFLASH`, supports a 16-token draft block and
the immutable draft revision, and contains target-hidden/KV state guards. vLLM
PR #41703 remains open. This is source-backed/offline integration evidence, not
a GPU performance or quality result.

Next: director registration of one independent H200 within the $28 authority;
the exact request is `DIRECTOR_REQUEST.json`. The shared NGRAM bench was not
claimed.

## 2026-07-23 — independent H200 execution started

Claimed `h200-dflash-e00q45wf04571cb67n`; H200 identity, driver 580.159.04,
Docker 29.5.3, and 225 GiB free disk were measured. The first remote owner
failed before source build because `/work` is not writable; the second reached
the pinned source checkout but lacked Docker-socket access. Both are
pre-invocation wiring defects with no model server, CUDA candidate, or workload
request. The claim remains active. Repair 2 uses a writable remote work root
and `sudo docker`; it is building the immutable SGLang image and retains source
and downloaded layers. Artifacts: `artifacts/dflash-h200-20260723t2343z`.

## 2026-07-24 — repair4 import terminal; repair5 continues in place

Measured pre-invocation terminal: image `sha256:e39df6f32da98c31caa4cdaccd33b2e5a23ada7cc2c46d0094d9d865f50bee2c`
built successfully, but its AR server exited while importing SGLang because
`openai==2.6.1` required missing `distro`. Retrieved owner stderr, Docker
inspect, and Docker log establish no health endpoint, workload, model CUDA, or
candidate invocation. This is an ordinary image dependency defect, so the
same claimed H200 remains warm and repair5 appends only `distro==1.9.0` after
the local editable install. It preserves the pinned SGLang commit, exact model
and draft revisions, workload, and decision gates; the remote owner is PID
`189256` under the existing deadline. Evidence is in
`artifacts/dflash-h200-20260723t2343z/retrieved-repair4/`.

Repair5 then proved the staging heredoc was not attached to Docker stdin, so it
silently left `/models/target` absent; the server rejected the local path
before model load. Repair6 retains its image/source layers and changes only
`docker run` to `docker run -i` for that snapshot-download producer. No
workload request or CUDA model execution has been accepted.

Repair6 successfully staged the exact 59-GiB target and 2.9-GiB draft and
loaded the AR target server (121,960 MiB GPU), then failed before the runner's
first request because `/work/project` was an empty host mount. The loaded
producer remains resident. Repair7 corrects the host mount and copies only the
runner into that producer before resuming the unchanged four-request diagnostic.

## 2026-07-24 — DFlash target-runtime incompatibility

Measured: the preserved AR diagnostic completed 4/4 requests of 4,214 prompt
and 358 completion tokens in 19.496 s batch time (4.874 s/request), with raw
SSE retained. Its token-ID field was absent. The DFlash startup then loaded the
same target and draft but failed before a candidate request when SGLang required
`Gemma4ForConditionalGeneration.set_dflash_layers_to_capture`, which this bound
target class does not implement. This is a typed upstream target/runtime
incompatibility, not a latency or quality result; the conditional c32 pair is
therefore not admitted. Raw producer, startup terminal, inspection, and hashes
are under `artifacts/dflash-h200-20260723t2343z/retrieved-terminal/`. The
conservative claimed-provider exposure through terminal capture is `$7.11`.

## 2026-07-24 — capture-hook continuation reaches the candidate runtime

Bound the exact upstream Gemma 4 capture contract to pinned SGLang: requested
checkpoint layers `[1,12,23,35,46,57]` map to Gemma's ascending pre-layer
capture indices `[2,13,24,36,47,58]`, producing six width-5376 features without
altering the target forward. Two pre-science defects (the image banner in a
module-path probe and native `seed` versus `sampling_seed`) were repaired with
the same model, image, workload, and gate. The seed failure was retained
separately because all four streams stopped before scheduler admission and
DFlash verification.

The first decision-bearing DFlash diagnostic then initialized the draft runner,
accepted four native requests, executed target prefill, reached 100% GPU
utilization and 131,052 MiB HBM, and returned one token on two requests before
the scheduler raised: `DFLASH greedy sampling requires a vocab-parallel head
with weight and shard_indices`. Pinned Gemma 4 ties logits to
`language_model.embed_tokens`, so the exact DFlash greedy-head contract is not
satisfied. This is a measured target/runtime incompatibility after candidate
execution, not a performance result. The diagnostic is consumed, no retry is
allowed, and the conditional c32 pair was not started. Cumulative conservative
provider exposure is `$8.249`; the retrieved archive hashes to
`f6deb8624962c8bae7f232b2bbaa7428a07b204b543b541dee04c82b291d7413`.

## 2026-07-25 — tied-head adapter continuation admitted

The director reopened only the untested tied-head interface. The prior run
proved target capture, draft initialization, request admission, and target
prefill; it did not execute a Gemma-compatible vocab-parallel adapter. The new
lane first proves that an unchanged TP=1 tied embedding projection satisfies
the greedy-head consumer exactly, then earns one fresh diagnostic and
conditional c32 pair. Prior `$8.249` exposure remains settled.

## 2026-07-25 — exact TP=1 adapter gate passes; H200 unavailable

Verified every immutable reopening hash. At pinned SGLang
`588d1f7bc942`, `Gemma4ForConditionalGeneration` assigns `lm_head` to the
same `language_model.embed_tokens` module at PP=1; DFlash's exact greedy
consumer reads only its `weight` and `shard_indices`. The adapter therefore
attaches the full `[0,262144)` original-vocabulary range to that existing
module, rejects TP/PP other than one, and leaves the module, Parameter, data
pointer, logits path, target forward, and checkpoint bytes unchanged.

Measured offline through the real pinned
`DFlashWorker._greedy_sample_from_vocab_parallel_head`: all 1,048,576 BF16
logit elements were bit-exact and boundary/tie fixtures returned
`[0,262143,0,262142]` as expected, including lowest-index tie resolution.
The result is
`artifacts/tied-head-adapter-offline-20260725/TIED_HEAD_ADAPTER_FIXTURES.json`
(`1e2648d8...7e42`).

The immutable no-restaging packet
`artifacts/tied-head-adapter-inputs-20260725.tar`
(`00efd6d5...7c68`) runs only the adapted four-request DFlash diagnostic and
its conditional matched c32 pair; it embeds the consumed AR text bytes needed
by the gate. An atomic `nvidia-h200-sxm` pool claim returned “no available GPU
bench matches this project.” No GPU was claimed, no science invocation ran,
and new spend is `$0`. Exact resident H200 requirements are now in
`STATUS.json.bench_need`; director provisioning/registration is the typed
external blocker.

Budget reconciliation: the turn contract labels the current `$18` reservation
as cumulative across all project allocations. Subtracting the settled
`$8.249` leaves at most `$9.751` for the future H200 claim; this stricter
current contract supersedes the reopening artifact's larger new-spend field.
## 2026-07-25 execution continuation — fresh H200 owner launched

Question: can the bound TP=1 tied-head adapter unlock the exact DFlash consumer on a fresh H200 while preserving greedy target semantics?

Action: mechanically verified the director binding and every bound hash, including target/draft/runtime input packet contents, then claimed `h200-dflash-adapter-e00vyqp7gxsr34wrtz` once. The first owner attempt failed pre-science because the fresh disk lacked `/home/glmrunner/gemma4-dflash`; the second exposed the same controller shell boundary before SSH. A bounded foreground smoke probe localized the issue and crossed remote directory creation plus pinned SGLang clone. The owner was patched to derive the archive hash from the binding and avoid the faulty shell construction.

Evidence: the durable controller at `artifacts/tied-head-adapter-owner-20260725t153031z-retry2` is live under `unit_manager: pid`, PID `841139`, start ticks `110944877`, and has reached the bound SGLang image build. No server, CUDA invocation, or scientific request began in the invalid attempts. The active command graph stages only target `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, draft `eabd648301ce28583cc14757912e5e0f84e152e1`, runtime `588d1f7bc9424201f89957e145f9d5af633a3eb8`, and the bound reconstructed image, then invokes `remote_tied_head_adapter.sh`.

Interpretation: the adapter gate and immutable binding remain valid; the observed failures are ordinary controller/staging defects, not scientific evidence. The owner retains the claim through staging, adapted four-request diagnostic, conditional c32 pair, typed retrieval, server stop, and release by 21:45Z. Never replay the old unadapted or historical AR diagnostic.

Next move: retrieve and interpret the owner terminal when it completes; promote only a real DFlash diagnostic gate and exact c32 result.
## 2026-07-25 repair continuation — resident manifest observer

The first durable owner stopped pre-science after exact target/draft materialization and pinned image construction because `sha256sum` traversed root-owned Hugging Face `.cache` metadata. Remote evidence (`artifacts/REPAIR_DIAGNOSTIC_REMOTE.txt`, SHA-256 `312abc31d0926c00b55c84927957158a77ee759aa162f585922f7a45d8ff2df6`) confirms the pinned source commit, target files, draft files, and base image are resident; no container or scientific invocation was running.

`REPAIR_READY.json` records the typed recoverable boundary. The launcher was amended only to reuse existing model/image bytes and exclude `.cache` metadata from the resident manifest while hashing the actual model files. A same-claim repair owner is now durable at `artifacts/tied-head-adapter-owner-20260725t160538z-repair1` (PID `874035`, start ticks `111155641`, `unit_manager: pid`) and continues directly to `remote_tied_head_adapter.sh` after manifest persistence.
## 2026-07-25 terminal — adapted DFlash semantic rejection

The persisted four-request DFlash producer was repaired in place without rerunning science: the runner incorrectly parsed cumulative `output_ids` and the terminal `[DONE]` frame. Reconstructed rows contain 358 raw token IDs for all four requests. A second consumer repair accepted the pinned runtime's measured `Decode batch ... accept len` telemetry because this SGLang commit does not emit the older `DFLASH verify completed` phrase.

Measured gate: all 4 requests completed, but candidate text matched the consumed AR control for only 2/4 requests. The diagnostic therefore fails deterministic target-token semantics. Observed acceptance telemetry was 2 `accept len` events, mean 4.77 accepted drafts per observed event (9.54 total from the observed log events). The matched c32 AR/DFlash pair was not started. This is a scientific integration rejection, not a performance result; no endpoint promotion is authorized.

Final typed terminal: `TIED_HEAD_ADAPTER_H200_TERMINAL.json`. Raw producer archive and repaired gate remain preserved under `artifacts/dflash-diagnostic-repair*`. The healthy DFlash server is being stopped and the H200 released ready after final state retrieval.

## 2026-07-25 offline continuation — first divergence and depth controller

Measured persisted evidence is more specific than the 2/4 text gate: each
candidate row contains 358 copies of one token ID. Request 2 differs from the
consumed AR stream on output zero (`Is` versus `On`); request 1 repeats
` hasher` for 228 outputs before AR changes. The other two prompts naturally
repeat their initial token text for the full forced completion and therefore
cannot validate state advance. Aggregate SSE metadata supplies 314 actual
verify cycles, 1,122 accepted drafts, 4,710 proposals, and the full accepted-
draft histogram, but the consumed AR route has no token IDs and neither route
persisted per-cycle logits, KV locations, or carried state. The narrowest
proven boundary is therefore the first prefill-output/verify-settlement cycle;
offline artifacts cannot decide whether target logits or later settlement
first fail.

Source comparison identifies one falsifiable owner-state repair. Pinned SGLang
`588d1f7bc942` defaults `direct_carry_valid=True`, bypassing its request-indexed
FutureMap relay for bonus IDs and new sequence lengths. Later v0.5.15 removes
direct carry and always relays request-indexed state. The apply-checked
`DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch` changes that default to false,
without changing verifier math, acceptance, KV geometry, or model bytes.
`dflash_cycle_oracle.py` now checks draft proposals, target top-1 logits/IDs,
maximal acceptance, bonus, KV positions/locations, committed length,
next-cycle seed/length, and ordinary AR; exact pass and stale-relay fixtures
both behave as preregistered. This is a source-supported repair candidate, not
a measured semantic fix.

The conditional c32 controller uses the 314-cycle histogram and the existing
H200 c32 fixed-M384 trace. Its M12 model-kernel/full-GPU-active proxy envelope
is 137.316–147.819 ms per cycle. Expected emitted tokens at depths 4/8/12/16
are 3.5350/4.4586/4.5605/4.5732. Depth 8 wins the half-fixed cost envelope;
under a row-proportional verifier, depth 4 wins until fixed block-16 draft cost
exceeds about 0.943 times M12 verify cost, then depth 8 wins. This is a
controller construction only: survival came from a semantically invalid run
and non-M12 verifier costs are analytical until a lossless DFlash measurement.

Result: `OFFLINE_DFLASH_REPAIR_RESULT.json`
(`6f5c24ea...3692f`). New provider spend is `$0`; no bench was claimed or
modified. Next is one fresh director-bound cycle capture with the patch and
oracle, followed only on pass by DFlash-specific c32 depth-cost measurement.

## 2026-07-25 — bound preclaim verification

All eight local artifacts referenced by
`DIRECTOR_DFLASH_CYCLE_ORACLE_BINDING.json` matched their bound SHA-256
digests. The exact upstream `588d1f7bc942` `dflash_info_v2.py`,
`dflash_worker.py`, and `dflash_worker_v2.py` also match the source digests
recorded by the repair evidence. The required predecessor has neither a
durable `MIXED_LOCAL_M384_TERMINAL.json` nor a released claim; its PID owner
is live and the H200 has a current heartbeat. No H200 connection, claim, or
provider expenditure was made. The next admissible action remains the bound
atomic claim after that terminal and release.

## 2026-07-25 — offline DFlash depth-cost validity terminal

Question: do the retrieved depth-4/8/12/16 CUDA events support the bound c32
cost controller independently of the failed `/generate` stream consumer?

Action: bound the identical observer bytes at all four depths and traced each
positive pair to one `DFlashWorkerV2.forward_batch_generation` decode call
containing draft forward then target verification. Classified 96 zero-draft
rows as target-only prefills and excluded them. Because every fresh server set
`--skip-server-warmup` and its first paired row had the maximum draft time,
excluded exactly that one row per depth. Retained every later finite paired
row: changing live-batch geometry makes the distributions multimodal, and no
immutable batch-size label justifies statistical deletion.

Measured evidence: 1,204 paired controller rows remain (277/332/261/334 for
depths 4/8/12/16). Summed draft-plus-verifier CUDA-event costs are
21,888.582/23,082.174/22,030.279/24,589.311 ms. For the fixed 32 x 358-token
producer budget, depth 4 minimizes measured cost, 0.647% below depth 12. All
128 response streams contain final `[DONE]` frames and bound token-count
metadata, but all four request terminals still have zero complete requests
because the consumer attempted to JSON-decode `[DONE]`; they authorize no
endpoint latency, quality, token-identity, or equivalence claim.

Decision: `DFLASH_C32_DEPTH_COST_TERMINAL.json` passes with
`first_invalid_field=null` and selects depth 4. No GPU was claimed, the
112-cycle oracle was not replayed, no endpoint pair ran, and new provider
spend was `$0`. The current phase's previously measured H200 exposure is
reconciled at `$2.9737686855`; any depth-4 endpoint pair requires a later
director decision after grouped-head.

## 2026-07-25 — depth-4 endpoint terminal

The offline `/generate` SSE repair passed against the immutable retained
depth-4 fixture: 32/32 complete responses, exactly 358 final (not cumulative)
raw token IDs each, length finish reasons, and usage fields. One and only one
matched c32 AR/DFlash-depth-4 pair then ran on the retained H200 and released
the bench at `19:56:22Z` after 425.513 claimed seconds (`$0.289585`).

Both arms completed 32/32 with 358 raw IDs, unique request ownership, no
failures, and accepted-prefix telemetry. DFlash was slightly faster than its
paired AR control (`1.511282239` vs `1.528631381 s/request`) but missed the
qualified denominator (`0.625149102`) and campaign target (`0.500119282`).
More importantly, emitted target-token equivalence and cache/accounting
equality failed, so this is a quality/integration rejection rather than a
performance claim. The raw terminal is `DFLASH_DEPTH4_ENDPOINT_TERMINAL.json`
(`02a59aae…75015`); no replay is authorized.

## 2026-07-25 — request/cycle replay falsifies the relay-only repair

Question: where does the retained depth-4 c32 producer first lose equality
between the AR target trajectory, DFlash request state, and emitted stream?

Action: reconstructed every request from the raw cumulative SSE. The bound
server used `stream_interval=1` and non-incremental output, so each distinct
DFlash prefix is one prefill or verify emission. The offline replay validates
all 64 final SSE prefixes against the terminal rows and all 32 request hashes
across arms. A deterministic request-0 fixture uses measured cycle boundaries
10/11/12 and synthetic draft proposals to cross a zero-accept rejection, a
nonempty accepted prefix, bonus selection, committed-length advancement, and
the subsequent cycle. It passes all state equations.

Measured result: 12/32 request streams differ from AR. In deterministic
request-index order, request 2 first differs at prefill cycle 0/output 0:
target AR token `4602`, DFlash token `2791`. Requests 27 and 28 also differ at
token zero. The pinned DFlash worker returns
`target_worker.next_token_ids` directly on this prefill path, before verify
acceptance, bonus settlement, commit advancement, or next-cycle relay.
Independently, request 25 has an AR-equal prefill/pending seed `236814` and
then differs in verify cycle 1/output 1. That cycle accepts zero drafts, so its
single output is the target bonus: AR `3496`, DFlash `759`. Later first
differences are localized to exact accepted-prefix or bonus positions, but the
producer did not retain verifier logits, `verified_id`, KV locations/content,
or committed-length tensors, so it cannot separate wrong verifier output from
wrong hidden sequence/KV state.

Cache evidence is orthogonal. Per-request equality still fails, but both arms
report exactly 15,515 cached prompt tokens (29 x 535). The three zero-hit
owners rotate from AR requests `[10,15,30]` to DFlash requests `[12,21,23]`.
This is prompt-prefix cache attribution under different concurrent admission,
not a trace of decode `kv_committed_len` or KV contents.

Decision: terminal invariant-level falsification. The previous
`direct_carry_valid=False` patch repairs a synthetic request reorder, but the
pinned filter/merge path already disables direct carry after reorder and the
three measured prefill failures occur before relay. It is rejected as a
sufficient exact repair; no smaller exact source change is supported by the
retained evidence. Result:
`DFLASH_REQUEST_LEVEL_REPAIR_RESULT.json`
(`3b7d6879…3ec2`); replay
`dflash_request_cycle_replay.py` (`9e3289d8…4a00`); fixture
`artifacts/request-cycle-replay-20260725/REQUEST_CYCLE_REPLAY_FIXTURE.json`
(`8dae7cf4…217b`). No GPU was claimed or touched, no endpoint was replayed, and
new provider spend is `$0`.

## 2026-07-25 — exact request-state observer bound; predecessor queue active

Question: can one read-only exact-c32 capture distinguish target prefill,
prefill-to-verify KV/length commitment, and the first target-verifier result
without changing tokens or replaying a valid producer after a consumer defect?

Action: materialized the admitted pinned DFlash, TP-worker, ForwardBatch, and
hybrid-KV source bytes under `inputs/bound/`; bound return sites for target
prefill, the first ordinary AR target step, and the first DFlash
verify/accept/bonus step. The observer maps dynamic request slots through the
workload's unique request marker, records sequence lengths and KV locations,
and hashes one deterministic K and V coordinate for every referenced location
across all 60 target KV layers. The largest prefill transfer is bounded at
32,363,520 BF16 bytes with one host-transfer synchronization and no explicit
CUDA synchronization. It never writes model, sampler, acceptance, relay, or
cache state. The outer owner preserves a completed AR producer, retrieves
remote terminal/log/start evidence before release, and repairs a failed
consumer without rerunning either endpoint arm.

Evidence: six no-CUDA serialized fixtures pass, including permuted exact-c32
ownership, duplicate-marker failure, result-identity pass-through, event
digest determinism, KV-digest plane segmentation, and an end-to-end typed
consumer that localizes the request-25 first-verifier mismatch.
`REQUEST_STATE_CAPTURE_READY.json` (`49a4fafb…c7d5a`) binds the 327,680-byte immutable packet
`artifacts/request-state-capture-ready-20260725/REQUEST_STATE_CAPTURE_PACKET.tar`
(`c8f8759e…1da36`).

Boundary: the single queue check at `22:15:26Z` found certified-lazy actively
holding `h200-dflash-adapter-e00vyqp7gxsr34wrtz`; its typed terminal was absent.
FP8 was still active and queued next with no terminal. The bench retained
194.57 lifecycle minutes, but availability alone cannot override the named
order. `EXACT_REQUEST_STATE_CAPTURE_QUEUE_BLOCKER.json` records this external
boundary. No GPU claim or CUDA call was attempted, provider mutation was
false, and this continuation's actual spend remains `$0`. The next admitted
turn checks both terminals and the inventory once, then launches the bounded
owner only if both predecessors released and at least 50 lifecycle minutes
remain.

## 2026-07-25 — retained H200 capture stopped at source-binding preflight

Question: execute the director-authorized one exact-c32 AR/DFlash request-state
capture on the retained H200 without changing the scientific scope.

Result: a bounded owner claimed `h200-dflash-adapter-e00vyqp7gxsr34wrtz` and
used `sudo -n docker` for the first execution-equivalent pinned-image check.
It fail-closed before server start, CUDA invocation, or any request sample.
The remote terminal is `stage=preflight`, `active_arm=none`, and
`science_started=false`. The pinned image matched the admitted bytes for
`dflash_worker_v2.py`, `tp_worker.py`, and `forward_batch_info.py`, but not
`dflash_info_v2.py` (`b17ff… -> eb976…`), `memory_pool.py`
(`37f991… -> 26ce12…`), or `swa_memory_pool.py`
(`36830c… -> fefdca…`). This is a binding-metadata defect, not a scientific
measurement or a DFlash negative.

The controller retrieved the terminal, installed-source digest transcript,
and raw logs before releasing the bench to maintenance. Two pre-science owner
defects (a legacy inventory shape assumption and missing remote staging parent)
were preserved as invalid attempts; no producer or endpoint arm was replayed.
The attempted repair handshake only finalized this typed disposition and did
not modify source bytes or the question. Conservative current-turn provider
exposure is `$0.0657742666388889` (96.649062 claimed seconds), within the
`$2.00` reservation. See `DFLASH_EXACT_REQUEST_STATE_CAPTURE_TERMINAL.json`
(`c22995…69ed7`) and
`artifacts/request-state-capture-owner-20260725t2300z/retrieved-final/`.

Next: director rebinds the three observed image bytes immutably before any new
exact-c32 request-state capture is admitted. Do not count or replay this
preflight as a sample.

## 2026-07-25T23:09:33Z — source-identity rebinding admitted

The director consumed the typed preflight and issued
`DIRECTOR_EXACT_REQUEST_STATE_CAPTURE_REBINDING.json`. It binds all six
installed source identities to the retained pinned image, authorizes only
packet-metadata rematerialization plus the existing offline fixtures, and then
admits one unchanged exact-c32 capture with `sudo -n docker`. DFlash is the
sole H200 claimant at priority 8560; the corrected FP8 sm90a discriminator
serializes after this terminal. No source-byte change, failed-preflight replay,
endpoint tuning, repair implementation, or provider lifecycle mutation is
authorized.

## 2026-07-25T23:15:13Z — rebinding gate passed; retained bench is externally unavailable

The director-bound six-hash installed-source inventory was rematerialized
without changing any `inputs/bound/` source bytes. The rebinding packet
(`artifacts/request-state-capture-rebinding-20260725t2309z/REQUEST_STATE_CAPTURE_PACKET.tar`,
SHA-256 `221d2166…7f806`) and manifest (`994789ab…a1cea`) are durable; all six
existing no-CUDA observer fixtures pass. The remote capture script now uses
`sudo -n docker` for every Docker operation, and the outer owner accounts for
the prior `$0.0657742666388889` exposure cumulatively.

The required atomic pool claim was then attempted once. It failed before any
remote access, CUDA invocation, or scientific request because the named H200
is still `maintenance` with no claim, while the pool admits only `available`
benches. `DFLASH_EXACT_REQUEST_STATE_CAPTURE_AVAILABILITY_BLOCKER.json`
records this typed external boundary. No lifecycle or provider state was
mutated, no sample was consumed, and the authoritative project ledger records
`$0.110010858903` cumulative capture exposure (including prior retained-bench
accounting). The lab owner/director must reconcile that maintenance
state to `available`; then the prepared single capture can claim atomically.

## 2026-07-25T23:27Z — exact AR producer preserved; observer consumer boundary

The director-reopened owner atomically claimed the named H200 and used the
project-local rebinding packet. The initial image-source check failed only
because the image banner preceded six valid SHA-256 lines on stdout; this was
an ordinary preflight framing defect, with `active_arm=none` and no science
marker. The in-place repair filtered only canonical digest lines, required all
six, and retained the same claim.

The repaired execution loaded the exact model/KV state and completed the sole
AR c32 producer: `complete_requests=32`, `pass=true`, terminal SHA-256
`45b8120b…141af4`. The observer captured `ar-c32.jsonl` (SHA-256
`292786e6…30d94`) but fail-closed on mixed request markers and request-slot
rebindings. Thus it did not yield the required request-state comparison or a
scientific project terminal. The producer is consumed exactly once and must
not be rerun; the defect is a typed observer-consumer integration boundary.

The owner retrieved the compact terminal, raw server/worker output, producer
responses, state stream, and observer errors before releasing the bench to
maintenance. Its cumulative project exposure is `$0.30443484876411114`,
leaving `$1.695565151235889` of the `$2.00` reservation. A later director
re-admission must reactivate the retained bench and authorize a
consumer-only repair against these durable artifacts; it must not replay the
completed exact-c32 endpoint arm.

## 2026-07-25T23:43Z — authoritative RID lifetime and candidate-only observer repair

Question: derive request ownership from the immutable 32/32 AR terminal, 28
captured events, 10 observer errors, and pinned request/cache-pool source,
without claiming a GPU or replaying AR.

Result: pinned `ForwardBatch.init_new` copies `ScheduleBatch.reqs[i].rid` into
the unpadded host list `ForwardBatch.rids`, while `ReqToTokenPool` reserves row
0 for padding, reuses a retained slot during chunked/committed-prefix work,
and returns that physical slot to `free_slots` at request release. Therefore
RID is the logical lifetime; `req_pool_indices[i]` is only current-row physical
telemetry and may legally rebind after release. The old process-global slot
map and prompt-marker scan explain all retained errors (8 mixed-marker, 2
slot-rebinding) and cannot repair the 28 old events retrospectively because
they did not retain RID.

Implemented schema-v2 capture records `ForwardBatch.rids`, excludes padded
rows by `len(rids)`, slices padded KV-location arrays by exact host extend
lengths, and performs the request-index join only against the candidate
terminal's returned request IDs. The candidate-only consumer compares target
prefill and first verify/accept/bonus/stream state directly to the immutable
AR token stream, so no AR state replay is needed. Eight CPU fixtures cover
padding, row reordering, slot recycling, fail-closed RID validation, padded KV
locations, serialized RID joins, and first-verifier localization.

Terminal: `DFLASH_REQUEST_OWNERSHIP_OBSERVER_REPAIR_TERMINAL.json`
(`f13f08e4…8837a`). Content-addressed packet:
`artifacts/request-ownership-observer-repair-20260725T234315Z/packet/3407231b…9174`.
No GPU was claimed, no endpoint was launched, no request body was changed,
and provider spend remains `$0.30443484876411114`. DFlash candidate sampling
is still unconsumed and requires a later director re-admission.
