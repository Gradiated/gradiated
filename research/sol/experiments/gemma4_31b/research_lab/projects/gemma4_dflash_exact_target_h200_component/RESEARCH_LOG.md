# Research log

## 2026-07-29T22:44:39.438840Z — exact H200 component packet ready

Question: can exact DFlash beat matched AR and NGRAM controls while preserving greedy target and KV semantics?

Action: materialized the exact f63458b5 source archive and immutable runner, adopted the fixture-validated RID/physical-slot mapping, and built a durable owner/worker packet with single-consumption markers, same-claim repair, zero/partial/full next-round audits, and CUDA interval-union accounting.

Evidence: offline validation passed; no GPU/provider/endpoint action occurred. The historical request-25 sample remains consumed, uninterpretable, excluded, and unreplayed.

Artifact: DFLASH_H200_COMPONENT_READY.json SHA-256 `ca18a8ecc1949fa2cc751a992d9c8af5adfc04e66b886e25e51fb45d8b639bc7`; packet archive SHA-256 `bcccec58b0f5ced606f8c7e3584f8500fa99546a97db2af67afbad4347451c04`.

Next: a later director may bind a compatible current bench and atomically claim only after rechecking the exact $6 reservation and lifecycle runway.

## 2026-07-29T23:01:12Z — retrieval-only replacement owner ready

`retrieval-0.json` proves an integration-only retrieval failure: the predecessor
created its compact archive inside the tree being archived. Worker return code
75 leaves science consumption unknown and does not authorize replay. PID
`362641` / start ticks `148132006` and claim generation
`2026-07-29T22:47:36.830795Z` remain live and untouched.

The first offline replacement attempt changed heartbeat control. It was
preserved as `DFLASH_H200_OWNER_REPLACEMENT_READY_ATTEMPT0_INVALID.json` after
the newer R2 binding proved the shared heartbeat repair was already adopted and
forbade that change. The amended replacement reuses the existing owner
heartbeat unchanged and changes only retrieval/adoption.

A real shell packaging fixture over a complete retained tree passed: the source
tree's size-and-hash manifest was unchanged, temporary and final archives were
outside the source tree, retrieved bytes matched their digest, and persisted
state was classified before any possible continuation. No scientific worker,
SSH, endpoint, Docker, claim, release, or provider action ran.

Artifact: `DFLASH_H200_OWNER_REPLACEMENT_READY.json` SHA-256
`bcead7c00f27636cafa3c95f351ba2e14763876bbf14246e2aa2c2bca4d54236`;
replacement source SHA-256
`6a1ce229214431d242f6fffa9e4ab8473452431f7ee6ff42561b1044eb959a35`.
The artifact is launch-inert; a later director owns the exact-PID handoff.

## 2026-07-29T23:11:46Z — marker-proven unconsumed retrieval adoption repair ready

Question: can the retrieved `server_startup_defect` be classified without
guessing from its absent `science_consumed` object?

Action: read only the handoff, retrieved adoption, the exclusive marker writer,
and the replacement classifier. The marker writer records its exclusive
`SCIENCE_STARTED` file immediately before `exec` of the immutable request
runner. The complete retrieved snapshot manifest contains none of those three
marker files, while its `REMOTE_ATTEMPT` reports all three false.

Evidence: the source-hash-pinned patch dynamically classifies that exact
snapshot as `classified_persisted_attempt`, with all arms unconsumed and retry
scope `all`; it does not use absence of `science_consumed` by itself. Artifact:
`DFLASH_H200_ADOPTION_CLASSIFICATION_REPAIR_READY.json` SHA-256
`30b3276607ae9d7e998952947a77d92bc99878a76f0b882e81753d8798ac1b42`.

Next: a later director may verify the artifact and bind the exact-PID repair.
The repair is retrieval-adoption classification only before any worker, CUDA,
model load, or arm; this turn sent no request and performed no remote action.

## 2026-07-29T23:29:00Z — direct fresh-claim continuation owner ready

Question: how can a future fresh claim resume the classified unconsumed run
without repeating the r3 `repair_wait` race?

Action: implemented a direct-continuation owner. It retrieves outside the
remote run tree, persists the fresh adoption, requires the exact snapshot
manifest and exclusive pre-request marker predicate, then consumes a future
hash-bound direct authority before staging the unchanged packet.

Evidence: the actual corrected snapshot passed the owner gate. Mutating either
its manifest binding or its fresh classification produced a typed
`direct_authority_boundary`; no remote or scientific action was invoked.
Artifact: `DFLASH_H200_DIRECT_CONTINUATION_OWNER_READY.json` SHA-256
`5ab9e0788e50d59802888f6e8c3b8b2d6d9039bc210b5531d751bb13f53bf2eb`.

Next: director-only fresh claim and authority binding after cost, identity, and
watchdog-runway checks. The owner does not use `repair_wait` for its initial
direct-continuation transition.

## 2026-07-29T23:38:00Z — direct owner terminal/release lifecycle ready

The newest binding found that the direct owner stopped after its worker, so it
could lose claim ownership without terminal retrieval. The repaired owner now
retrieves after each worker return, validates a scientific terminal before
ready release, otherwise distinguishes a recoverable request from a typed
repair terminal, and releases maintenance only with a typed incomplete
handoff at the deadline. The shared fixture proved request consumption is one
atomic rename and that `repair_terminal` remains distinct. Artifact:
`DFLASH_H200_DIRECT_OWNER_TERMINAL_RELEASE_READY.json` SHA-256
`5141545d8ca22394eaf0b3ef68313e590b7fc89920d27b691480fe82cf4f6601`.

## 2026-07-29T23:43Z — pre-science immutable-owner boundary

The bound H200 was claimed at `2026-07-29T23:41:24.589244Z`; the exact
detached direct owner started as PID `393511` / start ticks `148452233`.
It exited before heartbeat, SSH, container, CUDA, or worker execution because
the READY manifest requires `dflash_component_owner.py` at 31,565 bytes and
`eaec2de1…`, while the current project-local file is 33,082 bytes and
`2acf8f2d…`. No arm was submitted or consumed.

`PRE_SCIENCE_OWNER_BOUNDARY.json` and the owner-log digest preserve the
diagnostic. The fresh authority forbids a second owner, and restoring the
concurrent local bytes would require new authority, so the claim was released
to maintenance for director rebind rather than replaying or guessing. The
conservative reservation exposure is recorded as `$5.581925`, below `$6`.

## 2026-07-29T23:57Z — direct-owner repair binding conflict

Action: inspected the durable `direct-2` server-startup repair boundary. It retained the same claim and proved AR, DFlash, and NGRAM unstarted. The root cause remains pinned-image `sglang-kernel 0.4.3` below the pinned source minimum 0.4.4. A narrow packet was prepared to archive the zero-request AR root and install exactly `sglang-kernel==0.4.4 --no-deps` before the unchanged server entrypoint.

Evidence: the owner consumed `direct-2` request then exited at `continuation_authority_boundary:adoption_sha256_mismatch`; no new server, CUDA request, or scientific arm result was persisted. The active binding forbids replacement ownership.

Next: director rebind required for the ownerless retained claim; preserve remote checkpoint, draft, source, cached image, and all compact snapshots.

## 2026-07-30T00:09Z — r2 lost-owner recovery source ready

Action: published a hash-bound recovery owner for a later director-only same-claim launch. It validates the exact claim, adoption `1f1a226c…`, consumed direct-2 request, corrected patch `f893a8f3…`, and packet `3e59bcdd…`; it retrieves before and after only worker generation 2.

Evidence: offline compile and contract check passed; no GPU-pool, SSH, Docker, CUDA, provider, repair-request, or scientific action occurred.

Next: director may bind and launch exactly one recovery owner before the r6 release fence.

## 2026-07-30T00:13Z — recovery retry-entrypoint owner loss

Action: preserved both zero-request AR archives and prepared packet `e3f0bd4f…`, which archives the current AR partial under its exact generation before creating a fresh root.

Evidence: worker 2 stopped before server health or science at `repair_output_boundary:partial_archive_exists`; all three arms remain unstarted/unconsumed. The recovery-3 request was valid and submitted, but the live recovery owner has no post-`repair_wait` dispatch branch and exited.

Next: director recovery binding must supply an owner with executable request-consumption dispatch; do not replay workers 0/1 or release the retained claim.

## 2026-07-30T00:19Z — consumed repair-3 dispatcher recovery ready

Action: published `dflash_component_direct_recovery_owner_r2.py` and the
hash-complete `DFLASH_H200_R2_CONSUMED_REPAIR3_RECOVERY_READY.json`. The owner
validates the exact ownerless claim, adoption `10335540…`, consumed request
`12f45574…`, patch `03aa2b4d…`, and repaired packet `e3f0bd4f…`; it adopts
that consumed repair exactly once and enters only worker generation 3.

Evidence: offline compilation and local contract/hash verification passed.
The post-worker path retrieves and classifies before terminal handling; a
recoverable result enters a real `repair_wait` dispatch loop, atomically
consumes a new request, validates it against the current adoption, and resumes
only the authorized next scope. Request rejection emits a fresh diagnostic
while heartbeat ownership remains live. No GPU pool, SSH, container, CUDA,
provider, request, or scientific operation occurred in this turn.

Next: a later director may verify the readiness digest and launch the single
same-claim recovery owner. Workers 0–2 remain prohibited from replay.

## 2026-07-30T00:25Z — dispatcher fallthrough repaired

Action: superseded the rejected readiness with
`DFLASH_H200_R2_DISPATCHER_CONTROL_FLOW_READY.json`. The owner now places
repair waiting inside an inner dispatcher after a recoverable worker result.

Evidence: offline branch exercise covered valid request, rejected-then-valid
request, repair terminal, and deadline. A rejected request writes a fresh
diagnostic and remains waiting with the same worker generation; a repair
terminal takes typed maintenance without another worker; only a newly validated
consumed request advances. No external action or science occurred.

Next: later director-only verification and launch, beginning at worker 3.

## 2026-07-30T01:04Z — r3 retained downloader owner launched

Question: can the exact retained claim recover the missing guest downloader
without changing the scientific packet or releasing the warm H200?

Action: bound repair director `618d8056…` and repaired owner
`df32e138…` into `artifacts/dflash-h200-r3-cold-worker3/EXECUTION_BINDING.json`
(`eccda1be…`). The owner uses the pinned SGLang image for authenticated
`huggingface_hub` downloads, falling back only to a claim-local venv, and
sends a cold-stage error to the retained dispatcher. It launched once as
PID `441959` / start ticks `148936887`.

Evidence: grouped snapshot matched claim `2026-07-30T00:49:46.346350Z`, H200
UUID and SSH fingerprint, with a fresh successful heartbeat at `01:03:31Z`.
The owner had completed cold reconcile/check and its live remote child was
`sudo -n docker pull` of the exact pinned image. No worker, CUDA invocation,
or scientific arm has started or been consumed.

Next: let the durable controller finish cold staging or retain the claim for
its hash-bound repair handshake; do not launch another owner.

## 2026-07-30T01:13Z — same-claim downloader timeout repair

Action: reconciled terminal owner `441959`: its pinned-image module probe
timed out at 120 seconds before any CUDA work, worker, or request. The remote
census showed no surviving container or downloader. Patched timeout handling
into the retained cold-stage dispatcher, increased the probe bound to 600
seconds, rebound the owner as `02cc9403…`, and launched exactly one
same-claim replacement owner `446635` / `148998370`.

Evidence: the replacement is live on the unchanged claim and has crossed the
amended path: `config.json` verified, then its active SSH child invoked the
pinned-image `huggingface_hub` download for
`model-00001-of-00002.safetensors`. This remains pre-science; AR, DFlash,
NGRAM, workers 0–2, and request 25 are untouched.

Next: preserve this owner and allow resumable staging to continue or enter
its retained repair dispatcher on a typed cold-stage defect.

## 2026-07-30T01:30Z — retained cold-stage capacity boundary

Action: inspected the sole repair-ready diagnostic and the owner retry path.
It would correctly resume only `cold_stage`, retaining verified rows, but no
code or request patch can make the admitted target fit on the current boot
disk.

Evidence: shard 1 is verified at 49,784,788,364 bytes. The pinned image uses
28.11GB; `/` is 96GB with 5.9GB available. The exact second shard needs
12,761.55MB and its captured downloader diagnostic reports insufficient disk
space. No container remains, and no worker, CUDA operation, or science arm
started or was consumed.

Interpretation: an unchanged hash-bound `cold_stage` request would replay the
same pre-science disk failure. A larger director-managed staging location or
capacity change is required; both are outside researcher/provider authority.
The owner and claim remain live in their documented repair wait and are not
released.

## 2026-07-30T01:48Z — storage-migration device mapping boundary

Action: consumed the bound storage-migration prerequisite through strict SSH;
the narrow controller was stopped before formatting, mounting, copying, or
request publication.

Evidence: the exact stable path `/dev/disk/by-id/virtio-dflash-stage` is absent
on the reachable guest, despite the director binding to managed disk
`computedisk-e00rwewnz08e4fgt41`. The retained owner `446635/148998370` and
claim heartbeat remain live. `REMOTE_DEVICE_ABSENCE.json` records this typed
external attachment-mapping blocker; no repair request exists and all science
remains unstarted/unconsumed.

Next: director must reconcile only the managed disk's guest device mapping;
retain the existing owner and claim, then rebind the storage action if needed.
## 2026-07-30T02:03Z — post-restart hardware rebind (execution)

Question: can the retained, unconsumed worker-3 cold stage continue after the
post-restart H200 UUID change without changing science or the continuous claim?

Action: verified director binding `72f7b677...`, repair-ready `b11608d3...`,
the unchanged claim, H200 identity/fingerprint/storage/watchdog, and the exact
live predecessor `446635/148998370`. Hash-bound R4 owner
`b5ea59ff...` and execution binding `bf99c294...` (only director, owner, and
GPU-UUID fields differ from R3), generation-fenced only that predecessor, and
launched the named detached R4 owner exactly once.

Evidence: R4 is live as `469053/149297134`, emitted a fresh claim heartbeat at
`2026-07-30T02:03:34.131224Z`, and persisted
`cold_stage_resumed_expanded_root` with `config.json` verified. No science or
worker execution was entered.

Next: the durable owner reconciles the retained partial and downloads only
missing/invalid rows before worker 3; it owns the same claim through its
absolute deadline.

## 2026-07-30T02:15Z — retained cold-stage checksum repair resumed

Question: can R4 resume only cold staging after its 300-second remote checksum
observer timed out, without changing the target, claim, worker generation, or
science contract?

Action: exercised the exact bound shard-1 path in the retained guest and
persisted `COLD_STAGE_REPAIR_DYNAMIC_CHECK.stdout` (SHA-256
`8d352b4b…`), which proves 49,784,788,364 bytes and SHA-256 `eeef8791…`.
The first repair request was consumed then correctly rejected at the packet
digest boundary (`RECOVERY_R2_REQUEST_REJECTION_3_0.json`); it started no
worker or science. Submitted a fresh `classify` repair request using the
bound immutable `e3f0bd4f…` packet. R4 consumed it and crossed back into its
actual `cold_stage` entrypoint (fresh reconcile and per-file check artifacts
at 02:15:07Z).

Interpretation: this is a recoverable observer/request-binding defect, not a
checkpoint or model incompatibility. The owner, PID `469053` / start ticks
`149297134`, and claim remain live; shard 1 is retained, shard 2 remains the
only missing model row, and workers 0–2/request 25 remain unreplayed.

Next: let the durable R4 owner continue the resumed cold stage and enter
worker 3 only after atomic checkpoint finalization or emit its next typed
repair/terminal boundary.

## 2026-07-30T02:25Z — r5 immutable-packet worker-3 repair boundary

Question: can the complete retained target enter worker 3 with the immutable
repair3 packet under the single r5 rebind authority?

Action: verified binding `f8ea81aa…`, claim generation, complete target
manifest `6202e8f8…`, immutable packet `e3f0bd4f…`, H200 UUID, strict SSH
host key, watchdog `427838`, and absence of R4. Bound R5 owner
`843aef62…` and execution binding `2525fb05…`, then launched the named
detached owner once as `479602/149434293`. It reused the complete target and
crossed `worker_3_packet_verified_dispatching`.

Evidence: worker 3 returned 1 before model, server, CUDA, or request entry:
the immutable packet's `hardlink_target_view` received `EPERM` linking
`chat_template.jinja` into its run-local target view. `RECOVERY_R2_ADOPTION_3.json`
and `RETRIEVAL_RECEIPT_103.json` record an empty remote snapshot; the remote
census found no worker, container, or GPU compute process. The R5 owner then
exited when it attempted to publish into an inherited completed repair
generation. `R5_RETAINED_REPAIR_BOUNDARY.json` (`25a6c67b…`) preserves the
typed, pre-science boundary.

Interpretation: no scientific sample was consumed. The complete target and
unchanged claim remain reusable, but the single R5 authority is exhausted;
a director-bound fresh repair owner must patch only the read-only target-view
fallback (reflink or verified temporary copy) and use a fresh repair ID.

## 2026-07-30T02:37Z — r6 target-view repair launched

Action: verified director binding `36b6fae1…`, the unchanged claim and H200
identity, strict SSH host key, watchdog `427838`, complete target
`6202e8f8…`, base packet `e3f0bd4f…`, and absence of R5. Derived packet
`052d2ce0…` changes only `hardlink_target_view`: it retains hard links when
possible and otherwise uses a read-only reflink or verified temporary-copy
fallback, recording each materialization mode. Its fresh repair namespace is
`…-r6-target-view`.

Evidence: packet validation passed locally. The named R6 detached controller
is live as `485251/149505876`; execution binding `2282b93e…` is hash-bound.
Its fresh claim heartbeat was persisted at `02:37:51.502769Z`, and
`PHASE.json` records `worker_3_packet_verified_dispatching` with the repaired
packet digest. It is the sole owner and now owns terminal retrieval or its
fresh retained-repair path.

## 2026-07-30T02:39Z — inherited repair-ready not signaled

Evidence: the supplied `REPAIR_READY.json` belongs to completed inherited
generation `…recovery-r2-3-dispatch-0`; its diagnostic is the superseded
cold-stage checksum timeout. R6 is live and its documented dispatcher accepts
only fresh IDs under `…-r6-target-view`; no fresh R6 repair-ready exists while
worker 3 is active.

Disposition: did not submit a request into the stale namespace or replay any
stage. The durable R6 owner retains the claim and current worker path.

## 2026-07-30T02:59Z — r6 classify-to-NGRAM in-place repair requested

Question: can the live R6 owner resume only its invalid consumer boundary
without replaying the retrieved AR or DFlash arms?

Action: inspected the fresh R6 repair-ready and its actual retry entrypoint.
`RECOVERY_R2_ADOPTION_3.json` binds the failure to the owner-generated
`classify` scope, while the packet accepted only arm scopes. Its retrieved
snapshot shows complete 32-row AR and DFlash terminals, but NGRAM contains
only `SERVER_SUBMITTED.json` and `server.log` (no science marker, requests,
responses, or terminal). Derived and manifest-validated packet
`e3d8527f…` adds only this scope mapping: archive that zero-request NGRAM
root atomically and run a fresh NGRAM root. The continuation patch passed the
owner's exact validator, then `repair-handshake request` wrote the bound R6
request at `02:59:30Z`.

Evidence: [R6 check](artifacts/dflash-h200-r3-cold-worker3/run/R6_CLASSIFY_NGRAM_REPAIR_CHECK.json)
and [request patch](artifacts/dflash-h200-r3-cold-worker3/run/R6_CLASSIFY_NGRAM_REPAIR_PATCH.json).
The request state is `requested`; owner `485251/149505876` retains the claim.

Next: do not poll or replace the owner. It must consume the request, retain
AR/DFlash, archive only the zero-request NGRAM partial root, then retrieve a
scientific terminal or publish the next typed repair boundary.

## 2026-07-30T03:08Z — r6 existing target-view reentry request accepted

Question: can the live R6 dispatcher resume its bound `classify` consumer
without replaying the 32 completed AR or 32 completed DFlash rows?

Action: verified binding `2c04ab76…`, owner `485251/149505876`, claim
`2026-07-30T00:49:46.346350Z`, repair-ready `60dd9aec…`, diagnostic
`ba6e2df7…`, H200 UUID, strict SSH identity, and watchdog `427838`. Derived
the packet `d4d558e0…` from the admitted `e3d8527f…` base, changing only
existing target-view fallback classification: exact size/hash plus read-only
verification now permits a retained reflink/copy row, while inode equality is
still required for a hard link. The archived zero-request NGRAM partial and
all frozen arm outputs were untouched. The exact repair-handshake request was
accepted at the worker-4 namespace with retry scope `classify`.

Evidence: [packet validation](artifacts/dflash-h200-r6-existing-view-reentry-repair/R6_EXISTING_VIEW_REENTRY_PACKET_VALIDATION.json) and the durable request at
`artifacts/dflash-h200-r3-cold-worker3/run/.repair-handshakes/dflash-h200-r3-cold-worker3-20260730t0045z-r6-target-view-worker-4-repair-0/REPAIR_REQUEST.json`.

Next: return without polling. The sole live owner may enter only the fresh,
previously unconsumed NGRAM arm or publish a new typed boundary.

## 2026-07-30T03:32Z — R7 NGRAM-only retained repair

- Action: claimed the bound warm H200 at 03:29:46Z and launched durable R7 owner PID 508978.
- Evidence: worker 7 used `classify` only; returned `server_startup_defect`, with NGRAM science marker false and archived snapshot `f7779a...`.
- Interpretation: no NGRAM scientific sample was consumed; AR/DFlash remain frozen. Owner heartbeat and repair handshake remain live.

## 2026-07-30T03:32Z — R7 NGRAM-only retained repair

- Action: claimed the bound warm H200 at 03:29:46Z and launched durable R7 owner PID 508978.
- Evidence: worker 7 used `classify` only; returned `server_startup_defect`, with NGRAM science marker false and archived snapshot `f7779a...`.
- Interpretation: no NGRAM scientific sample was consumed; AR/DFlash remain frozen. Owner heartbeat and repair handshake remain live.

## 2026-07-30T03:34Z — R7 FlashInfer incompatibility retained

- Evidence: retrieved worker-7 terminal (`rc=75`) rejects `prefill=triton, decode=flashinfer` for Gemma4 before NGRAM science.
- Interpretation: switching to a listed compatible backend changes the director-bound FlashInfer arm; do not replay or signal an incompatible repair.
- Owner boundary: R7 validates a repair request then returns without worker-7 re-entry, so a request would strand the sole live claim. Rebind required.

## 2026-07-30T03:45Z — exact backend intersection no-go and release

Question: does pinned SGLang expose any H200 backend that jointly supports
Gemma4 hybrid attention, FP8 KV, page size 16, and NGRAM top-k 10?

Action: audited the exact `f63458b5` source, then used the bound repair
generation only to fence R7 into terminal return. R8 and its packet were not
created. After R7 exited, strict SSH found zero containers and zero GPU
compute processes; the exact claim was released `available` at 03:44:44Z.

Evidence: [compatibility no-go](artifacts/dflash-h200-r8-ngram-backend-compat/R8_BACKEND_COMPATIBILITY_NO_GO.json)
(`f4fbd5b7…`) and [release evidence](artifacts/dflash-h200-r8-ngram-backend-compat/RELEASE_EVIDENCE.json).
Gemma4 accepts `trtllm_mha`, `triton`, `ascend`, or `intel_xpu`, while the
NGRAM hook requires `flashinfer` for top-k > 1 with page size > 1. TRT-LLM
MHA separately limits speculative target verification to top-k 1.

Interpretation: the supported intersection is empty under frozen geometry.
This is a source-backed pre-science compatibility no-go, not a scientific
performance result. AR and DFlash remain frozen at 32 requests each; NGRAM
remains unconsumed at zero requests. Conservative cumulative spend is
$13.351876692777779 against the $18 ceiling.
