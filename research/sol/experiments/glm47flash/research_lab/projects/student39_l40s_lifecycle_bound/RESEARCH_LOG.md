# Student39 L40S lifecycle bound — 2026-07-16

Question: does the measured 39-layer c32 point stay below `$0.514/M` once a real cold session, background utilization, and retry loss are charged at `$1.00–$1.25/L40S-hour`?

Action: reconstructed the content-bound retry/repair timeline and ran `lifecycle_bound.py`, a zero-provider deterministic model. The valid c32 path has `1,208.168 s` of cold lifecycle overhead: create, SSH, bootstrap, probe, 15.567-GB checkpoint transfer, repair input stage, derived model-load/compile/warmup, retrieval, and cleanup. The model-load component is the measured 550.535-second repair workload less the measured c16/c24/c32 profile walls. The first allocation (`983.374 s`, retrieval parser failure) and the retry's pre-repair unmaterialized workload (`867.074 s`) are retained as one-time research failures and excluded from the production model.

Evidence: measured c32 is `734.557` output tok/s, `65,536` output tokens in `89.218 s`, and `$0.415973/M` at `$1.10/hour`. The calculator uses `all_in = steady_state / (background_utilization × (1 - lifecycle/session) × (1 - retry_loss))`; no warm-start, recovery mechanism, production quote, or quality result is assumed.

Result: at 90% background productive utilization and 5% retry loss, all-in COGS is `$0.585/M`, `$0.508/M`, and `$0.493/M` at `$1.10/hour` for 2-, 8-, and 24-hour sessions respectively. The equivalent at `$1.00/hour` is `$0.531/M`, `$0.462/M`, `$0.449/M`; at `$1.25/hour` it is `$0.664/M`, `$0.577/M`, `$0.561/M`. At the `$1.10` base case, the minimum utilization is 97.25%, 84.47%, and 82.08% without retry, or infeasible, 88.92%, and 86.40% with 5% retry, across those three durations. A no-idle session needs 58 c32 batches with no retry or 78 with 5% loss. Generic 5/10/20% lifecycle fractions require 85.19/89.92/101.16% utilization at base rate without retry; therefore 20% lifecycle overhead cannot clear the target.

Decision: `PRESERVE_L40S_AS_CONDITIONAL_RECOVERY_DENOMINATOR`. The measured student is sustainable for a high-utilization 8–24 hour envelope at the `$1.10` planning rate and the `$1.00` low end, so recovery work can retain L40S as its denominator. It is not a robust placement at `$1.25/hour`, for short sessions, or with 20% lifecycle overhead; production placement needs a measured lifecycle reduction, near-saturation, or a lower committed rate.

Artifacts: `STUDENT39_L40S_LIFECYCLE_BOUND.json`; rerun with `python3 lifecycle_bound.py --out STUDENT39_L40S_LIFECYCLE_BOUND.json`.
