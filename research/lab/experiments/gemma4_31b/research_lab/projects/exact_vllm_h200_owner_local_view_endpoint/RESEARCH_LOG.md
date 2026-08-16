# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after the corrected owner proved lifecycle/SSH but a cross-project transfer view disappeared before staging. Build and validate a zero-new-weight-byte run-local view inside the same durable user owner immediately before create, then execute the already corrected semantic-first vLLM program. SGLang remains conditional behind `VLLM_MARKET_TRIGGER`. Budgets: 130 wall minutes, 90 provider minutes, 1.5 H200-hours, 3 CPU-hours, one 250-GiB disk, 12 GiB artifacts, `$4.00`, one allocation, no paid repair.

## 2026-07-17 — durable owner launched

Question: can the exact corrected vLLM endpoint clear the H200 market gate when staging is content-bound inside its sole owner? Action: launched `gemma-vllm-lv-20260717t1336z.service`; PID 1995494 is the user-systemd main process in its own service cgroup. Evidence: the unique hardlink view passed immutable identity and is actively running shared `validate_local_files_cached`; the progress artifact observed 14.94 GB of storage reads against 62.58 GB. Interpretation: no provider mutation has occurred and create remains mechanically gated on the run-local terminal, actual rendered audit, authenticated empty inventory/rate/placement, and immediate recheck. Next: do not restart; the owner will proceed through the one allocation or emit a typed blocker.

## 2026-07-17 — director closes at typed pre-create terminal

The owner completed the full content validation and exited before provider mutation. Hardlinks, sizes, and the exact manifest pass. The terminal failed only because `validate_local_files_cached()` returns false when it successfully performs a fresh full hash and writes the marker, while the project treated that return as validation failure; it also expected the wrong file count even though shared staging correctly returned eight payload files plus `model-files.sha256`. Per the explicit new-pre-create-failure stop, close with `$0`, zero provider seconds, and zero useful GPU seconds. This is no model/runtime/hardware evidence.
