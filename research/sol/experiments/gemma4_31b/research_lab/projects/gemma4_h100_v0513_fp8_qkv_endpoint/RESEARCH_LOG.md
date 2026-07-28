# Research log

## 2026-07-20 — delegated

The campaign's residual-frontier phase explicitly requires a matched H100 placement falsifier. The exact H200 QKV terminal, v0.5.13 runtime identity, representation, source bytes, workload, and `$0.741 s/request` economic ceiling are bound in `BINDINGS.json`. No provider resource or scientific arm exists yet.

## 2026-07-20 — bound snapshot and owner prepared; H100 inventory boundary

Question: can the admitted c32 FP8+QKV arm be launched as soon as a lab H100 exists?

Action and measured evidence: SHA-256 verification passed for the authoritative QKV terminal and all six consumed source files. The previously implicit QKV discriminator helper was added to the binding and materialized with the other immutable files under `inputs/`. A project-local owner and remote consumer now retain one claim through repair/retrieval, stage only missing or mismatched checkpoint files through a hash manifest, require c32/cache/240-FP8-module/consumer/QKV audit evidence, retrieve the compact bundle plus raw worker output and invocation marker, and apply the `<=0.741 s/request` decision gate. Python compilation and shell syntax checks passed.

Interpretation: these are readiness checks, not endpoint evidence. The atomic pool claim for `nvidia-h100-sxm` returned `no available GPU bench matches this project`; inventory has no available H100. No provider resource, checkpoint transfer, image pull, GPU invocation, or project spend occurred.

Next move: after the director registers an H100 and the reservation is durable, run the sole arm through `h100_endpoint_owner.py` with an absolute deadline.

## 2026-07-20 — pre-invocation checkpoint staging boundary

Action: the durable owner atomically claimed the director-registered H100 and completed remote identity/host diagnostics. Checkpoint staging returned typed_staging_boundary:checkpoint_hash_failed before it wrote INVOCATION_STATE.json, candidate CUDA, or candidate scientific markers.

Evidence: the retained artifact root contains the owner terminal, outer event stream, and remote identity stdout/stderr. Exposure was measured at 23.6647 seconds and $0.0141331 at the registered $2.15/hour rate. The old owner release path marked the bench maintenance; the pool now rejects a new claim because of that director-visible state.

Interpretation: this is an ordinary pre-invocation owner/staging defect, not a result and not arm consumption. The project-local owner now derives the actual registered rate, preserves a claimed bench through a repair handshake, and captures checkpoint-stage stdout/stderr. The bench requires director return to available; no new allocation is authorized.

## 2026-07-20 — retained H100 staging repair active

The restored H100 was claimed by the patched durable owner. Captured staging diagnostics established that the cold guest lacks both huggingface-cli and pip; the stager was repaired to use direct manifest-bound curl transfers with per-file size/SHA-256 verification. Six small files finalized under checkpoint.staging and the first 49.8-GB shard is downloading (2,432,524,288 bytes observed). The claim heartbeat is healthy and no CUDA, server, or scientific arm marker exists.

## 2026-07-20 — director maintenance inspection passed

The exact provider instance is RUNNING, its disk is READY and attached, the recorded watchdog is active, SSH succeeds, and the guest reports one H100 80GB with MIG disabled. The remote checkpoint root exists but is empty, confirming the failure occurred during staging rather than after a hidden model or scientific invocation. Inventory contents were corrected and the same bench was returned to available. Resume only with the patched durable owner; the sole c32 arm remains unconsumed.

## 2026-07-20 — owner deadline reached; provider absent; replacement staging required

The restored owner remained heartbeating through its absolute deadline, but sequential direct checkpoint transfer exhausted the window. Retrieved `INVOCATION_STATE.json` records `candidate_cuda_started=true` and `candidate_science_started=false`; the empty remote terminal and repair record show the process was terminated at the bounded repair deadline before any c32 arm. After the lease became stale, the director inspected the failed owner, reclaimed the bench to maintenance, and made one authenticated provider listing. Exact instance `computeinstance-e00r2qev2c3z3n2y08` and disk `computedisk-e00feh1fke1p86t48a` were both absent after the successful watchdog exit, so inventory was retired with cleanup verified and no deletion call.

The H100 economic question remains unconsumed. Increase cumulative authority to `$11.50` and require one offline controller repair: reuse the exact local checkpoint snapshot and the H200 owner's resumable content-addressed transfer rather than sequential guest-side HTTP. A typed staging-ready terminal gates one replacement director allocation; no provider creation or scientific inference is authorized in this preparation turn.

## 2026-07-20 — offline staging controller ready

Question: can the replacement H100 avoid the previous sequential guest HTTP staging boundary without duplicating the local checkpoint?

Action/evidence: bound and SHA-256 verified all eight files in the existing read-only H200 residual snapshot (62,578,655,208 bytes). STAGING_READY.json records the full manifest, source identity, and a compiled transfer controller. The future owner now uses two parallel resumable SFTP append streams for the two safetensor shards, retains named partials across restarts, records each transfer's elapsed time/throughput/hash, then verifies remotely before atomic read-only finalization.

Interpretation: this is an offline transfer-contract terminal, not CUDA or endpoint evidence. It passes the director allocation gate; the sole H100 c32 arm remains unconsumed.

## 2026-07-20 — one-off replacement H100 launched and transfer repaired in place

The cleanup-verified retired attempt was replaced once under the existing `$11.50`/four-H100-hour authority. Replacement instance `computeinstance-e00nmpn5czcb44jqm1` and disk `computedisk-e00rd32znm10exgyy3` are registered as bench `h100-v0513-fp8qkv-r2-e00nmpn5czcb44jqm1`. Owner `gemma4-h100-r2-owner.service` is protected through `13:59:17Z`; independent watchdog `gemma4-h100-r2-watchdog.service` cleans by `14:09:17Z`. Maximum replacement exposure is `$5.02`, keeping cumulative H100 exposure within the project reservation.

The first transfer invocation found that OpenSSH `sftp put -a` requires the remote partial to exist. No CUDA or scientific arm began. The retained owner accepted one in-place repair that creates the content-addressed partial before resuming. Both weight-shard transfers are now concurrent and advancing; an early sample recorded approximately 498 MB and 549 MB in the two remote partials. The repair request was consumed so it cannot authorize a later automatic retry.
## 2026-07-20 — H100 placement arm reconciled negative

The sole exact v0.5.13 FP8+QKV c32 arm was consumed and completed 32/32 requests at `0.9510141324 s/request`, with exact 17,120 cached and 117,728 uncached prompt tokens. This is 28.34% above the `0.741 s/request` H100 economic gate, so the matched placement is `endpoint_negative`. The worker's `path_unproven: consumer_audit_failed` classification was a postprocessing defect: the entrypoint and stack auditors both wrote the same 240 module prefixes to the shared file (480 valid rows), while 241 FP8 scaled-matmul consumer rows and two `_qkv_norm_rope_inplace_kernel` rows prove the intended path. `RECONCILED_TERMINAL.json` binds the immutable archive and evidence hashes; no replay is authorized. Conservative measured project exposure is `$5.845653`, including the retired first attempt and the replacement's full registered lifetime. Instance `computeinstance-e00nmpn5czcb44jqm1` and disk `computedisk-e00rd32znm10exgyy3` are verified absent, the watchdog is inactive, and the bench is retired.
