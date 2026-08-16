# Research log

## 2026-07-16 — Director opening handoff

- Decision: Use the free paid lane on the checksum-closed 42-layer v2 proxy, the campaign's smallest practical c32 model divergence after exact-model runtime/speculation closures.
- Exact candidate: `/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1`, contract `5dbf26dc16a1cabbdb36eb256a996a11cf44c71c702b72686806a68a3bb1a290`; the stale predecessor is prohibited.
- Measurement: one server, two complete cache-off 8K/1K batches each at c16 and c32; c32 primary; absolute pass `>=594.466` output tok/s within 300 seconds.
- Guardrail: `$1.00`, 3,900 seconds, one create, proven launcher/owner/watchdog, methodology off, terminal archive/spend/zero cleanup. No recovery or quality claim.

## 2026-07-16 — clean-v2 c16/c32 durable measurement launched

- Admission: bound only `/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1` to the shared local and remote allowlists, including its manifest (`cfee…cdda`) and checksum-list (`87d0…2950`) hashes; the stale predecessor is rejected. Focused validation passed 55 tests, shell syntax, exact payload hashing, and a before/after filesystem snapshot proving no candidate mutation.
- Correction: the initial direct service stopped before output creation or provider mutation because the shared frontier validator omitted the director-required `(16, 32)` pair. Recorded `artifacts/PRE_GPU_LAUNCH_CORRECTION_R1.json`, added that exact pair with a focused test (46 tests pass), and retained zero instances/disks before retrying.
- Handoff: sole owner `glm47-minimal-depth42-v2-c16c32-20260716-r2.service` is active under user systemd (PID `1339111`, recorded cgroup). Its independent watchdog PID `1339196` owns `computeinstance-e00h0n21gvh33xcev7` and boot disk `glm47-minimal-depth42-v2-c16c32-20260716-r2-boot` to epoch `1784180776.0359051`. The grouped snapshot recorded provider-create success (52.030 s) and subsequent SSH-readiness progress. Terminal reconciliation owns all later polling, artifacts, and cleanup.

## 2026-07-16 — retained-owner snapshot

- One grouped, non-blocking snapshot confirms the same active user-systemd owner (PID `1339111`, recorded cgroup), watchdog PID `1339196`, instance, disk, deadline, and artifact root. Forward progress is visible: SSH readiness completed in `44.604` seconds and `runtime_bootstrap` began at `2026-07-16T04:42:55.322430Z`.
- No launch, mutation, polling loop, or change to the session was made. Defer terminal reconciliation to the next scheduled owner turn.

## 2026-07-16 — Director terminal classification: ECONOMIC_PASS, quality failed

- Both exact cache-off arms completed: c16 delivered `616.602087` output tok/s in `53.142863` seconds and c32 delivered `686.910494` in `95.406899` seconds. Both are inside the campaign-authoritative 300-second background envelope and above `594.466`; at the `$1.10/hour` planning rate they are `$0.495547/M` and `$0.444826/M`. The inherited runner marks c32 `slo_pass=false`, but that stricter latency flag does not outrank the campaign envelope.
- c32 peaked at `43,871 MiB`; semantic determinism passed. The development quality screen failed with a multi-turn continuation regression and overall candidate score `1/6` versus `2/6`, so this is architecture-cost evidence only, not a quality-eligible or deployable result.
- Archive `ee0f3f3b…`, derived experimental exposure `$0.29131209`, and authenticated cleanup at zero instances/disks are complete. Provider ownership is released.
