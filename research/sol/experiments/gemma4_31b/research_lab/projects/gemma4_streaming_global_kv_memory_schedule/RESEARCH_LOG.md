# Research log

## 2026-07-29T15:43Z — V12 endpoint result is consumed; repair retry is unsafe

- Question: did `endpoint_failed` leave an unconsumed consumer defect that can safely use the requested `endpoint_only` repair?
- Action: retrieved and hash-bound the compact terminal, workload, activation capture, telemetry, and owner stdout/stderr before considering a repair request.
- Evidence: `retrieved_endpoint_0/TERMINAL.json` is SHA-256 `5a7bee8c…` and records 32 complete requests, `pass: true`, batch time 22.4558 s, and complete-request throughput 1.4250/s. The guest retains all 32 response captures, the activation capture, and a live 122,932-MiB container. The owner’s fixed retry path returns from any repair wait and increments `attempt`, so it would submit `endpoint-1` after the already-consumed endpoint.
- Interpretation: the nonzero wrapper exit is a retrieval/control-flow defect, not an unconsumed candidate. Writing the named retry request would violate the binding's one-submission limit. `V12_ENDPOINT_CONSUMED_REPAIR_CONTROL_FLOW_CONFLICT.json` (SHA-256 `ab3dd111…`) preserves the complete evidence and exact adoption conflict.
- Next: preserve the owner, loaded server, claim, watchdog, and candidate output; require a terminal-adoption/generation-fenced release path that never invokes `run_endpoint` again.

## 2026-07-29T15:30Z — V12 duplicate-destination staging repair dispatched

- Question: can the live owner resume the same retained-prefix transfer after its second `append_failed` without a source reload or scientific replay?
- Action: isolated the source-parsed defect: the append pipeline passes the SSH destination twice, which turns the second destination into a guest command. Installed a compatibility adapter only for that exact guest command and exercised the identical zero-byte append pipeline.
- Evidence: the adapter is SHA-256 `d16ce436…`; the smoke is `V12_DUPLICATE_SSH_DESTINATION_REPAIR_SMOKE.json` SHA-256 `5ebf7d07…` and preserved the 34,307,773,440-byte partial SHA-256 `5c9d7530…`. Repair generation `streaming-global-kv-v11-staging_failure-1` is requested; V12 remains live and heartbeating at 15:30:07Z, after re-entering the staged target path. GPU remains unused and no container or endpoint exists.
- Interpretation: this is an environment-level compatibility repair for already-parsed owner bytes, allowing the existing staging loop to continue without source edits, replacement, or upstream replay.
- Next: retain this owner while it transfers the unmatched suffix, verifies the manifest, and proceeds into the single bound server/endpoint path.

## 2026-07-29T15:25Z — V12 retained-prefix append repair dispatched

- Question: can the live V12 owner resume its unconsumed checkpoint staging after `append_failed` without replaying a producer or endpoint?
- Action: inspected its waiting repair record and retry path. The retained `model-00001-of-00002.safetensors.part` was exactly 34,307,773,440 bytes but mode `0444`; restored owner-write permission and exercised the exact SSH append boundary with a zero-byte payload.
- Evidence: the smoke preserved both byte count and SHA-256 `5c9d7530…`; `V12_APPEND_PERMISSION_REPAIR_SMOKE.json` is SHA-256 `40fe1832…`. The hash-bound request targets only `staging_failure`; V12 PID 102131 remains live, the claim heartbeat reached 15:25:37Z, and `RESUMED_OFFSETS.json` binds the same verified prefix. No server, CUDA replay, or endpoint request occurred.
- Interpretation: read-only partial mode was a recoverable integration fault. The existing owner’s repair wait returns to the staging loop, so the request does not reload the model or replay scientific work.
- Next: let the single durable owner finish suffix transfer and integrity, then launch the bound server and submit the one U=8 endpoint only if its gates pass.

## 2026-07-29T14:49Z — v11 prefix inspector cannot consume a source repair

- Question: can the live v11 owner repair the first resumable-staging fault in place?
- Action: inspected the one repair-ready diagnostic and the parsed retry entrypoint.
- Evidence: `part_state()` fails before prefix inspection because its nested remote Python heredoc quote-strips `print("0 absent")` into invalid Python. The owner remains live and heartbeating under the retained generation, with no server, request, endpoint output, or CUDA replay. Its repair waiter resumes the staging loop but does not consume request patch bytes; source edits cannot alter its already-parsed function body.
- Interpretation: this is a recoverable pre-science controller defect, but the current owner is not executable-repair-capable for it. A request would merely replay the identical SyntaxError.
- Next: preserve claim and inputs for a director-authorized same-claim replacement; do not signal a no-op repair, reload a server, or submit the candidate.

## 2026-07-29T14:38Z — v11 resumable owner is prepared but its launch fence expired

- Question: can the retained 34,307,773,440-byte first-shard prefix make the remaining c32 endpoint path fit?
- Action: derived v11 from v10, fixed ordered `retain()` locals, and implemented hash-checked prefix reuse with suffix-only SSH streaming, full-file verification, and atomic finalization.
- Evidence: shell syntax and the lifecycle-pure resumability fixture passed. The binding's first-shard prefix is unchanged. At the mandatory launch check, current UTC was 14:38:39Z while v11's binding fence was 14:38:00Z; no v11 owner or claim mutation occurred.
- Interpretation: the implementation is ready, but launching the stale command would violate the binding's lifecycle fence. No science, CUDA replay, or endpoint submission occurred.
- Next: director must issue a revised launch fence within the unchanged watchdog/release envelope before any v11 owner may start.

## 2026-07-29T14:27Z — v10 owner loss exposes an infeasible remaining staging window

- Question: did v10 progress through the repaired same-claim staging boundary?
- Action: took the first required grouped owner, claim, artifact, and log snapshot.
- Evidence: detached-owner reports v10 PID `52969`/ticks `145055323` dead while the original claim remains heartbeating. Its local log reaches missing remote checkpoint hash probes, then exits at `retain()` with `scope: unbound variable`. `TERMINAL.json` is absent. No server, request marker, endpoint root, candidate result, or CUDA replay exists. At 14:27Z only 53 minutes remained to the 15:20Z integrity fence, below the binding's 67.4-minute full-checkpoint-transfer bound.
- Interpretation: this is a localized pre-science controller defect, but an immediate full staging retry is no longer feasible inside the admitted absolute schedule. It is not endpoint evidence or a scientific negative.
- Next: preserve the claim/watchdog record for director reconciliation; do not launch another owner or submit the endpoint without a new lifecycle envelope.

## 2026-07-29T14:15Z — v10 same-claim staging replacement launched

- Question: can the zero-request v9 staging failure be repaired without losing the retained H200 claim or replaying the settled CUDA producer?
- Action: derived v10 only from v9, isolated SSH stdin from the manifest loop, made the owner adopt the exact existing claim rather than call `gpu_pool claim`, and bound direct hash-reconciled staging before integrity. The lifecycle-pure fixture passed. After commit-time validation, stopped only v9 PID `43683` at ticks `144967588`, verified it absent, and launched v10 PID `52969` under the same generation.
- Evidence: claim generation remains `2026-07-29T14:02:13.215196Z`; v9 repair generation `streaming-global-kv-v9-staging_failure-1` was waiting with no terminal, science marker, or endpoint output. V10 patch SHA-256 is `fa4615e8…`; owner SHA-256 is `833c92c7…`; its same-claim, execution-binding, and claim-generation artifacts are durable.
- Interpretation: this is one localized pre-science owner replacement, not a new claim or a sample. The CUDA producer `0f7c32bb…` and single candidate endpoint contract remain unchanged.
- Next: let v10 complete hash-reconciled integrity, candidate server activation, the one U=8 endpoint, and generation-fenced release; retain any further repair under this owner only if it fits the remaining absolute fence.

## 2026-07-28T14:55Z — streamed memory discriminator

- Question: can the activated compact global-KV mechanism cross the measured c32 layer-35 OOM without changing its attention information path?
- Action: traced only the bound terminal and activated source, built a complete intervention lifetime model, then implemented an eight-entry, one-query-row, one-request-at-a-time online-softmax consumer.
- Evidence: the terminal binds the OOM to a 2 MiB allocation with 2.31 MiB nominal free; the source-capped BF16 single-call transient falls from 1,852,480 to 213,312 bytes and the largest candidate allocation is 65,536 bytes. Three CPU Torch comparisons passed, including c32 scheduling and the measured 26-entry geometry, within one BF16 quantum.
- Interpretation: memory feasibility is analytically credible and no longer depends on an inferred eager c32 lifetime. CUDA compilation, runtime aliasing, graph behavior, component timing, and the endpoint remain unmeasured.
- Next: after the director authorizes a compatible H200 and spend, run the bounded correctness/memory/component discriminator and only then one new streamed c32 endpoint sample. Do not replay the consumed materializing arm.

Artifact: `MEMORY_SCHEDULE_DISCRIMINATOR.json`.

## 2026-07-29T13:39Z — v8 owner lost before candidate submission

- Question: did the retained v8 controller continue safely after the first candidate-server health miss?
- Action: took the required grouped detached-owner, claim, artifact, and bounded-log snapshot.
- Evidence: PID 26048/start ticks 144794786 is dead while the original claim generation `2026-07-29T13:33:24.414360Z` remains live. The exact image pull completed, then the server had no listener and `retain()` failed at owner line 82 with `scope: unbound variable`. No server-ready marker, candidate request, terminal, or candidate sample exists; the CUDA producer `0f7c32bb...` was not replayed. Diagnostic: `artifacts/streaming-global-kv-fresh-h200-20260729t1324z/OWNER_V8_PRE_SCIENCE_FAILURE.json`.
- Interpretation: this is a localized pre-science owner-controller defect, not endpoint evidence. The stale preserve-owner binding forbids a replacement launch, so the claim and resident artifacts remain untouched pending a same-claim director repair binding.

## 2026-07-29T10:25Z — zero-GPU packet identity repair

- Question: is the published `memory_schedule_model.py` mismatch stale binding metadata or a change that invalidates the U=8 memory accounting?
- Action: compared the bound model output against every published c1/c32 BF16 peak, found a doubled FP32 partial-state term in the current model, restored the single K/V-pair accounting, and reran the three existing CPU Torch discriminators.
- Evidence: the repaired model emits the packet's `721308`, `213312`, `1344204`, `18628812`, `1852480`, and `50627136` byte values; c32 layer-local, 512-token boundary, and measured 26-entry geometry all passed at the existing BF16 tolerance. Candidate and test bytes are unchanged; CUDA was not invoked.
- Interpretation: this was a post-publication code change, not stale metadata. The model is now content-bound as `df81c3b9...`; the U=8 schedule and the consumed materializing c32 arm remain unchanged.
- Next: only a director-authorized, 45-minute H200 discriminator may claim a compatible bench and run the new streamed candidate; do not replay the materializing c32 arm.

## 2026-07-29T10:45Z — H200 owner preparation

- Question: can one retained controller safely take a future registered H200 from cold staging through the U=8 CUDA discriminator and a conditional new c32 candidate endpoint?
- Action: hard-linked the hash-bound activated source under this project, added a CUDA runner for C=26 correctness, C=64 Q=1/Q=32 memory, and profiler-off component comparisons, and added a PID-controller-host owner using shared pool, repair, snapshot, and detached-owner contracts.
- Evidence: shell syntax and Python compilation pass; all frozen identities remain unchanged. The owner is deliberately unlaunched: this preparation performed no pool, SSH, provider, CUDA, or spend action.
- Interpretation: the owner retains the claim on a recoverable CUDA, endpoint, or retrieval defect, hashes compact retrieval before release, and calls the c32 endpoint only after the component gates pass. The later launch binding must supply the immutable exact-runtime image and endpoint command.
- Next: director may create/register the single H200 only after consuming the ready terminal and confirming the durable $4 reservation.

## 2026-07-29T11:46Z — same-claim R2 fixture repair launched

- Question: can the unconsumed CUDA discriminator resume under the original H200 claim after correcting only its compact-target fixture geometry?
- Action: derived each fixture start from the fixed target, protected entries, recent exact tier, query rows, and 512-token summary blocks; verified 26/64/64 compact entries locally; hash-bound an R2 runner, repair-capable owner, and patch manifest. The R1 request is bound to its ready record and R2 is detached under the retained claim.
- Evidence: R1's C=64 compact_tile_overflow produced no CUDA result. R2 entry starts are 4616 (C26/Q1), 24072 (C64/Q1), and 8200 (C64/Q32), each producing its required compact-entry count before allocation. The R2 owner crossed into its generation-specific CUDA capture.
- Interpretation: the repair changes only harness geometry; U=8, the planner, sources, tolerance, workload, and c32 endpoint contract are unchanged.
- Next: let the durable owner complete the CUDA gate or publish a retained same-claim repair; do not replay the consumed materializing c32 arm.

## 2026-07-29T11:47Z — CUDA passes; endpoint activation repair retained

- Question: did the corrected R2 fixture establish the target-H200 discriminator before the conditional candidate endpoint?
- Action: retrieved the atomically persisted R2 CUDA result and the endpoint’s compact failure capture.
- Evidence: C26/Q1 and both C64 boundaries passed with 26/64/64 compact entries; maximum absolute error was at most 0.00048828125. The profiler-off C26 component median was 1,156,154 ns activated versus 1,519,664 ns streamed. The endpoint made zero requests and failed before root creation because the candidate-server activation environment was absent.
- Interpretation: CUDA is a completed producer and must not be replayed. The endpoint activation flag omission is an ordinary integration defect, but R2’s endpoint repair branch exits after a request instead of resuming the endpoint; the live owner must not be signaled until a binding authorizes a repair-capable handoff.
- Next: preserve the live retained claim and request a same-claim endpoint-owner repair binding; do not rerun CUDA or the consumed materializing arm.

## 2026-07-29T12:58Z — fresh candidate endpoint owner prepared

- Question: can the unconsumed c32 candidate endpoint be resumed from a cold H200 without replaying the settled CUDA producer?
- Action: carried the proven SGLang `RadixAttention.forward` seam into a fail-closed U=8 streamed hook, added a candidate-only c32 consumer requiring an immutable activation capture and layer-35 telemetry, and bound a future-only v6 owner to preclaim input materialization, resumable staging, health, endpoint-only repair, retrieval, and generation-fenced release.
- Evidence: the v6 shell parses; endpoint and hook compile; final owner, endpoint, hook, candidate, activated source, checkpoint manifest, runner, image, workload, and preserved CUDA producer are content-bound in `STREAMING_GLOBAL_KV_FRESH_ENDPOINT_OWNER_READY.json`. No pool, SSH, provider, GPU, or SM120 operation occurred.
- Interpretation: the old resource is retired, the CUDA result remains consumed exactly once, and the sole open scientific sample is the fresh candidate c32 endpoint under a later reservation-and-execution binding.
- Next: director may bind a new H200 and launch this owner through `detached-owner`; do not start it or claim a bench from this preparation.

## 2026-07-29T15:00 — V12 pre-stop owner-loss conflict

- Action: derived V12 only from V11, replaced only `part_state()` with an stdin-free quote-safe remote size/SHA256 probe, and passed the exact absent/present fixture.
- Evidence: V12 owner SHA `21a5364a9a428b47ec0e0ad6af89678a8185d31b0832dc6f620759ef870af03e`; patch SHA `a7dcafae61a051bdcb58a81a9fdbb13f9eac0a42a70eede0674de4a6a895a97f`. The V12 pre-stop snapshot found the retained claim and 34,307,773,440-byte partial, no containers/endpoint roots/terminals, but detached-owner marked required PID 74239 `live:false`.
- Interpretation: pre-science owner loss contradicts V12's required live-predecessor transition; launching its command would exceed the binding.
- Next: director rebinds same-claim owner-loss recovery; preserve the claim, partial, image, and immutable inputs.

## 2026-07-29T15:56Z — V12 invalid endpoint no-replay guard and geometry boundary

- Question: can the install-only endpoint observer be repaired in place without replaying attempt 0?
- Action: revalidated live PID `102131`/start ticks `145439383`, the retained claim generation, ready hash `7fafb09b…`, absent request, attempt-0 terminal `5a7bee8c…`, and conflict `ab3dd111…`. Installed and exercised a guest endpoint guard that exits before `exact_runner.py` unless a repair authorization exists; it left no output root and preserved the loaded container.
- Evidence: the exact checkpoint `text_config` and live SGLang constructor geometry are q32/kv16/d256, while the admitted streamed consumer and hook contract are q32/kv4/d512. The hook's install-only row is therefore a false activation predicate. `V12_INVALID_ENDPOINT_REPAIR_PATCH.json` (`d5b13382…`) preserves the source hashes, smoke, and the healthy 122932-MiB resident server state.
- Interpretation: changing only the hook/adoption seam cannot translate kv16/d256 into the hard-coded kv4/d512 consumer without changing GQA head ownership and stride semantics. It is a typed integration-contract boundary, not a negative endpoint result. No request was written because the waiting owner would blindly invoke a second endpoint and there is no lawful corrected endpoint to authorize.
- Next: retain the existing server and claim; the director needs a rebind that either admits a geometry-correct consumer implementation or adopts a generation-fenced invalid/unrepaired terminal. Do not run another endpoint or replay the CUDA producer.

## 2026-07-29T15:53Z — V12 repair owner lost after guard

- Evidence: detached-owner reports PID `102131`/start ticks `145439383` `live:false`; the bench claim was still live with its last heartbeat at `15:52:40Z`, the repair handshake was still waiting, and no project terminal or repair request exists.
- Interpretation: the owner's fixed 600-second repair wait expired before the persisted 16:35Z deadline, an ordinary controller defect. The current binding names only that owner and does not authorize a replacement, so this project cannot safely restore a claim heartbeat itself.
- Next: director must issue a hash-bound same-claim rebind. Preserve the live container and guarded endpoint; no endpoint was replayed.
