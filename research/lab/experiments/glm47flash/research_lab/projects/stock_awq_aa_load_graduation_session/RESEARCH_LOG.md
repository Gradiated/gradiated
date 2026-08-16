# Research log

## 2026-07-16 — Director opening handoff

- The old methodology route was setup-only; the shared stock launcher has since produced two valid exact GPU sessions, so execute rather than prepare.
- After c36 cleanup is authenticated zero, one durable owner runs all seven c1 rows, all seven 180-second load phases, and one exact internal c32 control under `$1.10`/4,200 seconds, then cleans normally.
- This can satisfy graduation gates 2 and 3 only. Quality gate 1 remains blocked by the unfrozen/unmaterialized holdout and missing BF16/AWQ paired evidence.

At `2026-07-16T12:00:33.903Z`, cleanup-only reconciliation authenticated zero instances and zero disks from the maxseq36 owner. The paid-lane precondition is satisfied; grouped checks and launch may proceed in the same researcher turn.

## 2026-07-16 — Durable methodology owner launched

- Question/action: execute the one-create gates-2/3 methodology session under the existing shared launcher, with seven AA-matched c1 rows, c1–c64 180-second load phases, one internal c32 control, complete telemetry, and normal cleanup.
- Grouped evidence: direct inventory was zero instances/zero disks; exact AWQ manifest was `e201edca…d0a86`; fresh L40S pricing reported measured `$0.8581222/hour` and planning `$1.10/hour`; matching SSH public key and all required local inputs were present; methodology and launcher focused tests passed (`1` and `42` tests). Launcher/runner/remote hashes are `19b7e59c…`, `8e7b63d3…`, and `29766910…`.
- Owner handoff: `glm47-stock-awq-aa-graduation-20260716-r1.service` under `systemd --user`, PID `1529503`, cgroup `/user.slice/user-0.slice/user@0.service/app.slice/glm47-stock-awq-aa-graduation-20260716-r1.service`, watchdog PID `1529966`, instance `computeinstance-e00f8crv3w1a2c19bt`, deadline epoch `1784207921.252`, artifact root `artifacts/l40s_stock_awq_aa_graduation_20260716_r1`. The owner reached `ssh_readiness` at `2026-07-16T12:08:39.354423Z`; no model/scientific terminal was polled.
- Next move: reconcile this sole owner’s archive, measured methodology/load/control result, exposure/spend, and authenticated cleanup on a later researcher turn. Do not launch another allocation or claim quality gate 1.

## 2026-07-16 — Director live contract correction

The owner passed create, SSH, and `410.617 s` bootstrap, then entered exact checkpoint transfer at `12:16:22Z`. Preserve it: the seven c1 rows and full c1–c64 load ladder remain decision-relevant. However, the launched command binds `max_num_seqs=8` and frontier `c1,c8`, while the preregistered internal control is c32. Do not mutate the live owner or weaken the contract after launch. At the endpoint, report methodology and c1/c8 evidence separately; absence of c32 prevents the project-level `AA_GATES_2_3_PASS`, even if methodology itself passes. Normal cleanup remains mandatory.

## 2026-07-16 — Director scientific-progress snapshot

Read-only evidence at `12:28:54Z` shows healthy forward science: exact transfer passed in `380.519 s` (`14/14`, `20,193,158,555` bytes, zero reuse), exact model identity/load completed, and the fixed cache-off c1 control completed `4/4` with `4,096` output tokens at `59.243 tok/s` and p95 TTFT `585 ms`. Fixed c8 was active at the snapshot; the AA methodology rows follow it and had not begun. Preserve the sole owner/watchdog through the `13:12:36Z` science deadline and `13:17:36.668784Z` cleanup deadline. The missing c32 contract defect remains unchanged; normal cleanup is mandatory.

## 2026-07-16 — Director methodology-progress snapshot

At `12:45Z`, the durable owner/watchdog and exactly one instance/disk remain healthy. Fixed c1 and c8 completed at `59.243/363.344 tok/s`. All seven unique methodology-matched single-stream rows pass 10,000 `o200k_base` input plus 1,500 server-output geometry, with median `50.835` post-first-token tok/s and `799 ms` TTFT. Full 180-second c1/c2/c4 load phases pass at `45.951/91.143/181.227 tok/s`; c8 is active and c16/c32/c64 remain pending. Preserve through archive and authenticated cleanup. The launch can never supply the required internal c32 control, and the legacy development-quality arm may make the outer controller fail; neither invalidates separately complete methodology rows. Setup before science is `895.963 s`, below intended scored work if the ladder finishes, so no retained follow-up is warranted.

## 2026-07-16 — Director terminal reconciliation

Classify the project `SCIENTIFIC_PARTIAL_INTERNAL_C32_CLOSE`. The frozen methodology completed all seven 10K/1.5K single-stream rows (median `50.835 tok/s`, `799 ms` TTFT) and the preregistered c1/c2/c4/c8/c16/c32 load curve at `45.951/91.143/181.227/352.199/312.787/255.713 tok/s`; the frozen two-adjacent-gains plateau rule validly stopped before c64. The project-level `AA_GATES_2_3_PASS` remains forbidden because the launch bound exact controls only at c1/c8 and never ran the mandatory exact 8K/1K c32 control. Preserve the methodology report and broad retained-allocation multi-arm evidence separately. The outer return code came from an inherited development-quality arm and does not invalidate those rows.

The verified archive contains 53 manifest files and hashes to `4acb3d3b78f115512baa86b10b8a5699475e1462da6542cb1f92ba9e54b0b5d4`. Exposure was `2,821.452 s`; derived compute plus disk cost is `$0.672541854`. The frozen summary counts only `114.232 s` of fixed-control useful GPU time, while artifact walls add `1,439.676 s` of methodology work, for `1,553.908 s` captured scored time. That exceeds `895.963 s` setup, so no retained adjacent arm was warranted. Cleanup passed in `61.085 s`; the unit/watchdog are absent and authenticated inventory is zero instances/disks. Do not retry for missing terminal artifacts.
