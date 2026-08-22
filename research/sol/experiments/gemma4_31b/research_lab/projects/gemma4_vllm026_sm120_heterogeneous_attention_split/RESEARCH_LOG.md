# Research log

## 2026-07-29T07:11Z — exact offline split implemented

- Question: can vLLM 0.26.0 replace Gemma4's whole-model Triton selection with
  exact local/global consumers on sm_120?
- Action: traced `Gemma4Attention` through `Attention`, KV-spec grouping,
  `backend_per_kind`, model-runner metadata groups, and the FlashAttention,
  FlashInfer, Triton, and Flex consumers. Implemented a fail-closed config
  adapter and a fresh-process future sm_120 A/B oracle.
- Evidence: the exact admissible stock split is 50 sliding layers on
  `TRITON_ATTN` and 10 full layers on `FLEX_ATTENTION`. Both consume the same
  NHD paged-KV layout. FlashAttention is invalid for the exact SM120
  multimodal-prefix/head-size combination, FlashInfer lacks prefix support,
  and Flex is not exact for Gemma4's clamped sliding mask without another
  patch. Three offline mutation tests pass.
- Interpretation: retain this as a zero-build future component candidate. The
  physical hypothesis is lower global-attention kernel time and removal of the
  global Triton segmented-softmax scratch family; no endpoint gain or KV-byte
  reduction is claimed.
- Next: only after the norm-FP8 itinerary resolves and a director handoff
  permits the bench, run `future_sm120_oracle.py`; if it passes, measure the
  otherwise identical c32 endpoint with the emitted attention config.

Result:
`VLLM026_SM120_HETEROGENEOUS_ATTENTION_SPLIT_OFFLINE_RESULT.json`.

## 2026-07-29T07:54Z — component owner prepared offline

- Question: can the future one-shot all-TRITON versus layer-aware-FLEX oracle
  be executed without violating the shared warm-bench lifecycle?
- Action: added `run_sm120_attention_split_component_owner.py`. It rejects the
  preparation binding, requires a later hash-chained execution binding, uses
  `GpuClaimSession`, stages only the bound oracle after claim, verifies and
  stops only the future named PID/start-tick server tree, fences accelerator
  allocations, and retrieves separate arm evidence before classifying a
  terminal. Incomplete output enters a fresh hash-bound repair generation;
  completed arms are never replayed.
- Evidence: `py_compile` passed; the existing exact-dispatch unit suite passed
  3/3; invoking the owner with the preparation binding failed closed before
  `GpuPool` construction. No GPU, SSH, provider, or pool operation occurred.
- Interpretation: this is an executable controller preparation, not a sample
  or a claim authorization. The future binding must explicitly name the bench,
  server generation, SSH argv, and deadline.
- Next: director resolves the norm-FP8 terminal/reservation queue, then emits
  the later execution binding and launches the detached controller command in
  the owner-preparation result.

## 2026-07-29T08:30Z — retained owner repair conflict (no scientific sample)

- Action: launched the exact `b6ebe2a4…` detached command before its 08:33Z
  fence. It atomically claimed `rtxpro6000-gemma4-fp8-f4nbtoufbwf66f` at
  `08:29:54Z`; the heartbeat is live.
- Evidence: before any remote oracle command, `FileNotFoundError` occurred
  while persisting predecessor-fence output below an uncreated generation
  directory. The owner then overwrote the detached-owner `OWNER_STATE.json`
  with its progress state. Its live repair record is
  `.repair-handshakes/attention-owner-2026-07-29T082954.858364Z-r2/REPAIR_READY.json`.
- Interpretation: this is a controller integration/observability defect, not
  CUDA execution or an oracle result. The repair record permits only
  retrieval/adoption, yet no oracle exists, and this bound owner has no path
  to consume a pre-submission patch and retry. A mismatched request or a
  competing replacement would violate the binding.
- Next: director must issue a same-claim replacement/repair binding that
  preserves `claimed_at=2026-07-29T08:29:54.858364Z`, repairs the local
  directory/state-path bug, and authorizes the transition. Do not replay any
  scientific arm or checkpoint staging.

## 2026-07-29T08:33Z — repair-request entrypoint audit

- Action: inspected the live repair diagnostic once and the owner’s exact
  request path before signaling it.
- Evidence: `REPAIR_READY` binds only
  `retrieve_or_adopt_existing_attention_oracle_terminal`. The loaded owner
  waits for a request, then writes `typed_owner_deadline_or_unrepaired_boundary`
  and raises; it never dispatches back to `stage_oracle_after_claim` or any
  patched pre-submission operation. The durable controller and claim remain
  live.
- Interpretation: no retrieval target exists, so sending the documented
  request would wake the owner into release control flow and cannot repair the
  defect. Withholding that mismatched request is required to retain the claim;
  this remains a typed binding/owner entrypoint conflict, not a sample.
- Next: director rebinds an owner that can consume a same-claim pre-submission
  repair request or explicitly hands off to a replacement. No scientific arm
  may be replayed.

## 2026-07-29T09:15Z — stopped-predecessor fence repaired offline

- Action: preserved live exact PID/start-ticks fencing and added a fail-closed
  `already_stopped` path. It requires the bound prior claim generation and
  invalid-attempt terminal digest, sends no signal, and records a post-claim
  zero-allocation plus zero vLLM/attention-oracle/norm-FP8-driver census before
  staging the oracle.
- Evidence: behavioral mocks passed for live fencing, valid stopped fencing,
  missing stopped evidence rejection, normalized `0.26.0` acceptance,
  wrong-version rejection, zero-output terminal rejection, and complete
  two-arm/path-proof terminal acceptance. `py_compile` passed.
- Interpretation: zero-GPU controller repair only; no parent arm, CUDA path,
  endpoint c32, checkpoint transfer, or scientific sample occurred.
- Next: a later director must hash-bind stopped-predecessor evidence and
  explicitly reopen claim/launch authority.

## 2026-07-29T09:36Z — stopped-predecessor execution retained for repair

- Action: launched the exact `dae923b7…` durable owner. It claimed at
  `2026-07-29T09:36:50.649263Z`, persisted the bound no-signal predecessor
  census (zero allocations and zero forbidden drivers), then made its one
  parent invocation.
- Evidence: the parent exited `1` before either control or candidate arm:
  `FileExistsError` shows the owner made `run/` before the unchanged oracle,
  whose contract requires an absent output directory. There are no arm files,
  CUDA path proof, rows, or parent stdout. `REPAIR_READY` is live but binds
  only `retrieve_or_adopt_existing_attention_oracle_terminal`.
- Interpretation: this is an unconsumed pre-submission output-root integration
  defect. A retrieval-only request cannot apply the localized controller patch
  and would enter its release path, so it was withheld while the owner retains
  the claim.
- Next: director must bind an in-place pre-submission repair or explicit
  same-claim replacement; do not resend the parent until that authority exists.

## 2026-07-29T09:49Z — corrected parent terminal retrieved, incomplete

- Action: retrieved the sole corrected parent's remote terminal and arm logs
  after confirming the exact owner, claim generation, and r1 handshake hash.
- Evidence: `SM120_ATTENTION_SPLIT_ORACLE.json` is `oracle_failed`; both arms
  exited `1` with no rows or path proof. The candidate log records
  `No valid triton configs` for FLEX attention on SM120: required resource
  `156672` exceeds the `101376` hardware limit. Retrieved terminal SHA-256 is
  `f7f8950e…`; the output-root evidence is retained under
  `repairs/output-root-r1`.
- Interpretation: the parent was submitted exactly once, but its terminal is
  incomplete under the owner contract. No r1 adoption request was sent and no
  replay is authorized. This is not a completed component comparison.
- Next: project is paused pending a material director process/terminal wake;
  preserve the owner, claim, and release/watchdog fences.

## 2026-07-29T10:05Z — deep SM120 runtime repair parent launched

- Evidence: binding `9c219ead…`, invalid terminal `f7f8950e…`, live owner
  PID/start ticks, exact claim generation, unchanged r1 ready digest, absent
  request, and a quiescent remote executor were each revalidated once.
- Repair: pinned vLLM documents `VLLM_USE_FLASHINFER_SAMPLER=0` as its native
  sampler selection. The pinned FLEX backend accepts legal minimum 16x16
  tiles with matching 16-token logical Q/KV blocks; these preserve the 50
  TRITON / 10 FLEX dispatch semantics while reducing lowering live state.
- Action: archived remote `run/` as `run.invalid-f7f8950e…`, atomically staged
  source `ec3a1b92…`, and launched exactly one fresh parent (remote PID 38078)
  without precreating its exclusive output root. No r1 request has been sent.

## 2026-07-29T10:09Z — terminal inspection: execution remains live

- Evidence: the durable owner remains live with the unchanged r1-ready digest
  and no request. Remote parent PID 38078 is live, no terminal exists, and
  `VLLM::EngineCore` holds 12,346 MiB.
- Interpretation: this is active scientific execution, not a terminal or
  repair boundary. No adoption request or replay is authorized.
- Next: pause until a material terminal or parent-exit wake; preserve the
  existing owner, claim, 10:37Z release fence, and 10:45Z watchdog.

## 2026-07-29T10:43Z — corrected terminal retrieved and adopted locally

- Action: retrieval-only controller claimed the director-bound quiescent RTX
  bench, rechecked absent PID 38078 and zero allocations, then retrieved the
  bound terminal and both arm JSONs plus existing captures. It released the
  claim generation-fenced to maintenance.
- Evidence: terminal `b6f891f0…`, control `8ef31c46…`, and candidate
  `d372cc28…` match their binding hashes. Both arms exited zero, have three
  rows, and their semantic rows are equal. All three required backend
  path-proof flags are false; typed adoption terminal `cb7efaf5…` preserves
  the four capture hashes and classifies this as incomplete path proof.
- Interpretation: the retrieved bytes are decision-bearing evidence of an
  incomplete component oracle, not a valid backend comparison. No request,
  oracle replay, checkpoint activity, or endpoint run occurred.
- Next: director disposition only; any replay requires a new binding.

## 2026-07-29T11:06Z — path proof reconstructed offline; no replay

- Question: why did the completed all-TRITON/control and
  50-TRITON/10-FLEX candidate return equal rows but all three backend proof
  flags false?
- Action: read the hash-bound retrieval terminal, final oracle, corrected
  source, and four captures once, then traced only the pinned vLLM 0.26.0
  per-kind selector, layer construction, eager attention call, and Triton/Flex
  forwards.
- Evidence: the oracle searched only each arm's `stderr_text`. vLLM emitted
  the required backend-resolution records to stdout. Immutable control stdout
  contains `Using ... TRITON_ATTN`; candidate stdout contains both
  `Using ... TRITON_ATTN` and `Using ... FLEX_ATTENTION`. The pinned selector
  gives `backend_per_kind` precedence, constructs a fixed implementation per
  layer, and the eager forward path calls that implementation with no backend
  fallback. Both arms exited zero and all three semantic rows are equal.
- Interpretation: this is
  `offline_reconstructable_proof_from_immutable_captures`, not an attention
  or observer-infeasibility negative. Reconstructed control-TRITON,
  candidate-TRITON, and candidate-FLEX proof are all true; the sole corrected
  parent is a consumed valid component sample.
- Next: no replay is authorized or needed. The director may separately admit
  the unchanged c32 endpoint measurement; this component result alone does
  not satisfy the campaign's `0.500119281574996 s/request` endpoint target.

Disposition:
`SM120_ATTENTION_PATH_PROOF_CAUSAL_DISPOSITION.json`.

## 2026-07-29T11:28Z — c32 endpoint owner prepared offline

- Question: can the valid exact-semantics component be promoted to one future
  matched all-TRITON versus 50-TRITON/10-FLEX c32 endpoint pair without
  replaying the consumed parent or opening GPU authority during preparation?
- Action: added `run_sm120_attention_split_c32_owner.py` and
  `sm120_attention_split_c32_endpoint.py`. The owner is inert without a later
  hash-chained execution binding, binds the exact checkpoint manifest,
  workload, official vLLM wheel, image, causal disposition, and no-fallback
  source, and retains repair ownership across server/consumer defects. The
  endpoint consumer runs one complete 32-request arm per generation with exact
  prompt/output accounting and per-row response/timing hashes.
- Evidence: `py_compile`, endpoint workload preflight, and owner preclaim
  validation passed. A local fake OpenAI-compatible server completed 32/32
  control rows with the required 4214/358 token geometry. No gpu_pool, SSH,
  provider API, checkpoint staging, or scientific parent replay occurred.
- Interpretation: this is executable future owner preparation, not GPU or
  endpoint evidence. A later binding must provide the director-created bench,
  SSH identity, resident checkpoint path, exact control/candidate server argv
  and environment, ports, release fence, and source/path-proof identities.
- Next: publish the final hash-bound READY artifact and matching STATUS
  handoff; director may create only after the durable $6 reservation gate.

## 2026-07-29T12:34Z — SM120 cold bootstrap stopped before science

- Question: can the bound cold-start owner stage the exact eight-file
  checkpoint and verified official vLLM wheel inside the amended SM120 claim
  window, then run the matched c32 endpoint pair?
- Action: patched only the owner for resumable `.part` checkpoint transfer,
  remote SHA-256 verification/atomic finalization, official wheel
  verification/install, vLLM 0.26.0 and SM120 capability proof, then claimed
  `rtxpro6000-sm120-attention-c32-3u5oyb8eazps50` at 12:20:53Z and launched
  the exact PID-managed command. Repaired two pre-science controller defects
  in place: detached-owner artifact-root admission and missing local rsync;
  the latter used resumable SSH append, later bound with AES-GCM. No component
  parent replay occurred.
- Evidence: first owner exited before claim from the artifact-root mismatch;
  retry entered the claim and verified all metadata files. The large first
  safetensor reached 12,364,095,488 bytes of 49,784,788,364 at roughly
  20 MB/s, making completion plus runtime bootstrap and endpoint arms
  infeasible before the 13:01Z fence. Final remote census showed no transfer
  or vLLM process, zero GPU compute applications, and the partial `.part`
  retained. Artifacts: `COLD_BOOTSTRAP_BLOCKER.json`,
  `REMOTE_PRE_RELEASE_CENSUS.json`, and `BENCH_CONTENTS.json` under the
  endpoint artifact root.
- Interpretation: typed external cold-bootstrap throughput blocker; this is
  not an attention, runtime-support, or endpoint result. `science_consumed`,
  `science_started`, and candidate CUDA invocation remain false.
- Next: director should preserve or rebind the maintenance bench with a
  higher-throughput transfer path or compatible resident checkpoint, then
  rerun only cold bootstrap and continue to the unchanged endpoint pair.

## 2026-07-29T13:10Z — retained checkpoint owner launched under exact binding

- Action: revalidated execution binding `7f35bab3…`, parallel staging patch
  `cbcb4e1b…`, owner `456850be…`, bench identity, and watchdog PID 6661;
  lifecycle-pure preclaim passed. Claimed only the named RTX PRO bench at
  13:07:58Z and launched the literal binding `detached_owner_command`.
- Pre-science repair evidence: two manual launch attempts had duplicated the
  artifact-root argument. Both were stopped with their exact local owner and
  SSH stream trees reaped; their artifact roots were preserved as
  `artifacts/sm120-attention-c32-resume-20260729t1304z-launcher-defects`.
  They produced no server, model-load, CUDA, or science marker; retained
  remote checkpoint bytes remain resumable under the same claim.
- Current evidence: exact PID-managed owner PID 15764, start ticks 144666417,
  state path `artifacts/sm120-attention-c32-resume-20260729t1304z/DETACHED_OWNER.json`,
  and binding snapshot hash 7f35bab3…. Two distinct AES-GCM append streams
  are active for the incomplete safetensors; no endpoint arm has started.
- Interpretation: staging is active, no scientific sample is yet consumed,
  and the owner must continue through bootstrap, control, candidate, repair,
  and generation-fenced release by 14:00Z.

## 2026-07-29T14:01Z — checkpoint completed; owner stopped at bootstrap harness defect

- Action: monitored the single bound owner under the retained claim. The two
  large safetensors completed through the parallel AES-GCM streams, all eight
  checkpoint files were verified, and `CHECKPOINT_TRANSFER.json` persisted the
  exact manifest. No second owner, component replay, H200 action, or provider
  lifecycle mutation occurred.
- Evidence: the owner then exited before constructing the official-wheel
  remote command with `ValueError: Invalid format specifier` from unescaped
  braces in the embedded runtime-identity Python dictionary. No official
  wheel command, server, model load, CUDA call, science marker, or endpoint
  terminal exists. Typed terminal:
  `artifacts/sm120-attention-c32-resume-20260729t1304z/EXECUTION_ATTEMPT_TERMINAL.json`.
- Disposition: the absolute 14:00Z release fence had passed, so the claim was
  released to maintenance at 14:01:17Z with `BENCH_CONTENTS.json`. The exact
  checkpoint remains resident and reusable; this is incomplete integration
  evidence, not a scientific negative. Conservative cumulative exposure is
  settled at the binding maximum `$7.815453394075` through watchdog cleanup.
- Next: director must issue a fresh same-claim repair/execution binding for the
  owner f-string defect; reuse the verified checkpoint and do not restage or
  replay the consumed component parent.
