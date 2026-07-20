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
