# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after the L40S owner closed on an exact-image entrypoint bootstrap error before checkpoint/model/request. Run direct SGLang BF16 plus FP8-E5M2-KV on the exact checkpoint and trace. The sequential matched-vLLM control is authorized only after `SGLANG_MARKET_TRIGGER`; otherwise clean up. Budgets: 130 wall minutes, 90 provider minutes, 1.5 H200-hours, 3 local CPU-hours, one 250-GiB disk, 12 GiB artifacts, and `$4.00`; one allocation and no paid repair.

## 2026-07-17 — durable H200 owner launched

Question: execute the admitted exact SGLang endpoint. Action: consumed the passing identity assertion, rendered `sglang_h200_owner.py`, and passed its 25-check final-program audit. The first systemd invocation failed before provider access because its service PATH lacked the Nebius CLI; it produced no resource. The corrected owner uses the absolute CLI path. It created RUNNING `computeinstance-e00b9yw90e93mwf2b0` (`gpu-h200-sxm`, `1gpu-16vcpu-200gb`, 250-GiB named disk) under `gemma-sglang-h200-20260717t101700z-owner.service`; its artifact root is `artifacts/gemma-sglang-h200-20260717t101700z-owner-run` and absolute deadline is epoch `1784288425.5182638`.

The owner's independent-watchdog health assertion did not complete, so the verified owner entered authenticated cleanup before any SSH, checkpoint transfer, model load, or request. This is not model/runtime evidence and no successor allocation is authorized. Reconcile `failure.json`, `cleanup.json`, and inventory next; the create diagnostic is retained at the artifact root.

## 2026-07-17 — director terminal reconciliation

The typed failure is local watchdog scope: a system-scope owner called the user-scope watchdog helper without `DBUS_SESSION_BUS_ADDRESS` or `XDG_RUNTIME_DIR`. Cleanup passed with zero instances/disks. Provider exposure from resource creation through verified cleanup was 110.627 seconds; derived compute plus disk cost was `$0.076034`; useful GPU seconds were zero. Close per the one-allocation rule. This is no SGLang, H200, FP8-KV, semantic, throughput, or quality evidence.

## 2026-07-18 — director reactivation on corrected retained lifecycle

- Rationale: the prior allocation failed before SSH solely on a watchdog-scope defect. A separate corrected H200 lifecycle has since demonstrated create reconciliation, transfer, image launch, retrievable diagnostics, model loading, a real 600-second retained repair context, and authenticated cleanup. No prior SGLang/H200 science exists to preserve or falsify.
- Evidence: `BINDINGS.json` mechanically binds the exact checkpoint/runtime/trace, strict H200 economic gate, measured c32 BF16 component floor, and corrected owner implementation/regression. The c32 component floor is `0.22476958992984145 s/request` versus the strict `0.47201182295214134` endpoint ceiling; c16 is omitted because it leaves only about 30 ms for all residual work.
- Decision: reactivate this same scientific project at execution profile for one retained c32-first SGLang BF16/FP8-E5M2-KV endpoint owner. Limits are 120 wall minutes, 80 provider minutes, 1.34 H200-hours, one 250-GiB disk, and `$3.75`; the 10K view is conditional on valid c32 and at least 20 provider minutes remaining.

## 2026-07-18 — retained SGLang c32 development owner launched

All seven `BINDINGS.json` digests, the bound corrected-owner regression, the local retained-owner regression, and authenticated empty inventory passed. `gemma-sglang-h200-c32-20260718t031200z-owner.service` (user systemd, PID 2280803) created RUNNING H200 `computeinstance-e00mcm2qt1zmxsgxgh` with its named 250-GiB disk and independent user-scope watchdog. Artifact root: `artifacts/gemma-sglang-h200-c32-20260718t031200z-owner`; deadline epoch: `1784347890.5321448`. The c32 runner retains exact token arrays by duplicating the trace’s c16 rows without retokenization; it will execute the 10K view only after valid c32 with a 20-minute reserve. Attach and repair ordinary first-call faults in this allocation.

## 2026-07-18 — retained transfer repair

The owner’s first direct `scp` lacked the shared host-key options and returned 255 without retaining stderr, an observability defect. A direct retry through the established authenticated SFTP path reached the same `glmrunner` workspace and is making sustained progress on the first 49.78-GB shard. The original 600-second repair context is shorter than this size-bound transfer, so its owner process is SIGSTOP-paused while the instance, disk, user-scope watchdog, and transfer remain live; no allocation was replaced. The source now uses the shared `StrictHostKeyChecking=accept-new` and project known-hosts options for future owner invocations. Next: wait for all bound files, verify the remote index hash, then start the bound SGLang program on this resident allocation.

The first retry client disappeared with an incomplete 13.2-GB remote shard and no preserved stderr. The replacement transport is `gemma-sglang-h200-c32-20260718t031200z-transfer.service` (user systemd, PID 2285495), which re-stages all eight files under the same H200 deadline and artifact contract. This is transport repair only.

## 2026-07-18 — director terminal reconciliation

- Result: the original owner reached its absolute watchdog with `checkpoint_transfer_failed`; no image load, SGLang model load, c32 request, output, telemetry bundle, or economic row exists. `cleanup.json` authenticates zero matching/final instances and disks.
- Accounting: provider creation at `02:51:31.234081Z` through verified cleanup at `06:05:13.127693Z` is 11,621.894 seconds (193.698 minutes), versus the 80-minute project limit. Compute alone is about `$7.909344264` at the bound `$2.45/H200-hour`, before disk, versus `$3.75` authorized.
- Interpretation: close SGLang H200 as an over-budget transport failure with no SGLang, BF16, FP8-KV, c32, endpoint, output, throughput, or economic inference. Do not allocate this route again.

The first retry client disappeared with an incomplete 13.2-GB remote shard and no preserved stderr. The replacement transport is `gemma-sglang-h200-c32-20260718t031200z-transfer.service` (user systemd, PID 2285495), which re-stages all eight files under the same H200 deadline and artifact contract. This is transport repair only.
