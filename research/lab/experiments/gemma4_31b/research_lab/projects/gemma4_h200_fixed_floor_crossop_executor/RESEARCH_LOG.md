# Research log

## 2026-07-30 — R5 owner-retention and claim-launch seam repair

- Action: Under offline-only binding `2803248d...`, replaced the unsafe R5 owner with a retained multi-generation dispatcher and added the sole project-relative claim/derive/detached-owner entrypoint. The candidate runner and emitted-chunk oracle were not changed.
- Evidence: `R5_OWNER_REPAIR_VALIDATION.json` (`903202d...`) records Python compilation plus bounded fake boundaries for immutable repair consumption, no release on a recoverable path, decision-to-ready release, deadline-to-generation-fenced maintenance release, and fresh ready-gated detached launch publication. Packet and paused envelope hashes were rechecked against every member.
- Disposition: R5 is paused and claim-disallowed. No claim, SSH, CUDA, checkpoint, endpoint request, replay, or lifecycle operation occurred. A later director must issue a new time-bounded execution binding before the launcher may run.

## 2026-07-30 — R5 offline corrected-completions preparation

- Question: Can the invalid R4 pre-inference HTTP-400 boundary be corrected without changing the frozen completion-shaped workload or replaying any scientific stage?
- Action: Under offline-only binding `5f529b64...`, prepared the R5 candidate runner, durable dispatcher, packet, and paused execution envelope. The runner sends the unchanged bodies only to `/v1/completions`; it retains HTTP-error status plus up to 8 KiB of response body. The owner preserves candidate-only scope, stages into a noncanonical root, promotes only a complete 32-response ledger, and has separate retained-repair and decision-bearing release paths.
- Evidence: `R5_OFFLINE_VALIDATION.json` binds all four execution hashes. Python compilation and JSON parsing pass; a mocked `HTTPError(400)` verified status/body capture. No claim, SSH, CUDA, checkpoint load, endpoint request, stock/component replay, or provider action occurred.
- Next: The project is paused and claim-disallowed. A director must issue a fresh runnable clock after inspecting the bound R5 bytes.

## 2026-07-30 — R4 scalar repair reaches a consumed invalid endpoint sample

- Action: Verified the R4 binding, owner, claim, H200 UUID, SSH fingerprint, and watchdog; staged hash-verified source-only scale repairs over strict SSH and kept the same owner and claim. The first scalar repair exposed capture-illegal `.item()` paths, which were repaired in place without replaying stock or the component. Generation 5 used the live `k_scale_float`/`v_scale_float` Python scalars and a graph-safe audit path.
- Evidence: `PAIR_TERMINAL.json` (`2835f52e...`) records 32 candidate submissions, local/global cache-commit proof, and zero completed candidate requests: all requests returned HTTP 400, with zero SSE events and no emitted-chunk matches. The immutable 32-request stock arm was not replayed. The candidate terminal is consumed and invalid, not a latency result.
- Disposition: Released the same claim at `05:39:19Z` with conservative cumulative project spend `$1.887` (prior measured exposure plus the continuous 2,583-second H200 claim). Preserve the terminal and server artifacts; do not replay the candidate. A future endpoint admission must first diagnose the request-contract 400s.

## 2026-07-30 — R4 candidate-only retained repair: Triton constexpr scale selection

- Question: Can the already-authorized candidate-only endpoint arm proceed without replaying frozen stock after its first no-request startup failed?
- Action: Retrieved the R4 generation-0 diagnostic and full remote server stderr while owner `570159` kept the same `04:55:56Z` claim heartbeating. The candidate loaded the exact model and reached CUDA-graph capture, but no request was submitted. Archived remote zero-request root `candidate-r4-g0` as `candidate-r4-g0.pre_request_failed_20260730t0524z`; patched only `fused_qkv_kv_cache.py` to replace the illegal runtime `tl.where` over `K_SCALE`/`V_SCALE` constexpr values with the two branch-masked constant divisions, verified the staged remote SHA-256 `7ee1a18d...`, and submitted the hash-bound `candidate_only` repair request.
- Evidence: The owner consumed `REPAIR_REQUEST.0e8eca...` and advanced to generation 1, `candidate-r4-g1`, at `05:24:49Z`. The failure is a Triton compilation/integration defect, not endpoint evidence: model loading completed, then CUDA graph capture raised `CompilationError` at the scale select; `candidate_requests_submitted=0` and no `PAIR_TERMINAL.json` existed.
- Next: The same owner executes only candidate generation 1 and will retrieve a complete terminal or publish the next retained repair boundary before the absolute deadline. Frozen 32-request stock and the consumed component are not replayable.

## 2026-07-30 — R3 immutable-control observer disproves candidate-only admissibility

- Question: Can the director-bound R3 observer recover exact control emitted-token provenance without replaying stock?
- Action: Implemented and exercised `fixed_floor_crossop_endpoint_token_observer.py` against a read-only project-local retrieval of the 32 immutable remote control SSE files. The observer binds the frozen control terminal hash `6bc155f1...`, records each SSE hash and event count, and deliberately performs no tokenizer decode/re-encode.
- Evidence: `artifacts/fixed-floor-crossop-endpoint-r3-candidate-only-20260730t0503z-preflight/CONTROL_TOKEN_OBSERVER.json` exits `72`: every row has 359 SSE events and exactly zero `choice.token_ids`. This is measured provenance evidence, not a candidate result. The observer, candidate-only boundary, R3 owner, and packet compile and are hash-bound in the R3 packet; the observer gate is false.
- Interpretation: The director binding expressly forbids substituting text/usage equality or a decode/re-encode inference for emitted IDs. Therefore its prerequisite for all 32 candidate requests is false. Replacing a healthy R2 owner to enter a candidate-only arm would consume the only candidate sample while making the exact-token pair permanently uninterpretable.
- Next: Preserve owner `554215`, its claim, all frozen stock bytes, and the preflight artifact. Do not write an R2 request, transition to R3, or submit candidate traffic unless a director materially changes the exact-token evidence contract.

## 2026-07-30 — retained R2 candidate-start repair needs a director-bound narrow entrypoint

- Action: Retrieved and hash-bound the generation-1 worker evidence while owner `554215` remained live and heartbeating. Archived the remote zero-request candidate partial root atomically as `candidate.pre_request_failed_20260730t0500z`; its manifest and the local compact copies are under `artifacts/fixed-floor-crossop-endpoint-r2-20260730t0451z/run/g1-retrieved/`.
- Evidence: The stock arm persisted 32 completed responses (`control-TERMINAL.json`, `6bc155f1...`) but its token-ID observer is empty, so it cannot certify the pair. Candidate launched a container but failed before readiness or a request with the weight-loader assertion `torch.Size([256])` versus `torch.Size([512])` (`candidate-server.stderr`, `2124f19e...`). `REPAIR_ENTRYPOINT_CONFLICT-g1.json` (`03e40eb...` diagnostic) proves the live bound owner recognizes only `stage_and_pair`, `pair_runner_only`, and `retrieval_only`: its two runnable scopes rerun the monolithic stock/candidate runner, while retrieval-only requires an absent pair terminal.
- Disposition: This is an ordinary integration/observer failure, not endpoint evidence. No safe documented `REPAIR_REQUEST.json` exists: requesting any accepted runnable scope would replay the consumed stock arm, and an unrecognized `candidate_only` scope is normalized by the owner to that same replay. Preserve the owner and claim; require a director-bound candidate-only/token-observer entrypoint or replacement authority before repair.

## 2026-07-30 — exact c32 endpoint packet ready, offline only

- Action: Verified `b62b46af...`, predecessor `71b73736...`, the accepted component/resource hashes, the durable `$4` reservation, and replacement watchdog `546249`. Materialized the pinned `gemma4_causal.py` under this project as a verified hard-link, then built the adapter, sequential c32 pair runner, and retained-repair owner.
- Evidence: `ENDPOINT_INTEGRATION_PACKET_R1.json` binds every mutable execution byte. The adapter initially exposed a stale installer boundary that truncated the pinned runtime's `forward` signature; the adapter now replaces the complete producer-to-attention boundary and passes Python compilation. The pair keeps stock and candidate roots disjoint and requires 32 complete requests, exact token IDs, and local/global cache-commit audits.
- Disposition: Executable readiness is published but remains offline-only. No claim, SSH, CUDA, checkpoint load, component replay, endpoint request, or provider-lifecycle call occurred. A later director must bind the one matched endpoint pair.

## 2026-07-30 — R2 no-launch metadata recovery completed from preserved target objects

- Action: Verified the `eb706cee...` resource-metadata repair binding and ran its bounded R2 compile-only collector on the exact H200. Both `WRITE_CACHE=True` specializations compiled under Triton 3.6.0; the candidate kernel was not launched, no timing was replayed, and no endpoint was called.
- Evidence: The durable terminal is `82706fea...` and release evidence is `8137d07b...`. Although Triton `KernelMetadata` omitted the required fields and PTX had no `.maxnreg`, its immutable CUBIN bytes were captured in that terminal. Parsing the CUDA ELF `.nv.info` records for the exact `.text` section recovered `EIATTR_REGCOUNT`: 26 local registers/thread and 30 global registers/thread. `EIATTR_FRAME_SIZE` and `EIATTR_MIN_STACK_SIZE` are both zero for both objects, establishing zero spill loads and stores. `TARGET_OBJECT_RESOURCE_RECOVERY.json` records the CUBIN and terminal hashes.
- Disposition: The owner unnecessarily released after 10.117141 claim seconds, but no additional claim is necessary: the pinned target objects are authoritative evidence from the compile-only run. The resource gate now passes, the measured component terminal remains consumed exactly once, and cumulative project exposure is `$0.12902125211111112`.

## 2026-07-30 — no-launch resource recovery invalid; owner release defect

- Action: Under `DIRECTOR_FIXED_FLOOR_CROSSOP_H200_RESOURCE_RECOVERY_20260730T0414Z.json`, the collector staged only its runner and the unchanged candidate, entered compile-only mode, and did not launch the candidate, timing loop, component cases, or an endpoint.
- Evidence: Triton compilation returned a `CompiledKernel`, but its installed API has no `n_regs` attribute. `compile.stderr` records the exact `AttributeError`; `RECOVERABLE_DIAGNOSTIC.json` records `resource_terminal` and `no_candidate_launch: true`.
- Disposition: The owner then incorrectly released its 10.013132-second claim rather than waiting on the published repair handshake. The bench is available, but this binding's retained-claim repair path was broken; do not reclaim it in a loop. Cumulative project exposure is `$0.12213597559722224`; the previous ten-case result remains consumed and unchanged.

## 2026-07-30 — consumed R2 ten-case H200 component terminal, acceptance-incomplete

- Action: R2 retained the claim through the standalone SGLang scheduler-context repair and completed the one authorized local/global `M={32,118,1409,1631,2048}` submission. It released the bench ready after 169.439240 claim seconds; cumulative project exposure is `$0.11532148298611113`.
- Measured: `TERMINAL.json` (`8a4fba27...`) identifies NVIDIA H200 SM90, pinned candidate `4b697f3c...`, and pinned memory-pool bytes. Every row has zero QKV NRMSE and byte-exact K/V output; median candidate reductions range from 23.73% to 67.47% (all positive). `EXECUTION_CAPTURE.json` (`eeb6ad1f...`) records the candidate CUDA invocation and persisted terminal; release evidence is `e096676c...`.
- Interpretation: This is a consumed component sample, not an endpoint result. The bound acceptance contract also requires registers/thread `<=32` and zero spills, but the terminal contains no compiled resource metadata. Do not replay the settled component to fill that omission; request a director-bound evidence-only recovery if that gate remains necessary.

## 2026-07-30 — pre-science owner launcher defect; maintenance handoff

- Action: Verified binding `02207541818e...`, the $1 reservation, exact H200 UUID/fingerprint/watchdog, and bound a controller-host owner. It atomically claimed at `03:58:52Z`.
- Evidence: Before the first SSH staging command or CUDA invocation, a Python local-name collision made the owner expand a function as an SSH argument list (`Value after * must be an iterable, not function`). `OWNER_FAILURE.json` is `de8ebc7f...`; release evidence is `dd718723...`. The invocation-state and terminal files do not exist, so no scientific sample was consumed.
- Disposition: The failed owner released the bench to `maintenance` in 0.012735 claim seconds ($0.000008666875). The corrected owner source renames the command list; that necessarily invalidates the previous derived binding. A researcher cannot re-ready the maintenance bench, so a director must inspect/re-ready and issue a new hash-bound execution envelope before retrying the still-unconsumed ten-case ledger.

## 2026-07-30 — director admits one exact H200 component after reservation

- Decision: Reactivate the source-complete QKV norm+RoPE to E5M2 NHD
  KV-cache epilogue as the next direct-H200 component lane. The pinned DFlash
  lineage is closed: measured DFlash was slightly slower than AR and its
  frozen NGRAM comparator has no exact supported backend intersection.
- Gate: Request a cumulative `$1` project reservation. This request is not
  authority; no claim or GPU mutation is allowed until a later director sees
  the exact durable reservation and issues an execution binding.
- Scope: One component-only local/global `M={32,118,1409,1631,2048}` ledger,
  at most 20 wall minutes and 5 scientific GPU minutes, with no endpoint.
  Preserve the offline correctness, register, spill, and per-geometry timing
  gates in `DIRECTOR_FIXED_FLOOR_CROSSOP_H200_ADMISSION_20260730T0351Z.json`.

## 2026-07-27 — source-complete QKV-to-E5M2 cache epilogue

- **Decision:** Selected exactly one boundary: the accepted in-place QKV
  norm+RoPE producer to the indexed NHD E5M2 KV-cache commit. Scheduler
  synchronization was rejected because it waits for dependent model work, and
  previously tested norm/quantization, scheduler, overlap, graph, and tied-head
  candidates were not reopened.
- **Measured evidence:** Direct SQLite reconstruction matched all 3,660 QKV
  chains. Against the retained deferred-local-KV stack, the removable
  divide/cast/store work plus global clones is `0.322976317 s` in the
  `23.038600455 s` c32 window. It represents 19,520 launches and
  459,516,477,440 trace-weighted intermediate bytes; the fused producer still
  owes 54,942,187,520 compulsory E5M2 cache-write bytes.
- **Implementation:** `fused_qkv_kv_cache.py` extends the previously measured
  exact QKV Triton kernel so K/V CTAs store their live BF16 results directly
  into the E5M2 cache. `install_fused_qkv_cache.py` applies only to the pinned
  `gemma4_causal.py` hash and disables the now-redundant downstream cache
  write. `exact_consumer.py` is the sole target-H200 component consumer across
  local/global M=`32,118,1409,1631,2048`.
- **Offline result:** AST/source/installer validation passed. A conservative
  50%-realization transfer from the measured complete window predicts
  `0.6207671440689129 s/request`, a `0.700946%` complete-request reduction from
  `0.625149101968745`; it does not reach the locked
  `0.500119281574996 s/request` target.
- **Handoff:** The source-complete positive is eligible for one
  director-authorized H200 component call only. Use the exact hash-bound command
  in `FIXED_FLOOR_CROSSOP_OFFLINE_TERMINAL.json`. Reject on source mismatch,
  cache-byte mismatch, QKV NRMSE above `1e-5`, registers above 32, spills, or
  non-positive median reduction at any exact geometry. No GPU, checkpoint
  shard, SSH, provider, endpoint, or paid resource was used here.
# 2026-07-30 — R5 candidate-only deadline handoff

- Question: Can the director-authorized corrected R5 candidate-only arm produce 32 exact-oracle completions before its fixed release fence?
- Action: Verified the R5 binding, validation, packet, launcher, owner, runner, immutable control, H200 identity, SSH fingerprint, and watchdog. The live retained owner consumed narrow `candidate_only` repairs only. Retrieved generation-1 remote logs; atomically staged the director-bound `install_fused_qkv_cache.py` repair (`8602b00e...`) and submitted the generation-1 hash-bound request. No stock/control or component replay, request-body/oracle mutation, chat-completions call, or provider lifecycle action occurred.
- Evidence: The candidate server twice failed before readiness because `endpoint_candidate_gemma4_causal.py` could not import `install_fused_qkv_cache`, then SGLang fell back to Transformers and rejected the checkpoint at `torch.Size([256])` vs `torch.Size([512])`; `remote-g1-diagnostic.txt` preserves the raw log. Generation 2 had only one second left under the absolute fence and the SSH worker timed out before a request or compact pair terminal. The durable terminal is `artifacts/fixed-floor-crossop-endpoint-r5-candidate-only-20260730t0610z/TERMINAL.json`: `repair_deadline_boundary`, `science_consumed:false`. The owner released the bench at `06:18:30Z` to maintenance. Conservative cumulative project exposure is `$2.066` (`$1.887` prior plus about `$0.179` for the 264-second R5 claim).
- Disposition: This is a typed lifecycle/deadline handoff, not an endpoint measurement. Preserve g0-g2 diagnostics and do not replay the frozen stock, component, or candidate without a new director lifecycle envelope.

## 2026-07-30 — R5 offline packet closure

- Question: Can the candidate runtime be cleanly re-materialized without the missing installer source that invalidated R5 before requests?
- Action: Added install_fused_qkv_cache.py to the R5 packet and bound the complete runtime chain: candidate model, endpoint adapter, installer, and fused kernel. validate_r5_packet_closure.py staged only the nine packet members into two independent fresh roots and imported the full chain with the container ordering /work/project:/sgl-workspace/sglang/python.
- Evidence: R5_PACKET_CLOSURE_VALIDATION.json (d7f17ff8...) records both clean stages, each with installer digest 8602b00e...; R5_PACKET_CLOSURE_OWNER_VALIDATION.json rebinds packet 846bd42a..., owner 2a631efb..., launcher 1c97d696..., and candidate runner 42f12828....
- Disposition: Offline closure passes, but remains claim-, SSH-, CUDA-, checkpoint-, endpoint-, and provider-lifecycle-disabled. Candidate requests remain zero; no stock or component replay occurred. A director must next bind strict cold-H200 bootstrap and a fresh lifecycle.

## 2026-07-30 — R5 cold bootstrap owner seam

- Action: Bound the exact cold H200 identity and implemented a detached controller-host launcher plus one continuous-claim cold owner. It rechecks claim-generation, H200, SSH fingerprint, and watchdog identities; reconciles immutable manifests through verified temporary names and atomic finalization; heartbeats through retained repairs; and proceeds directly to the unchanged candidate-only runner.
- Evidence: R5_COLD_BOOTSTRAP_OWNER_VALIDATION.json (c5b163b5...) compiles both scripts and executes deterministic fresh/repeated manifest retention plus verify/finalize behavior. The owner and launcher hashes are 76ae253d... and 5f754e54....
- Disposition: This is offline controller evidence only. Claim, SSH, CUDA, checkpoint/image staging, requests, stock/component replay, and provider lifecycle mutation remain false. Candidate requests remain zero.

## 2026-07-30 — R5 cold manifest-acquisition authority boundary

- Action: Read the newest manifest-acquisition binding once, checked the named DFlash compatibility project and its prior materializer once, and checked only credential presence (not credential values). The exact target file manifest is independently content-addressed; the DFlash materializer confirms the exact draft consists of `config.json` and `model.safetensors` at the pinned revision and provides both hashes and weight size.
- Evidence: The only concrete acquisition route is Hugging Face `snapshot_download` at the pinned target and draft commits. This controller has neither `huggingface_hub` installed nor a configured Hugging Face token/cache; the binding supplies no guest-side credential authority. `R5_CHECKPOINT_ROUTE_BLOCKED.json` binds the complete known file identities plus all packet, workload, and emitted-chunk oracle hashes.
- Disposition: This is a typed external credential/authority blocker, not scientific evidence. No claim, SSH, CUDA, checkpoint/image transfer, request, stock/component replay, or provider lifecycle mutation occurred. Candidate requests remain zero and the replacement H200 stays unclaimed.
