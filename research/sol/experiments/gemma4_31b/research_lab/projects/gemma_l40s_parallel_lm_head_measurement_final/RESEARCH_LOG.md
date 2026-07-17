# Research log

## 2026-07-17 — director delegation

Activated as the sole paid direct lane after the diagnostic-bearing predecessor proved its only failure was uppercase `T`/`Z` in `spec.hostname`. Reuse the already audited controller/program/wrapper byte-for-byte, prove the generated request name and hostname are lowercase RFC-1123, and launch once. Any terminal closes; no retained arm is compatible. Budgets are 45 wall minutes, 20 provider minutes, 0.34 L40S-hours, 1 CPU-hour, one 100-GiB disk, 2 GiB temporary/4 GiB artifacts, and `$0.50`.

## 2026-07-17 — one lowercase owner launched

Question: can the audited actual pinned-image six-row BF16 `ParallelLMHead` sweep reach the single authorized L40S after the deterministic lowercase correction? Action: exact-matched controller (`b29ab7…4cad`), benchmark (`de7f84…ab71`), and wrapper (`e7a947…c255`); the authenticated inventory contained zero instances/disks; and `artifacts/precreate-lowercase-20260717t065653z.json` mechanically recorded a matching lowercase RFC-1123 `--name`/`--hostname` (`gemma-l40s-head-final-20260717t065653z`, 38 characters) from the real create argv. Launched the unchanged shared controller once as durable user-systemd unit `gemma-l40s-head-final-20260717t065653z-owner.service` (PID 1915762, cgroup recorded in status), deadline `2026-07-17T07:57:38Z`, artifact root `artifacts/gemma-l40s-head-final-20260717t065653z/`. The controller creates its independent cleanup watchdog only after a provider instance binds. Interpretation: provider mutation has been submitted under the only authorized owner; do not poll, restart, or create another resource. Next move: terminal reconciliation must retrieve its typed artifacts and verify cleanup/inventory.

## 2026-07-17 — director terminal reconciliation

The unchanged actual `ParallelLMHead` passed all M=1/2/4/8/16/32 rows with finite zero-oracle outputs. CUDA p50 was 3.918944/3.928864/3.947456/3.980416/4.045664/4.451712 ms, mapping over 358 steps to 1.402982/0.703267/0.353297/0.178124/0.090522/0.049804 seconds per request. M=1 exceeds both total-request envelopes before any other model work; M>=2 does not, and c8-c32 retains the credible background-batching branch. The typed artifact records 1.401232476 useful GPU seconds, 681.499 provider seconds, `$0.143668052`, and verified zero instances/disks. Its `bandwidth_floor_ms` field is dimensionally overstated by 1,000x and is excluded from interpretation; measured CUDA/wall rows and budget translations remain valid. Project closed without retry.
