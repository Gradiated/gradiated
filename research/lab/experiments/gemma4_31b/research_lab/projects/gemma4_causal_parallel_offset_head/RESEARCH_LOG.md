## 2026-07-26 — offline causal offset-head discriminator

Question: can one shared Gemma causal head emit offsets 1–16 and support the
locked `0.500119281574996 s/request` target without changing target
verification or KV authority?

Action: bound pinned Gemma/SGLang producer, tied-head consumer, acceptance, and
KV-compaction source locally; implemented the 6.301M-parameter rank-256 causal
head, offset-weighted loss, one-pass request-owned layer-45/54/60 capture,
deterministic trainer/holdout evaluator, exact-shape fixture, immutable
request-disjoint 4096/512 split, and full draft-plus-verify cost model.

Evidence: `EXACT_SHAPE_FIXTURE.json` executes
`[32,16,5376] -> [512,262144]` with BF16 taps/weight and FP32 logits on
PyTorch meta tensors. `artifacts/capture-fixture/CAPTURE_FIXTURE.json`
preserves request ownership through a forced reorder. The H200-bound grouped
depth-12 tied head is `4.182975769 ms`; linear depth-16 accounting plus the
causal allowance is `6.077301025 ms/call`. Measured DFlash verifier cost rises
`1.141709834x` from depth 12 to 16. With the same-distribution measured
`10.664799253` current accepted target tokens and the measured GPU interval
union, the optimistic service threshold is `16.054` accepted target tokens,
or `94.0875%` of the maximum 16-token draft prefix. Perfect acceptance
projects to `0.474599747 s/request`; `16.05` projects to
`0.500232052`, above target.

Interpretation: an analytical path exists only near perfect prefix survival,
but there is no real target-tap disjoint holdout or trained checkpoint. The
project has `$0` provider authority, so no compatible capture/training venue
is in scope. No synthetic acceptance was substituted and no GPU sample was
consumed. The director-bound semantic-localization digest also mismatches the
current cross-project bytes (`7fef...34f2` expected, `7e59...a46b` observed),
so those mutable bytes were not consumed.

Next: director consumes `CAUSAL_PARALLEL_OFFSET_HEAD_RESULT.json`. Reopen only
with positive spend for the single hash-bound capture/train/holdout cycle in
`EXPERIMENT_CONTRACT.json`; do not write READY until the disjoint holdout
clears `16.054` and a matched GPU command exists.

## 2026-07-26 — H200 owner and admission binding

Question: can the admitted one-cycle H200 falsifier be made executable without
claiming a provider bench before the exact reservation is consumed?

Action: implemented `run_h200_capture_train_owner.py` and hash-bound it in
`H200_CAPTURE_TRAIN_READY.json`. The owner uses the proven H200 lifecycle
identity, requires a director receipt for exactly `$14`, atomically claims and
heartbeats a shared inventory bench only after that receipt, stages a
project-local immutable packet, runs the pinned SGLang capture command and the
existing deterministic trainer, and has no endpoint-pair branch.

Evidence: owner syntax and CLI checks passed; the bound owner digest is
`f27a6dc22d11cf91cbef887a14e33819f74f564afd0f9bbe521234bb02e05e38`.
`H200_CAPTURE_TRAIN_READY.json` binds the admission, split, cost model, source,
and mechanism digests. No GPU was claimed, no provider was created, and no
scientific sample was consumed.

Next: the director must consume READY together with the exact `$14`
reservation and provide an eligible shared H200 bench. Then run exactly one
capture/train/request-disjoint holdout cycle; endpoint work remains closed.

## 2026-07-26 — repaired H200 owner execution seam

Question: can the rejected H200 owner be repaired before provider use without
changing the single-cycle causal-head experiment?

Action: replaced the absent staged entrypoint with the pinned image's direct
`python3 -m sglang.launch_server` invocation; staged `exact_runner.py` at its
actual `/work/input/exact_runner.py` path; added health/exit checks and an
in-container marker immediately before the first capture request. The owner
now uses `repair-handshake ready/wait` to retain its live claim across
pre-science staging, launch, and health defects.

Evidence: the corrected owner hash is
`d5a04e12fe2afaee9025cea81492c84e7ec8b53dc5e17df45aec3650b14c84fd` and
the corrected READY binds director repair
`81602ebc94220b9f02c49888e2b2fd01c73935b052db003b52b713d082d59c47`.
No provider operation, claim, CUDA work, or scientific sample occurred.

Next: director consumption of this corrected READY remains required before a
single durable H200 cycle. Endpoint pairs remain unauthorized.

## 2026-07-26 — repair-2 paid-stage preservation

Action: split the owner into capture and training/holdout stages. Capture now
retrieves `CAPTURE_TERMINAL.json` and `chunks.jsonl` to the controller and
writes `CAPTURE_STAGE.json` before training begins. A later defect enters a
fresh repair generation under the same heartbeat and resumes only the consumer.
Success requires local `HOLDOUT_RESULT.json` plus a retrieved
`head_checkpoint.pt` whose digest agrees with the holdout record.

Evidence: corrected owner digest
`ceede7e73c373d1222585c20f0681e079c3eb91d321838cf423c4861400c22ae`; READY
binds repair-2 digest `b73d0da55aced0ff0b80c47461ed1c5a4e78f8cf0f9027963af1e23f561be293`.
No provider action, claim, or scientific sample occurred.

## 2026-07-26 — repair-3 cold checkpoint staging

Action: added `CHECKPOINT_MANIFEST.json` and owner staging that reconciles each
project-local source file against the cold bench. Matched immutable bytes are
preserved; mismatches copy to hash-named temporary files, verify, become
read-only, and atomically finalize. `CHECKPOINT_STAGE.json` is persisted before
the unchanged repair-2 capture/train/holdout sequence.

Evidence: owner `dd3b7a53e264167bf7ad68dbd3a18f4c87ed2b2d502887391c9e174a566607ea`,
manifest `6ea47a70ea0a3bcf4e764b3fb6f9e6ef061e4063d8b3b1fb66d0d50b6aa7105f`,
and repair-3 `ff9804229384d4c93cb59da4389195ef82a39ee153d7309b5c982b316c7e4fb8`
are bound. No provider action, claim, CUDA work, or sample occurred.

## 2026-07-26 — registered H200 dispatch

Action: launched the director-prescribed PID-managed detached owner for
`h200-causal-head-e00b9qw8d6qd7wrjj1`. Its first process exited before a pool
claim because detached-owner correctly precreated its state/log directory and
the owner required that same output directory not exist. This was a local
pre-science idempotency defect; changed only the output-directory creation to
`exist_ok=True`, hash-rebound READY (owner
`6994565778b997da7c6231eb07cc5661c4efd0c2d199728a8995ffc3eaf6788c`, READY
`2c16f2be0af94a2ca59c8e6fbcc112eb5662837e6e4dc407ea14c879bdd400cf`), and
relaunched the exact owner command.

Evidence: PID `2056931`, state
`artifacts/h200-capture-train-20260726t2037z/OWNER_STATE.json`, claimed bench
at `2026-07-26T20:41:17Z`. It is resumably staging and hash-verifying the
bound checkpoint; no capture request, CUDA candidate, training, holdout, or
endpoint pair has started. The retained owner owns heartbeats and repair until
the lifecycle deadline.

## 2026-07-26 — repair-1 observer integration

Question: whether the first capture produced usable request-owned tap rows.
Action: retrieved the compact capture terminal, observer diagnostic, raw
request terminal, and remote marker before changing state. The server was
healthy and all 32 requests completed, but an unmapped warmup/control forward
raised `aux_tap_contract`, leaving zero tap rows and no chunk manifest.
Patched only the capture hook: ignore unmapped control rows, use SGLang's
documented +1 physical-layer capture IDs, and atomically archive a prior
invalid capture root with file hashes before a fresh retry. Submitted the
hash-bound `repair-1` request; the same live owner consumed it and resumed
checkpoint reconciliation.

Interpretation: this is an observer integration invalid attempt, not an
interpretable capture sample; raw 32-request evidence is retained. Training,
holdout, and endpoint pairs remain unstarted. Next: let the retained owner run
the single repaired capture/train/request-disjoint holdout cycle or surface a
new typed repair.

## 2026-07-26 — repair-2 cached-prefix ownership

Question: why repair-1 no longer raised an observer exception but still
persisted zero mapped rows. Action: inspected the repaired capture terminal
and raw 32-request terminal once. The common prefix was cache-resident, so the
forward extend span begins after token 535 and cannot use the original fixed
marker offset. Patched only request ownership to scan each actual extend span
for its submitted marker. The hook will atomically archive the prior invalid
root; repair-2 binds this hook digest and was consumed by the unchanged live
owner.

Evidence: PID `2056931` remains live; its rebuilt packet and resumed manifest
reconciliation are durable. Two prior raw capture roots remain on the bench;
neither has mapped taps or a chunk manifest. Training, holdout, and endpoints
remain unstarted. Next: wait for the repaired capture terminal/manifest, then
allow the owner to consume the sole training and request-disjoint holdout.

## 2026-07-26 — repair-3 explicit runtime ownership

Question: why scanning the cached-prefix extend spans still yielded no marker.
Action: retrieved the observer terminal, raw workload identity, and pinned
SGLang protocol evidence once. The OpenAI protocol exposes `rid`, while the
workload supplied none; normalized model IDs are therefore not a reliable
ownership channel. Bound the unchanged 32 request payloads to
`causal-offset-00` through `causal-offset-31` and mapped only those runtime
IDs in the hook. Repair-3 binds the two mutable files and was consumed by the
same PID/claim.

Interpretation: this is a concrete source-localized observer ownership repair;
earlier raw roots remain preserved, capture remains unmeasured, and no
training, holdout, or endpoint action has started. Next: accept capture only
if nonzero mapped rows and a chunk manifest persist, otherwise retain the
claim for a newly typed in-place repair.

## 2026-07-26 — repair-4 warmup identity isolation

Question: why explicit request IDs still caused `aux_tap_contract` before the
real batch. Action: retrieved the compact terminal, observer diagnostic, and
raw request terminal once. `warmup = dict(bodies[0])` copied the admitted
`causal-offset-00` ID into a synthetic one-token request; the observer then
correctly treated it as the real arm. Patched only that line to remove `rid`
from warmup while retaining IDs on the 32 bound requests. Repair-4 was
hash-bound and consumed by the original PID/claim.

Evidence: new packet creation and manifest reconciliation are durable; all
earlier invalid raw roots remain on the warm bench. No training, holdout, or
endpoint action has started. Next: require nonzero mapped rows and a chunk
manifest before the single downstream consumer.

## 2026-07-26 — repair-5 source-bound forward-batch ownership

Question: identify a real request-to-tap ownership boundary before another
batch. Action: consumed the director disposition and inspected the pinned
image offline. The preserved SSE reports `id=causal-offset-00`; completion
conversion passes `request.rid` to `GenerateReqInput`; pinned
`ForwardBatch` construction sets `rids=[req.rid]`; and response metadata
returns that runtime RID. The hook had registered IDs only inside its
`is_extend()` path. Moved registration to the common logits boundary before
mode selection and bound the three runtime-source hashes plus amended hook in
`repair-5-source-evidence.json` and the hash-bound repair request.

Interpretation: repair-5 is a source-localized ownership repair, not a
heuristic batch. PID `2056931` consumed it and resumed the same capture path;
training, holdout, and endpoints remain closed until mapped rows and a chunk
manifest persist.

## 2026-07-26 — repair-6 server-only observer lifecycle

Question: why did the retained observer error report `aux_tap_contract` while
the same shared root held a zero-row pass terminal with no observer error?
Action: inspected the retained terminal, raw response identity, capture
command, and bootstrap once. The container exports the bootstrap through
`PYTHONPATH` for both `python3 -m sglang.launch_server` and the later
`docker exec` request runner. The unconditional bootstrap thus installed a
second zero-row atexit capture in the request-runner process, which can
overwrite the server terminal. Bound only a server-process predicate
(`launch_server` in `argv[0]`) in `capture_bootstrap/sitecustomize.py`, with
`repair-6-server-process-boundary-{evidence,patch}.json`, and submitted it to
the retained handshake.

Evidence: repair-6 is consumed by PID `2056931`; generation 7 binds packet
sha256 `7b3e2c580be7cb98093ed411ed2b31dd116fe0559646d71ff9b4d94950524568`
and bootstrap digest
`deb0b2a838c3710e1316b4797d07c6848224ce797053885d6aed7c1166adde55`.
The checkpoint manifest remains fully reused and verified. No valid capture,
training, holdout, endpoint pair, or causal-head scientific sample has been
recorded.

## 2026-07-26 — repair-7 generation-fresh terminal producer

Question: why did repair-6 still retrieve the terminal predating its own
`science_started` marker? Action: retrieved the compact terminal and server
logs once. `sitecustomize` runs before Python finalizes the `-m` target, so
the argv-gated bootstrap suppressed the server hook; the old terminal remained
visible. Restored unconditional bootstrap installation and changed the hook
so only an interpreter that crossed a real logits boundary writes a terminal.
This lets the server archive the old root while the no-forward request runner
cannot overwrite it. Repair-7 binds only these two mutable files and resumes
the capture stage from the same owner.

Evidence: repair-7 was consumed by PID `2056931`; generation 8 packet rebuild
is durable and the H200 capture container is live under the existing claim.
No current-generation manifest, training, holdout, endpoint pair, or
scientific sample has been recorded.

## 2026-07-26 — repair-8 runtime auxiliary-state binding

Question: why did the first generation-fresh capture still have no tap rows?
Action: retrieved the compact capture evidence and the pinned Gemma source
once. Generation 8 reached `science_started` and completed all 32 requests,
but its server observer recorded `aux_tap_contract`. The pinned
`Gemma4ForCausalLM.forward` supplies auxiliary states only when its runtime
capture flag is true; the initializer-only hook state had been superseded.
Bound the same flag and requested layers immediately before every model
forward, recorded the source path in
`repair-8-runtime-aux-forward-evidence.json`, and submitted repair-8.

Evidence: repair-8 is consumed by the unchanged PID and generation 9 packet
sha256 `16cc0ad7949cf2e2c2b9788ca4edc0a78d63bca1f9745a7e244f83bf9d15347c`
is durable. The completed 32-request observer-invalid root is preserved;
capture remains unmeasured and training, holdout, and endpoints remain closed.

## 2026-07-26 — repair-9 multimodal wrapper auxiliary binding

Question: why did the runtime-forward repair still leave auxiliary states
absent? Action: inspected the loaded-model type and the pinned deployed
wrapper once. The checkpoint loads `Gemma4ForConditionalGeneration`; its
`gemma4_mm.py` forward owns `capture_aux_hidden_states`, calls its
`Gemma4TextModel`, and alone decides whether to unpack auxiliary states before
logits. The causal-wrapper patch therefore did not reach this model. Bound the
same capture flag and layer list immediately before the actual multimodal
wrapper forward, recorded the source evidence, and submitted repair-9.

Evidence: repair-9 is consumed by PID `2056931`; generation 10 binds packet
sha256 `7db78ede26b07724b47fb123494cd4f8414cf2b9fdb602c27e7a82f92819dd51`.
Prior fresh raw roots remain observer-invalid and preserved; no valid capture,
training, holdout, endpoint pair, or scientific sample has been consumed.

## 2026-07-26 — repair-10 delegated text-model layer binding

Question: why did the actual multimodal wrapper repair still emit no
auxiliary states? Action: retrieved the generation-10 terminal and inspected
the pinned call path. `Gemma4ForConditionalGeneration.forward` delegates to
`general_mm_embed_routine(language_model=self.language_model)`, whose
`Gemma4TextModel.forward` alone makes the auxiliary tuple from
`layers_to_capture`. Bound the physical layer list immediately before that
text-model forward, alongside the already-bound multimodal flag, and submitted
repair-10 without changing the admitted workload or any downstream stage.

Evidence: repair-10 is consumed by PID `2056931`; generation 11 packet
sha256 `ef3eb629c380abbe9985fa1d490c45d401dd38b78d0e32e97bce39b87ae3231d`
is durable. Capture remains unmeasured; training, holdout, endpoint pairs, and
scientific samples remain unconsumed.

## 2026-07-26 — repair-11 generation-fresh capture root

Question: why did generation 11 fail before a current capture terminal or
manifest? Action: retrieved the repair diagnostic and exact runner boundary
once. The runner creates `requests` with `exist_ok=false`; a surviving request
directory caused a pre-request `FileExistsError`, while the local terminal was
older than the attempted launch. Bound only a root-lifecycle repair: the server
archives any nonempty prior capture root with a byte-hash manifest, and the
runner archives a surviving exclusive requests directory before creating it.

Evidence: repair-11 was consumed by the unchanged PID. Generation 12 packet
sha256 `db7f2263ba52d3729a4843dd359609754c581669ed00dec2eb27aeca2485ec77`
binds `capture_offset_taps.py` sha256
`362bd2ffcdbe04ba09b745a9faf71aa95943e96085dd6635e3b1601bb61a7603` and
`exact_runner.py` sha256
`03c1ab6085579e32f821fc1c3bbf6cc5e9788b4ee521b5522db7091483caf8e0`.
No capture rows, training, holdout, endpoint pair, or scientific sample has
been consumed. The next gate is a generation-current terminal plus nonzero
request-mapped chunks.

## 2026-07-26 — repair-12 concurrent capture-root archive

Question: why did the generation-fresh run still yield no capture terminal?
Action: retrieved the generation-12 container and current capture root once.
All 32 raw request responses and the runner terminal persisted, but the model
worker logged `RuntimeError:aux_tap_contract`. The same server bootstrap logged
a `FileNotFoundError` while a second SGLang Python process raced to rename the
shared capture root; that interpreter skipped the hook installation. Bound a
race-tolerant archive that selects only evidence-bearing roots, uses a unique
archive identity, and accepts a competing completed rename.

Evidence: repair-12 is consumed by the unchanged PID; generation 13 packet
sha256 `3020dbc4ff6c3a693fcb9b946c573983a8923504cb00083f197e6a2ba409e252`
binds `capture_offset_taps.py` sha256
`abaf6bb14cd6a8bfaca0f08ed2b3aa2dd7aad72188529d067ad88accaed7c373`.
The raw generation-12 request root is preserved under the remote archive.
Its observer failure is invalid and not a capture sample; training, holdout,
and endpoints remain unstarted.

## 2026-07-26 — repair-13 runtime auxiliary-path trace

Question: why did the race-free generation 13 still report
`aux_tap_contract`? Action: retrieved the compact current observer artifact,
raw-request archive, and container tail once. All 32 requests completed after
the race-tolerant archive repair, so the unresolved boundary is now the live
path between `Gemma4TextModel.forward`, the multimodal unwrap flag, and the
logits processor's auxiliary argument. Bound one compact trace per boundary;
it changes neither the model nor the workload.

Evidence: repair-13 is consumed by the unchanged PID; generation 14 packet
sha256 `6da435733e10106232c00833b8a29d7cdb4d240ec90bd7e41066f146238307aa`
binds `capture_offset_taps.py` sha256
`7531355ebed714be840daedad76e3551b1e0391c292d6cf2ad407f57ab722771`.
Generation 13's raw root is archived and observer-invalid, not a capture
sample. The next capture must retrieve its trace before any further repair;
training, holdout, and endpoints remain unstarted.

## 2026-07-26 — repair-14 terminal-layer capture index

Question: what did the generation-14 runtime trace prove? Action: retrieved
the compact text, multimodal, and logits traces before patching. All paths
agreed on active auxiliary capture but reported `[46,55,61]` and exactly two
states. The pinned `Gemma4TextModel` records the final layer only when its
identifier equals `num_hidden_layers` (60), making the generic `+1` transform
wrong solely for the terminal physical layer. Bound the corrected mapping
`[46,55,60]` and no workload change.

Evidence: repair-14 is consumed by the unchanged PID; generation 15 packet
sha256 `d1e5d9f8f7acd411e14c9c9f9eccc68bfaceda10960839def2332ae03f8a63fc`
binds `capture_offset_taps.py` sha256
`e990a8072cd68420216b275857b540b39988f12a9d6db8ce586eb56816b84c45`.
Generation 14's raw root is observer-invalid and preserved. Training,
holdout, endpoints, and scientific samples remain unconsumed pending a
current nonzero-row capture manifest.

## 2026-07-26 — repair-15 completed-capture terminal recovery

Question: did generation 15 complete a usable producer despite the generic
terminal retrieval failure? Action: retrieved its compact remote evidence once.
All 32 request terminals passed and 90 manifest-hashed tap chunks persisted
with 11,544 rows and ownership spanning request IDs 0–31; no observer error
persisted. The sole defect was omission of `CAPTURE_TERMINAL.json` on server
shutdown. Bound a recovery-only runner that rehashes every chunk, validates its
request-index/RID ownership, atomically writes the terminal, and returns before
any HTTP request; the bootstrap preserves this complete root rather than
archiving it.

Evidence: repair-15 request is durable at
`artifacts/h200-capture-train-20260726t2037z/.repair-handshakes/repair-15/REPAIR_REQUEST.json`,
with patch sha256 `c8f1c9f32ccc7387077dd772fd4c15c1d1ff08e8d51b5651e9c668fb32d012ba`.
The producer is consumed once; the owner must now retrieve the recovered
terminal and proceed directly to the unstarted training/holdout consumer.

## 2026-07-26 — repair-16 hash-verified training-input materialization

Question: why did the recovered capture not enter training? Action: retrieved
the consumer stderr, compact capture terminal, remote container state, and
artifact tree once. The recovered producer is valid (`90` chunks, `11,544`
rows, and `32` request mappings), while training failed before tap loading:
the packet contained the split manifest but not its two immutable JSONL files.
Materialized the project-local admitted bytes at the remote project artifact
root through size/hash reconciliation, then bound only the consumer fallback
and its hash checks.

Evidence: remote `TRAIN_INPUT_MANIFEST.json` records the sealed train and
holdout digests matching `IMMUTABLE_SPLIT.json`; repair-16 request binds only
`train_and_evaluate.py` with patch sha256
`6930f88bbbcaf5c06e2ebb01400a2ed3c59a13c6760f41e47f166858401e2d26`.
Capture is not replayed; the next owner generation may run only training and
the request-disjoint holdout.

## 2026-07-26 — repair-17 deterministic prefill-row collation

Question: why did the input-complete consumer still stop before optimization?
Action: retrieved the full consumer traceback and inspected the retained
chunk metadata once. Only offset zero had duplicates: `56` repeated prefill
logits rows across the `90` chunks. For each affected request, exactly one row
has the deterministic final-prompt token generated by the admitted workload;
all nonzero offsets are unique. Bound that discriminator and fail closed on an
ambiguous or nonzero duplicate.

Evidence: repair-17 binds only `train_and_evaluate.py` (patch sha256
`c149d7dd9b4c174596364236336adf7043ddef6b04338e8de581ee3e6f42993a`).
The capture and split artifacts remain consumed/preserved; the retry starts at
the unstarted training and disjoint holdout consumer.

## 2026-07-26 — repair-18 complete prefill-group selection

Question: why did deterministic prefill selection still fail? Action: grouped
the retained rows by request and target offset before selecting. The prior
pairwise implementation saw several nonmatching offset-zero rows before the
one prompt-tail row and rejected prematurely. The amended consumer accepts an
offset-zero group only when its complete group contains exactly one
hash-derived prompt-tail token; all other duplicate groups remain fail-closed.

Evidence: the actual patched `load_capture` executed on the retained remote
90-chunk producer and returned `11,488` unique keys without CUDA or any
training step (`repair-18-load-capture-check.json`, sha256
`a09df905e34d55dd307fa620dcccbc189f2ed85fcd2a6d8f2801754e91aeb40b`).
Repair-18 binds that checked consumer patch; capture remains consumed once.

## 2026-07-26 — repair-19 measured negative terminal adoption

Question: did generation 19 produce a scientific result or another consumer
defect? Action: retrieved the persisted holdout result and checkpoint hash
before considering any repair. The exact request-disjoint consumer completed:
the checkpoint hash matches and its mean accepted target tokens at depths
4/8/12/16 are all `1.001953125`, far below the required `16.054`. This is a
decision-bearing mechanism negative, not an opportunity to retrain.

Evidence: repair-19 binds only a terminal-adoption early exit after verifying
the existing split, cost model, result, and head checkpoint. Its real remote
entrypoint check exited zero without CUDA or training. Conservative provider
exposure through the fixed five-hour lifecycle is `$12.298611`, below the
`$14.00` authorization. Endpoints remain unrun and closed.

## 2026-07-26 — terminal measured negative

Question: did the admitted causal parallel-offset head meet the disjoint
holdout gate? Action: the retained owner adopted the persisted result under
repair-19, wrote its terminal, and released the H200. No capture, training,
holdout, or endpoint work was replayed.

Evidence: the 4,096-example training / 512-example request-disjoint holdout
has checkpoint sha256 `2945432594c77a248a6877eee83b23ececa95192718cf66cc6bf700b64938c34`
and holdout sha256 `c26e5f4e5b6b9b9280faf4b8796f6eacd6dde5ab9a0c7b3a50812b4b277f54a8`.
Depths 4, 8, 12, and 16 each measured 1.001953125 accepted target tokens,
below the 16.054 acceptance gate. This closes the mechanism as a measured
negative; full lifecycle conservative provider exposure is `$12.298611`.
