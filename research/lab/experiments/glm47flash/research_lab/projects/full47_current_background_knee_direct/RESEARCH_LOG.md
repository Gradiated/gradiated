# Research log

## 2026-07-16 — Director opening handoff

The exact unchanged-stock c32 endpoints span `596.852-609.606` tok/s while c36 collapses to `549.799`, leaving the current scheduling knee unidentified. After shared65 cleanup is independently authenticated zero, run one bracketed same-server sequence `(32,24,28,30,32)`, two complete waves per arm, under a durable systemd-main owner and independent watchdog. Promote only a stable best c24/c28/c30 at `>=606.355` and `>=1.03x` the c32-anchor mean; otherwise close. One create, `$0.60`/2,400 seconds, no retry or retention. If the literal packet and durable owner are not ready in the launch turn, close before create rather than returning readiness.

## 2026-07-16 — PRECREATE_CLOSE_SHARED65_NONZERO_INVENTORY

Question/action: apply the scheduled shared65 dependency check before freezing the literal `(32,24,28,30,32)` L40S packet or mutating the provider.

Evidence: the proven campaign controller's authenticated `list_items` query at `2026-07-16T14:43:15Z` returned the orphaned shared65 L40S instance `computeinstance-e00bwz6fs4z3sa3dme` (`glm47-shared65-20260716-r1`, `RUNNING`) and its managed boot disk `computedisk-e00rmrskbwp8wjst7w` (`READY`). The bounded snapshot is `artifacts/PRECREATE_SHARED65_INVENTORY_2026-07-16T144315Z.json`. The frozen checkpoint, launcher, and runner hashes were still exact, but cannot override the sole-owner prerequisite.

Interpretation/next move: `PRECREATE_CLOSE_SHARED65_NONZERO_INVENTORY`. No packet validation, durable service, provider create, or GPU science was started by this project (`0` useful/scored GPU seconds). The one-turn contract explicitly directs a pre-create close when authenticated zero is absent; reopening requires a fresh director admission rather than launching after this turn.

## 2026-07-16 — durable ordered-bracket owner launched

Question/action: directly re-admit the unchanged-stock scheduling-knee measurement after the director's authenticated shared65 cleanup, add the exact ordered bracket only, and launch the sole L40S owner.

Evidence: focused tests passed (`59` tests) after restricting the controller to `(32,24,28,30,32)` and binding runner identities `c32_pre,c24,c28,c30,c32_post`; every profile keeps `2*c` fixed-geometry requests. The frozen packet is `artifacts/l40s_background_knee_20260716_r1/LAUNCH_PACKET.json` (SHA-256 `2a1c0ddc892f13d8dfd9032aeee4a27106cbe813288262fc4e377e6b568322db`), with current launcher/runner/remote-wrapper hashes and the unchanged model-manifest hash. The durable owner is `glm47-background-knee-20260716-r1.service`, PID `1598757`, cgroup `/user.slice/user-0.slice/user@0.service/app.slice/glm47-background-knee-20260716-r1.service`, and `INVOCATION_ID=eb383a0e8ae349918a2e7ba516984808`. One grouped post-launch snapshot found `computeinstance-e00eqzrjfcjrs2v28v` STARTING on preemptible `gpu-l40s-a/1gpu-16vcpu-64gb` with disk `computedisk-e00qzwhc60svqmwf87`; `events.jsonl` records `stock_control` and `provider_create` start. The launcher now creates the independent `glm47-background-knee-20260716-r1-watchdog.service` directly after the provider-create subprocess returns.

Interpretation/next move: this is an executed durable experiment owner, not readiness. Return immediately without sleeping, checkpoint-transfer/model-load polling, or waiting for the scientific terminal; reconcile its archive, watchdog, and authenticated cleanup only on the later harness turn.

## 2026-07-16 — Cycle 130 fresh direct re-admission

Shared65 watchdog cleanup is independently authenticated at zero instances/disks as of `14:55:38Z`. The prior pre-create result used zero creates and produced zero science, so this director admission reactivates the same scientific project rather than creating a successor.

Source audit found the current shared launcher/runner cannot literally preserve duplicate bracket controls, and its detached watchdog remains inside the scientific service's control group. In this turn only, implement and focus-test exact `(32,24,28,30,32)` support with unique ordered identities `c32_pre,c24,c28,c30,c32_post`, two waves/`2*c` completions per arm, and a separately owned persistent systemd watchdog. Rehash/freeze and launch under a durable systemd-main scientific owner in the same turn or close locally. The original `$0.60`/2,400-second cap, economic/robust/stability gates, no-retry rule, and no-retention decision remain unchanged.

## 2026-07-16 — Director live admissibility audit

Preserve the owner: science PID `1598757` and watchdog PID `1599027` are active systemd mains in distinct cgroups, provider create and SSH passed, and runtime bootstrap is active. There is no scored or terminal evidence yet.

The frozen controller's generic background `PASS` is only a completion indicator; it does not implement the project's ordered profile/count/cache/histogram checks or the 3% anchor and dual throughput promotion gates. Do not mutate the live run. At terminal, manually admit raw evidence only if the archive proves exact ordered IDs/concurrencies, row counts `64/48/56/60/64`, 8K/1K token geometry and complete token IDs, every request within 300 seconds, zero prefix-cache deltas, semantic/histogram completeness, BF16 KV identity, telemetry, hashes, and independently authenticated cleanup. Then apply the frozen stability and throughput rules. The `2*c` work is one rolling arm per concurrency, not two barrier-separated repetitions. Ignore experimental-rate planning COGS in favor of the authoritative `$1.10/h` rate.

No adjacent retained follow-up is admissible: there is no distinct decision-relevant existing command ready within ten minutes, and prior split-8 uplift is only about `1.045%`. Clean normally. The watchdog unit may time out during worst-case deletion, so independently authenticate zero inventory even if it reports success.

## 2026-07-16 — Cycle 132 live checkpoint

Runtime bootstrap passed in `402.962 s`, CUDA/Transformers and the tiny-transfer probe passed, and exact checkpoint transfer began at `15:08:43Z`. At `15:11:27Z`, read-only inspection found `9,082,837,444 / 20,170,199,928` model bytes staged. Both systemd owners remain active and independent; the sole provider instance/disk are RUNNING/READY. GPU use is still idle, so useful/scored science remains zero. Derived exposure/cost is `653.304 s`/`$0.155726`, with deadline maximum about `$0.5721`. Preserve the owner; there is no result to adjudicate and no new retained or portfolio trigger.

## 2026-07-16 — Cycle 133 live checkpoint

Exact transfer passed with `14/14` files and `20,193,158,555` bytes in `347.699 s`. Model load completed at `15:18:38Z` in `31.10 s`; the exact compressed-tensors AWQ server is healthy with `42,491 MiB` resident, maxseq32/maxbatched65536, prefix cache disabled, and BF16 KV requested. Semantic and paired diagnostics completed: relative non-regression passes, while the inherited absolute point screen still fails its catastrophic-category gate. Preserve that as the unchanged-checkpoint quality claim limitation, not a scheduling failure.

The remote phase is now `conditional_semantic_quality_performance_batch`, but the timed runner had produced no rows or profiles at `15:18:52Z`; scored throughput remains zero. Both durable owners remain valid, exposure/cost is `1,066.174 s`/`$0.254141`, and the science/watchdog deadlines are `15:35:33/15:40:33Z`. Preserve unchanged; no terminal archive gate can yet be applied.

## 2026-07-16 — Terminal manual adjudication: `SCHEDULING_CLOSE`

The 49-file archive verifies at `94e2f841…d86dbf`. Every ordered profile has its exact ID/concurrency and row count (`64/48/56/60/64`), 8,192-input/1,024-output geometry, complete token IDs and 1,024-count histograms, success/length termination, zero prefix-cache deltas, and worst completion below 64 seconds. BF16 KV was requested through `auto` on the BF16 server identity; exact runtime/resource/telemetry evidence is retained. Controller generic background `PASS` is only completion evidence because it does not implement the project decision rule.

Measured output throughput is c32_pre `608.582948`, c24 `532.524371`, c28 `540.698935`, c30 `571.242407`, and c32_post `595.731293` tok/s. The c32 mean is `602.157121`, and anchor drift is `2.134269%`, passing the `3%` stability gate. Best candidate c30 is only `0.948660x` the anchor mean and misses both `606.355` and `620.221834` (`1.03x` mean). Return `SCHEDULING_CLOSE`; lower concurrency does not rescue the exact stock endpoint.

Useful GPU time is `523.606 s` in `1,644.534 s` exposure; derived compute/disk/total cost is `$0.387561758/$0.004441246/$0.392003003`. No retention ran. Controller cleanup passed, both systemd services are inactive, and a fresh independent provider query at `15:29:12Z` returned zero instances/disks. Do not repeat or sweep scheduling.
