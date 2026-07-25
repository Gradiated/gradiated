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
