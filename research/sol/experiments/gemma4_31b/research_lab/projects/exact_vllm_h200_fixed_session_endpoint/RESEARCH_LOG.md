# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after SGLang closed on a local watchdog-scope failure before SSH. Reuse the exact rendered vLLM runner, passing checkpoint/trace, fixed shared session workspace, and proven user-service owner/watchdog. Run semantic-first vLLM c1/c4/c8/c16 plus separate 10K; SGLang is conditional only behind `VLLM_MARKET_TRIGGER`. Budgets: 130 wall minutes, 90 provider minutes, 1.5 H200-hours, 3 CPU-hours, one 250-GiB disk, 12 GiB artifacts, `$4.00`, one allocation, no paid repair.

## 2026-07-17 — user-scope fixed-session vLLM owner launched

Question: can the exact pinned BF16/vLLM endpoint reach the admitted semantic-first trace after the session-ownership correction? Action: consumed the passing 12-check director assertion and rendered `vllm_fixed_session_owner.py` around the shared `VerifiedRetainedOwner`, `session_staging.transfer_checkpoint`, and explicit user-manager watchdog. `FINAL_PROGRAM_AUDIT.json` passes all checks, including `sudo install -d -o glmrunner -g glmrunner` before transfer, explicit diagnostic entrypoint override, exact token arrays/barriers, semantic-first execution, telemetry, and the conditional SGLang trigger. The owner was launched as user service `gemma-vllm-fixed-20260717t10351784284530z-owner.service` (PID `1974599`, cgroup recorded in `STATUS.json`) with deadline epoch `1784289931.0389726`; the grouped launch snapshot observed its named H200 `computeinstance-e00zccekqsk6a32ag1` in reconciliation and the persisted `owner_started` event. Interpretation: this is executed retained work, not readiness. The owner creates the independent user-scope watchdog immediately after create reconciliation. Next move: defer reconciliation until its typed terminal/cleanup evidence; do not poll, restart, or create another allocation.

## 2026-07-17 — director terminal reconciliation

The user owner/watchdog, H200 create, SSH, and remote session-parent ownership all passed. Shared checkpoint staging then required local `checkpoint/model-files.sha256`, which the passing exact checkpoint terminal never created, and failed before transferring a byte, pulling the image, loading the model, or serving a request. Cleanup passed with zero instances/disks. Provider exposure was 131.544 seconds and derived compute plus disk cost was `$0.090411`; useful GPU seconds were zero. Close per the one-allocation rule. This is a local transfer-marker contract failure, not vLLM, H200, checkpoint, semantic, throughput, quality, or economic evidence.
