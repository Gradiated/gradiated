# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after the L40S owner closed on an exact-image entrypoint bootstrap error before checkpoint/model/request. Run direct SGLang BF16 plus FP8-E5M2-KV on the exact checkpoint and trace. The sequential matched-vLLM control is authorized only after `SGLANG_MARKET_TRIGGER`; otherwise clean up. Budgets: 130 wall minutes, 90 provider minutes, 1.5 H200-hours, 3 local CPU-hours, one 250-GiB disk, 12 GiB artifacts, and `$4.00`; one allocation and no paid repair.

## 2026-07-17 — durable H200 owner launched

Question: execute the admitted exact SGLang endpoint. Action: consumed the passing identity assertion, rendered `sglang_h200_owner.py`, and passed its 25-check final-program audit. The first systemd invocation failed before provider access because its service PATH lacked the Nebius CLI; it produced no resource. The corrected owner uses the absolute CLI path. It created RUNNING `computeinstance-e00b9yw90e93mwf2b0` (`gpu-h200-sxm`, `1gpu-16vcpu-200gb`, 250-GiB named disk) under `gemma-sglang-h200-20260717t101700z-owner.service`; its artifact root is `artifacts/gemma-sglang-h200-20260717t101700z-owner-run` and absolute deadline is epoch `1784288425.5182638`.

The owner's independent-watchdog health assertion did not complete, so the verified owner entered authenticated cleanup before any SSH, checkpoint transfer, model load, or request. This is not model/runtime evidence and no successor allocation is authorized. Reconcile `failure.json`, `cleanup.json`, and inventory next; the create diagnostic is retained at the artifact root.

## 2026-07-17 — director terminal reconciliation

The typed failure is local watchdog scope: a system-scope owner called the user-scope watchdog helper without `DBUS_SESSION_BUS_ADDRESS` or `XDG_RUNTIME_DIR`. Cleanup passed with zero instances/disks. Provider exposure from resource creation through verified cleanup was 110.627 seconds; derived compute plus disk cost was `$0.076034`; useful GPU seconds were zero. Close per the one-allocation rule. This is no SGLang, H200, FP8-KV, semantic, throughput, or quality evidence.
