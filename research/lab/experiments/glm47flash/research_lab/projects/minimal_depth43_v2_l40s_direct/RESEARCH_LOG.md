# Research log

## 2026-07-16 — Director opening handoff

- Parent result: depth42 is an architecture-cost pass at c16/c32 (`616.602/686.910` tok/s) but fails the development quality proxy; cleanup is complete.
- Candidate: nested 43 layers by restoring source block 42 and skipping `[6,15,24,33]`, retaining the final 13 source layers unchanged.
- Admission: before create, cleanly materialize and checksum-close the root and prove restored payload plus c32 KV keeps projected peak `<=44,532 MiB`; otherwise close at `$0`.
- Measurement: one create, exact c16/c32 8K/1K arms, absolute `594.466` gate, quality reported separately, `$1.00`/3,900-second cap, terminal cleanup.

## 2026-07-16 — depth43 admission and durable c16/c32 owner launched

- Restored source block 42 into the clean nested root `/root/.cache/glm47flash-awq-minimal-depth43-v2-5820e0c57965`; payload, index, no-symlink, MTP, and checksum closure passed. The exact c32 projection is `44,512.935 MiB` (`353.935 MiB` payload plus `288 MiB` KV over the measured depth42 peak), inside the `44,532 MiB` admission limit by `19.065 MiB`.
- Bound only this manifest/checksum identity into the shared local and remote validators. Focused tests (47), shell syntax, checksum hashing, and a no-mutation snapshot passed. The CPU/meta loader probe hit the known pipeline-group environment bound without candidate mutation.
- The first unit stopped before provider mutation because the shared local validator had not yet admitted the new exact root; its journal diagnostic was retained by systemd and inventory remained zero. One narrow identity correction was made and tested.
- Active owner: `glm47-minimal-depth43-v2-c16c32-20260716-r2.service` under user systemd, PID `1352734`, cgroup recorded in `STATUS.json.active_session`. Watchdog PID `1352917` owns instance `computeinstance-e00r6hz6ywseq74brt` and its boot disk through epoch `1784182941.1442761`; provider create passed in `51.693 s` and SSH readiness is in progress. Defer all terminal polling, transfer, load, and scientific reconciliation to the scheduled owner turn.

## 2026-07-16 — terminal QUALITY_PROXY_CLOSE

- Measured endpoint: all exact requests completed with semantic pass. c16 reached `600.704460` output tok/s in `54.549287 s` and c32 reached `636.469100` in `102.968078 s`; at the planning `$1.10/hour` these are `$0.508662/M` and `$0.480079/M`. Both clear the absolute `594.466` campaign gate and remain inside the 300-second background envelope.
- Quality boundary: the frozen development point screen scored the candidate `0/6` versus its carried control `2/6`, strictly worse than depth42's `1/6`; full quality remains unproven. Return `QUALITY_PROXY_CLOSE`, not a deployable or quality-adjusted result.
- Allocation/artifact: `1,263.034` allocation seconds, `157.517` useful GPU seconds, derived exposure `$0.30106605`, archive SHA-256 `8db63070ed174a9710f181e17d3cb747f9ca70b54775ee6eaf0bfa3beaad8120`. Cleanup passed with zero final instances and disks.
- Retention adjudication: create, SSH, bootstrap, and transfer consumed `838.036 s`, but this already-launched unit had no retained-session/post-recovery path or named trigger and its brief explicitly prohibited retention. Its summary records `retained_for_next_experiment=false`; normal cleanup was therefore required. The later depth44 memory-tax gate also closed, so no adjacent trigger survived.
