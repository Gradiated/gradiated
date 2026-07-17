# Student39 L40S sustainable lifecycle bound

## Question

Does the measured 39-layer c32 point remain below the campaign's `$0.514/M` output-token target after realistic background utilization, setup, retry, interruption, and session-amortization costs at the authoritative L40S planning rate?

## Why it matters

The exact student measured `734.557` output tok/s and `$0.415973/M` steady-state at `$1.10/L40S-hour`, but that 19.1% headline margin excludes lifecycle overhead. Recovery work is only valuable if a sustainable L40S operating envelope survives. The prior lifecycle project modeled the old 47-layer c16 point and strict provider comparator; it did not bind the physical student's c32 session, 64-request/89.218-second batch, corrected memory headroom, or the campaign's current `$0.514/M` objective.

## Fixed evidence

- Student archive: `../distilled_depth_student_architecture/artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02/`, summary SHA-256 `5b2c9f57573dd8f53024bcea7109c920781d78f603a2694bd154c490691bad89`, bundle SHA-256 `f9f3f77da53d30e87604d8a0f8c1ddd81e8bed65bab100896b06b5c6a7b35383`.
- c16/c24/c32 throughput is `674.424 / 661.661 / 734.557` output tok/s on exact cache-off 8,192-input/1,024-output requests. c32 completed 64 requests in 89.218 seconds; planning steady-state COGS is `$0.415973/M`.
- Planning L40S rate is `$1.10/hour`, with fresh production evidence range `$1.00–$1.25/hour`. Experimental accounting uses the actual provider-metered rate and must not replace the production base case.
- Reuse `../warm_checkpoint_lifecycle_bound/LIFECYCLE_MODEL_2026-07-15.json` and its calculator only as a method prior; do not transfer old checkpoint setup times silently.

## Scope

Run one `$0`, no-provider lifecycle falsifier. Reconstruct the exact student session's allocation, bootstrap, checkpoint staging, load, repair, useful c16/c24/c32 work, retrieval, and cleanup timelines from content-bound events and telemetry. Separate one-time research failures from a reproducible production lifecycle and report both. Use the measured c32 batch as the productive unit, then calculate sustainable `$ / M` over productive utilization, batches or hours per retained session, setup/reload frequency, idle retention, interruption/retry rates, orchestration, storage, and the full `$1.00–$1.25/hour` production rate range. Keep the workload's completion/reliability envelope explicit; latency is a tradeoff, not an inherited interactive rejection gate.

Report the minimum productive utilization and batches/session needed to beat `$0.514/M`, plus sensitivity at 5%, 10%, and 20% lifecycle overhead and at representative 2-, 8-, and 24-hour background sessions. Do not infer a warm-start mechanism, production quote, or quality result. Do not search prices, invoke a provider, edit the serving launcher, rerun throughput, or access the holdout.

## Portfolio decision

If the measured student remains below `$0.514/M` across a plausible background envelope at the planning base case and at least part of the production-rate range, preserve L40S as the recovery denominator. If it requires implausible near-perfect utilization or fails even at long sessions, close L40S as the eventual placement and make the completed RTX/A40 alternatives the post-quality placement priorities. Either result directly changes whether larger recovery spend is economically justified.

## Artifact contract

Produce `STUDENT39_L40S_LIFECYCLE_BOUND.json`, a reproducible calculator, and a concise `RESEARCH_LOG.md` with measured, derived, and inferred fields labeled separately.

## Available resources

Use the student archive, prior lifecycle model, fresh shared price inventory, campaign telemetry, and factory economics tools. Budget is `$0`; provider mutation is prohibited.
