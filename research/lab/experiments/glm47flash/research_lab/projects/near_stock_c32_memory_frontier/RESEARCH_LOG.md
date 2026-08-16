# Research log

Opened by the 2026-07-16 user performance-discovery pivot. The scientific target is c32 on the complete 47-layer current-AWQ model, first through runtime memory-tax reduction and then FP8 KV if needed. Produce a measured full-model L40S result, not another readiness-only artifact.

## 2026-07-16 — retained-session operational null

**Question.** Execute the admitted matched c16 control and resident FP8-E4M3-KV c32 recovery under one external-systemd owner.

**Action and evidence.** Offline evidence retained FP8 as the only admissible c32 mechanism: the unchanged-work runtime-only bound is 544.211 tok/s, below the 594.466 tok/s economic gate. Launcher and recovery hashes exactly matched their admission values; checkpoint/tokenizer identities matched; authenticated inventories were zero before and after. The initial unit used a bash ExecStart and was fail-closed before provider creation because the launcher requires `SYSTEMD_EXEC_PID == launcher PID`. One material correction made the launcher direct ExecStart and attempted its recovery as `ExecStartPost`; systemd rejected the malformed post command with a Python `SyntaxError` before the control started. [RETAINED_SESSION_PRE_GPU_FAILURE_R1.json](artifacts/RETAINED_SESSION_PRE_GPU_FAILURE_R1.json) preserves the typed, credential-free diagnostics and zero inventory.

**Interpretation and next move.** No instance, disk, model load, OOM, or throughput sample occurred, so the outcome is an operational null—not evidence about c32. The project stop rule permits completion after this typed pre-GPU failure with verified cleanup. A future retry needs a tested systemd unit composition that keeps the smoke launcher as the direct `ExecStart` PID while queuing recovery without shell-quoting ambiguity.

## 2026-07-16 — $0 retained-sequence correction passes

**Question.** Can the shared recovery path be made safe for direct `Type=oneshot` `ExecStart`/`ExecStartPost` use without a shell, provider call, or wrapper?

**Action and evidence.** Added mutually exclusive `--control-summary` source resolution to `vllm_recover_existing.py` (SHA-256 `c39d79e…`): it requires a readable summary with a retained nonempty instance ID and exactly one retained instance/disk, then rejects mismatched live inventory. Focused resolver and shared-launcher tests passed (38 tests). The local external-systemd proof [RETAINED_SEQUENCE_PROOF_R2.json](artifacts/retained_sequence_proof_r2/RETAINED_SEQUENCE_PROOF_R2.json) passed: direct control had `SYSTEMD_EXEC_PID == PID`, emitted retention before direct post recovery, retained static `c32`, `65536`, and `fp8_e4m3fn` arguments, and mocked scientific failure removed the summary-resolved instance/disk to zero. Its control-failure branch skipped post recovery deterministically. Authenticated Nebius inventory stayed zero instances/zero disks.

**Interpretation and next move.** This removes the r1 shell/PID and post-command parse defects but does not measure FP8 or touch a GPU. Re-queue one later 4,500-second/$1.30 full-model retained FP8-KV c32 session under the proven direct oneshot composition; it remains the only c32 scientific arm.

## 2026-07-16 — exit-1 retention proof and r3 measurement launch

**Question.** Does a retained control that exits 1 still execute direct post recovery, and, if so, can the admitted FP8 session start under that same ownership contract?

**Action and evidence.** The extended local proof [RETAINED_SEQUENCE_PROOF_R2.json](artifacts/retained_sequence_proof_r3/RETAINED_SEQUENCE_PROOF_R2.json) passed its `retained_exit_one` branch: `Type=oneshot` plus `SuccessExitStatus=1` accepted the direct control's exit 1, then started direct recovery after the retained summary and reached mocked zero-instance/zero-disk cleanup. The focused shared tests still pass (38). Authenticated inventory was zero before launch. The real `glm47-near-stock-c32-r3.service` began at `2026-07-15T23:59:52Z`, owns `computeinstance-e00cvg7rbk9p5dm59w`, and has passed provider create and SSH readiness into the pinned runtime bootstrap. The launcher’s 4,500-second deadline/watchdog remains the cleanup authority.

**Interpretation and next move.** The real session is active, not a result: no model load or throughput figure is yet available. Reconcile its control and FP8 artifacts plus final inventory after the durable owner terminates; do not start another provider operation.

## 2026-07-16 — r3 ownership snapshot

**Evidence.** One grouped read-only snapshot found `glm47-near-stock-c32-r3.service` active in the same cgroup with main PID `1226550`, owning only `computeinstance-e00cvg7rbk9p5dm59w` and disk `glm47-near-stock-c32-r3-boot`. The control events show 404.488 seconds for pinned runtime bootstrap, CUDA/Transformers preflight, successful transfer probe, and 20,193,158,555-byte checkpoint transfer in 355.610 seconds; the launcher then entered `scientific_workload` at `2026-07-16T00:14:10Z`. No control summary or FP8 artifact exists yet.

**Interpretation.** This is forward progress under the admitted durable owner, not a throughput result. Do not poll or mutate it; reconcile only after termination.

## 2026-07-16 — r3 still independently owned

**Evidence.** The single permitted grouped snapshot keeps `glm47-near-stock-c32-r3.service` active in its original cgroup with PID `1226550`, one matching instance, and one matching boot disk. The control remains in its launcher-owned `scientific_workload` phase; no summary, archive, or FP8 post-arm artifact has appeared.

**Interpretation.** There is no terminal result to reconcile and no authority to interfere before the launcher deadline/watchdog. Preserve the ownership state and reconcile on the next terminal observation.

## 2026-07-16 — r3 remains non-terminal

**Evidence.** One grouped snapshot again found the direct oneshot service active in its original cgroup with its sole matching instance and disk. No control archive/summary or FP8 post-arm artifact has been written; the last durable event remains control `scientific_workload`.

**Interpretation.** Preserve the independent owner and await its terminal cleanup/artifacts; the separate SM120 screen is outside this project.

## 2026-07-16 — director terminal classification

R3 produced a valid adjacent full-model BF16-KV control: c1/c8/c16 reached `56.611 / 360.608 / 552.171` conservative output tok/s with all rows successful. The retained FP8 arm never loaded the model because vLLM 0.15.0 rejected `fp8_e4m3fn` and listed `fp8_e4m3` as the accepted token. Its failure is operationally null, not negative FP8-KV evidence. Combined derived experimental exposure was `$0.723372253`; final cleanup passed at zero instances and zero disks. This project closes under its one-session stop rule, and the director delegated one corrected candidate-only successor.
