# Research log

## 2026-07-16 — Director direct component handoff

FP8 MLA remains scientifically unresolved because earlier attempts never ran valid one-head split attention. After the live Marlin owner cleans to authenticated zero inventory, run one exact BF16-KV/FP8-KV component A/B on L40S through the supplied-script controller and the proven pullable v0.15.0 image. Require actual writer, stage-1, reduction, attention output/LSE, numerical, byte, resource, and p50/p95 evidence. One create, `$0.55`/1,800 seconds, no retry or retention; no preparation-only result.

## 2026-07-16 — L40S owner launched; terminal reconciliation deferred

Question: does exact one-head, paged four-split FP8-e4m3 KV attention beat matched BF16 on L40S while retaining output/LSE agreement?

Action: grouped preflight passed with zero Nebius instances/disks, a matching ephemeral SSH pair, unique name, controller SHA-256 `a29eb582…`, benchmark/spec SHA-256 `922618af…`, and the pullable v0.15.0 digest. The supplied `mla_microbench_control.py` was corrected from its conflicting v0.25.1 image pin and launched under user-systemd as `glm47-sm89-fp8-mla-v2-20260716.service`; the component benchmark performs a shuffled-page, one-KV-head BF16/FP8-e4m3 A/B with per-token scales, four partial reductions, output/LSE, bytes, numerical checks, and p50/p95 rows for B1/B8/B32 at the five frozen lengths.

Evidence: owner PID `1570670`, cgroup and systemd `RuntimeMaxSec=2100` are recorded in `STATUS.json.active_session`. The controller wrote `provider-request.json`; authenticated inventory identified L40S `computeinstance-e00fra6cqp83df3fmh` and its boot disk in `STARTING`. The controller create call was still in flight at the required one ownership snapshot, so its independent instance/disk watchdog will spawn on create return; systemd is already the absolute external watchdog.

Interpretation/next move: this is an executed paid owner, not readiness. Do not poll it this turn. On reschedule, reconcile the returned artifact/summary, numerical and performance gates, and zero-resource cleanup to emit the sole typed endpoint.

## 2026-07-16 — Director closes implementation before result promotion

The live owner remains exclusive, but the frozen script cannot produce the contracted evidence. Its wrapper passes an unsupported `--seed`; it uses eager gather/einsum rather than a bound FP8 kernel, duplicates one complete-attention timing as both stage-1 and full attention, omits tail masking and resource identity, undercounts a 1,152-wide FP8 backing allocation through a 576-wide view, and defines saturation so max-abs scaling maps at least one element to the forbidden boundary. Writer timing and elementwise tolerance are also absent. Therefore any self-reported pass is invalid, retention is false, and the endpoint is `IMPLEMENTATION_CLOSE_PENDING_CLEANUP`. Allow only the existing owner's cleanup; no repair, retry, or successor under this line.

Read-only reconciliation confirms the predicted pre-result failure: the controller recorded `StopIteration` at `2026-07-16T13:51:55.960945Z` and opened its generic 600-second repair window. Scored GPU science remains zero. This is not a repair authorization; the owner proceeds only to its bounded teardown.

## 2026-07-16 — Terminal cleanup reconciliation

The repair window expired without intervention, and the sole owner cleaned successfully at `2026-07-16T14:02:42Z`. The verified summary records `1,177.776 s` exposure, `$0.248288996` derived experimental cost, zero scored GPU seconds, artifact `19f2069b…`, and authenticated final inventory of zero instances and zero disks. Final result: `PRE_SCIENCE_IMPLEMENTATION_CLOSE`. This is neither FP8 performance nor numerical evidence; the line is terminal without retry or retention.
