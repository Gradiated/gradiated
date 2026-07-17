# Research log

No researcher turn has completed. The first action is the rendered pre-create contract audit in `PROJECT.md`; a passing audit proceeds directly to one durable L40S CUDA owner.

## 2026-07-17 — L40S owner reached typed provider-create blocker

Question: can the pinned Gemma 4 31B FP8 consumer reach one L40S and produce the pre-registered correctness/workload evidence?

Action: rendered the required path/concurrency/workload/telemetry/cleanup audit once. It passed, including an empty Nebius inventory and a c8 overlap fixture. Started durable systemd owner `gemma-fp8-l40s-owner-20260717t012541z.service` with artifact root `artifacts/gemma-fp8-l40s-20260717T012541Z/`, absolute deadline `1784258741`, and the shared `VerifiedRetainedOwner` cleanup primitive. The owner attempted its one authorized `gpu-l40s-a` create and the provider returned exit 3 before an instance identity or watchdog existed.

Evidence: the audit is `artifacts/gemma-fp8-l40s-20260717t/rendered-contract-audit.json`; `provider-create.json` preserves return code 3 and redacted stdout/stderr SHA-256 identities; `failure.json` is typed `PlacementError`; `cleanup.json` verifies zero matching and total instances/disks. A fresh inventory immediately after cleanup was empty. No CUDA consumer, model load, or FP8 output occurred.

Interpretation/next move: this is a typed external pre-create blocker with an observability limitation, not FP8 incompatibility evidence. Do not retry the exclusive paid allocation without a director decision; a future route must retain a bounded redacted provider-create diagnostic text before classifying provider behavior.

## 2026-07-17 — pool-d correction closes Nebius before CUDA

Question: can the independent catalog-valid pool d fix the pool-a pre-create path without changing the admitted FP8 experiment?

Action: reused the passing audit unchanged; verified only live `gpu-l40s-d` / `1gpu-16vcpu-96gb` catalog availability and empty instance/disk inventory (`artifacts/gemma-fp8-l40s-20260717T013144Z-pool-d-precreate.json`). Launched durable owner `gemma-fp8-l40s-owner-20260717t013157z.service`; it reached exactly one pool-d create with the same model/image/workload contract and captured a bounded sanitized provider diagnostic.

Evidence: Nebius returned `InvalidArgument` / exit 3 because the generated `spec.hostname` was invalid. No instance or disk was created, no watchdog was needed, and `cleanup.json` verifies zero matching and total resources. The sanitized diagnostic is `artifacts/gemma-fp8-l40s-20260717T013157Z/provider-create-diagnostic.json`; request and trace identifiers are redacted.

Interpretation/next move: this was a request-construction failure, not pool capacity or FP8 evidence. The director's explicit second-pre-GPU stop rule closes Nebius for this arm, so do not repair/retry here. The exact-market fallback may use this only as a typed Nebius request-validation blocker; no CUDA, correctness, throughput, or cost conclusion exists.

## 2026-07-17 — final lowercase pool-d owner active

Question: can the admitted FP8 owner pass Nebius request validation after correcting only the deterministic hostname defect?

Action: validated lowercase RFC-1123 name `gemma-fp8-l40s-20260717t013820z` and empty inventory in `artifacts/gemma-fp8-l40s-20260717t013820z-hostname-precreate.json`, then launched the unchanged audited pool-d owner. The grouped snapshot confirms owner PID/cgroup, instance `computeinstance-e00gy2yzmrw5wt71st`, boot disk `computedisk-e00awghabvzsc726xv`, deadline `1784259509`, and forward progress. The owner is still completing the provider create path, so an independent shared `placement_control.py watchdog` service is active against the known instance/disk.

Interpretation/next move: this is an executed paid experiment. Do not poll, replace, or create another allocation; reconcile only its typed terminal, artifacts, exposure, and cleanup on the next turn.

## 2026-07-17 — shared-transport pool-d owner active

Question: can the same audited FP8 science contract pass the previously proven campaign transport path after the raw SCP host-key failure?

Action: replaced only the project-local SCP invocation with shared `stock_control.scp_to`; the owner already uses shared `wait_ssh`/known-host refresh, `run_ssh`, `VerifiedRetainedOwner`, and the watchdog primitive. After empty inventory and narrow lifecycle checks, started `gemma-fp8-l40s-owner-20260717t014650z.service`. The grouped snapshot confirms owner PID/cgroup, instance `computeinstance-e00x4q0ny0ztjmntg4`, deadline `1784260010`, and active shared external watchdog `gemma-fp8-l40s-20260717t014650z-external-watchdog.service`.

Interpretation/next move: paid execution is active. Do not wait for transfer or load, poll science, or create another allocation. Reconcile this exact owner's typed terminal and cleanup later.
