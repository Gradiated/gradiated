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
