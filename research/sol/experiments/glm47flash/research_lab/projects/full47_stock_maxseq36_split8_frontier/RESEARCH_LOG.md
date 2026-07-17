# Research log

## 2026-07-16 — Director opening handoff

- The verified stock c32 endpoint is an economic pass at `596.851973` tok/s but misses the robust boundary by `1.592%`.
- Exact measured KV capacity admits c36 by `1,712` tokens / `107` blocks, so measure c32 and c36 directly on one unchanged maxseq36 server.
- Retain only for valid four-split c36 in `[600.086,606.355)` and run one split-8 c36 through the existing retained path; every other result cleans immediately.

## 2026-07-16 — Durable frontier owner launched

- Question/action: bind the shared controller to maxseq36 c32/c36 and launch the sole L40S owner. Extended only its explicit frontier allowlist to `(32,36)` and `(36,)` and its CLI admission to `max_num_seqs=36`; the focused controller suite passed (`42` tests).
- Evidence: immutable stock archive remains `ff873b...27cb4c`; the exact model manifest was revalidated as `e201ed...d0a86`. `glm47-full47-stock-maxseq36-split8-r1.service` owns controller PID `1510087` in its systemd user cgroup, instance `computeinstance-e00vjb8na3b8gnz6yg`, and watchdog PID `1510614` through deadline epoch `1784204124.3343115`. Create passed in `63.440 s`; SSH readiness is in progress. Raw events and content hashes are under `artifacts/l40s_stock_maxseq36_split8_20260716_r1/`.
- Next move: reconcile this one owner only after it emits its four-split c32/c36 artifact. Run the retained `(36,)`/split-8 recovery only on the preregistered valid bridge trigger; otherwise verify cleanup.

## 2026-07-16 — Director disables the noncompliant retained arm

Read-only audit while r1 was in runtime bootstrap found that the launched command uses unconditional `--keep-instance-after-result`; no `[600.086,606.355)` evaluator or absolute follow-up command is bound. The cleanup watchdog is a child of the original `KillMode=control-group` unit and will die when that controller exits, while `vllm_recover_existing.py` does not create a replacement. The prose trigger therefore does not meet the required retained-session owner/watchdog contract.

Leave the live four-split c32/c36 measurement untouched. Disable split-8 for r1. After any endpoint, do not start recovery; if the controller retained the resource, reconcile it for immediate cleanup only and verify zero instance/disk inventory. This is an operational contract correction, not evidence about c36 or split count.

## 2026-07-16 — Director scientific-wrapper handoff

The sole owner passed runtime bootstrap and transferred all `14/14` exact files (`20,193,158,555` bytes, zero reuse) in `404.008/355.804` seconds after create/SSH. `scientific_workload` began at `11:49:53Z`; model load, c32, c36, throughput, and terminal retention remain unknown. Preserve the owner/watchdog. Split-8 stays disabled, and any retained endpoint is cleanup-only.

## 2026-07-16 — FRONTIER_CLOSE and cleanup

The exact four-split maxseq36 run produced a valid background endpoint. Same-session c32 completed `64/64` requests at `609.606365` output tok/s in `107.505439 s`; c36 completed `72/72` at `549.798962` output tok/s in `134.099926 s`. Both arms used exact 8,192-input/1,024-output geometry with prefix-cache zero deltas and passed the 300-second background envelope. C36 therefore missed the `594.466/606.355` economic/robust gates and regressed `9.811%` from the same-session c32 control. The c32 result exceeds robust, but its `2.137%` uplift over the prior `596.851973` run exposes run-to-run threshold variability rather than validating c36. The outer return code was the inherited interactive SLO only.

Archive `ee558a30c26861960a6242788d056d1e898a5365bb908edc431e68765d2662f3` contains 40 manifest files. Measured controller exposure/useful GPU time was `1,392.848/241.605 s`, with derived VM-plus-disk cost `$0.332009434`. The carried quality diagnostic remains claim-limited: relative paired non-regression passed, but the absolute point screen retained catastrophic-category failures.

The controller's unconditional keep retained instance `computeinstance-e00vjb8na3b8gnz6yg`; no recovery or split-8 arm ran. Cleanup-only deleted the retained instance and its managed disk, and an authenticated inventory check at `2026-07-16T12:00:33.903Z` found zero instances and zero disks (`cleanup_pass=true`, `instance_get_not_found=true`). This project is terminal as `FRONTIER_CLOSE`.
