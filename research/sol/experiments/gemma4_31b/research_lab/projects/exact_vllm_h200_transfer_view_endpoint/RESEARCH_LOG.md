# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after the fixed-session owner passed user watchdog/create/SSH/remote ownership but pointed staging at a raw checkpoint without the required manifest. Bind the preexisting storage-free hardlink transfer view that already completed one full transfer. Local validation may use a bounded durable owner and gates provider create. Then run semantic-first exact vLLM; SGLang is conditional only behind `VLLM_MARKET_TRIGGER`. Budgets: 130 wall minutes, 90 provider minutes, 1.5 H200-hours, 3 CPU-hours, one 250-GiB disk, 12 GiB artifacts, `$4.00`, one allocation, no paid repair.

## 2026-07-17 — durable transfer-view integrity owner started

Question: whether the admitted storage-free hardlink view satisfies the shared staging consumer before any H200 provider mutation.

Action: consumed the passing director assertion and checkpoint terminal, then launched `gemma-transfer-view-integrity-20260717.service` as a user-systemd durable owner (`MainPID=1977524`, cgroup recorded in `STATUS.json`). It invokes the shared `session_staging.checkpoint_files()` and `validate_local_files_cached()` against `corrected-transfer-view`, checks every checkpoint payload inode/device against the materialization terminal, and atomically writes `artifacts/TRANSFER_VIEW_TERMINAL.json`.

Evidence: the view has `model-files.sha256` with the admitted manifest digest `e9da34db5ed8e7dce27e242088733cbf09ad489de451f8634b4afbe671a8f8b1`; it contains the two expected shards and exact ancillary files. The previous fixed owner’s typed failure was specifically the missing manifest at the raw checkpoint path, so no provider, engine, or hardware conclusion is implied.

Next: reconcile its typed terminal. On pass, bind the source fixed-session program to this view, run its actual final-program audit, then launch the single user-owner H200 endpoint. On failure, close as a typed no-provider pre-create blocker.

## 2026-07-17 — director consumes passing transfer-view terminal

The local owner completed successfully and is inactive. `TRANSFER_VIEW_TERMINAL.json` passes after 77.389 seconds over 62,578,655,922 bytes: nine files, exact manifest digest, hardlink identity, checkpoint/director assertion hashes, and the shared staging consumer all agree. No provider resource or spend exists. Provider launch is now unblocked; the next researcher consumes this terminal and may exit only after executing the final renderer/launcher into a durable endpoint owner or a new typed blocker.

## 2026-07-17 — admitted renderer executed to typed pre-create blocker

Question: can the prior fixed-session owner render and launch unchanged except for binding its checkpoint source to the passing corrected transfer view?

Action: bound the actual imported owner constant to `corrected-transfer-view`, consumed both passing terminals without reopening integrity, refreshed authenticated inventory/rate/capacity, and executed the actual lower remote renderer during the mandatory final-program audit.

Evidence: identity and transfer bindings all pass. Current authenticated H200 rate is `$2.45/hour`; fresh `eu-north1` advice reports eight preemptible one-H200 slots; before and after inventories contain zero instances and disks. The lower renderer deterministically raises `ValueError` because the embedded `trigger={...}` dictionary is not escaped inside `remote()`'s f-string. `artifacts/FINAL_PROGRAM_AUDIT.json` is the typed blocker. No create command ran, so provider exposure, spend, and useful GPU time are zero.

Interpretation/next: this is a pre-create renderer defect, not vLLM, H200, checkpoint, transfer, semantic, throughput, or economic evidence. The requested checkpoint-only mutation cannot launch until a director separately admits the one-line template-brace repair.

## 2026-07-17 — director admits one in-project lower-program correction

No allocation or spend was consumed, but the independent read-only audit rejects a brace-only repair. Correct the actual rendered program once: escape the trigger dictionary; run the proven Docker/NVIDIA-container host bootstrap; start the exact image with `--entrypoint vllm ... serve` and fail readiness immediately on container exit; avoid replaying semantic c1 into the scored cache baseline; preserve logs/metrics through an EXIT trap and non-`--rm` container; stop telemetry before atomic tar/checksum retrieval; retain ITL/per-token timing and provider/useful/cost accounting; and implement the real SGLang same-session branch behind every named trigger rather than hard-coding false. The final terminal must behaviorally inspect the rendered lower argv, single-c1 flow, traps/atomic retrieval, telemetry, user owner/watchdog, and executable conditional branch. Only a pass plus refreshed empty inventory/rate/placement authorizes the still-unconsumed sole allocation. A new typed pre-create failure or any paid pre-semantic failure closes.

## 2026-07-17 — corrected endpoint owner launched

Action: implemented only the admitted lower-program repairs. The rendered program now bootstraps Docker/NVIDIA-container support, uses an explicit diagnostic `nvidia-smi` entrypoint and `--entrypoint vllm ... serve`, stops immediately if the server container exits during readiness, executes semantic c1 once then `baseline_after_semantic` c4/c8/c16 plus 10K, records per-token arrivals/ITL, preserves telemetry/logs/metrics through an EXIT trap, atomically finalizes tar/checksum artifacts, and has a real BF16 SGLang FP8-E5M2-KV conditional branch.

Evidence: `artifacts/FINAL_PROGRAM_AUDIT.json` passes all 32 rendered behavioral/identity checks. Fresh `artifacts/PROVIDER_PREFLIGHT_FINAL.json` passed authenticated empty instance/disk inventory, `$2.45/hour` H200 rate, and fresh `eu-north1` preemptible capacity. The sole owner is running as user-systemd `gemma-vllm-transfer-20260717.service` (PID `1988826`, cgroup and deadline in `STATUS.json`); no second allocation is authorized.

Next: reconcile this owner only after it emits a typed endpoint outcome; retrieve and interpret the semantic and c1/c4/c8/c16/10K evidence, then evaluate the persisted SGLang trigger and verified cleanup.
