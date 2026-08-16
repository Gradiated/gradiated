# Student39 L40S production all-in gate

## Question

Can a real 12–24 month L40S production topology—including CPU, RAM, disk, networking, orchestration, and restart semantics—fit the narrow hourly-rate and reliability envelope required for the recovered 39-layer c32 point to remain below `$0.514/M`?

## Why it matters

The completed lifecycle bound validates the throughput arithmetic but shows that L40S is only conditional. At `$1.10/GPU-hour`, 90% background utilization, and 5% retry loss, c32 is `$0.507821/M` over 8 hours and `$0.493418/M` over 24 hours. The total all-in hourly caps are only `$1.113384` and `$1.145885`; one additional cold reload makes the 8-hour case fail at `$0.531075/M`. The shared planning rate is GPU-only/derived, so the campaign does not yet know whether ancillary topology costs and restart behavior consume the margin.

## Fixed evidence

- Use `../student39_l40s_lifecycle_bound/STUDENT39_L40S_LIFECYCLE_BOUND.json` and its measured `1,208.168`-second cold lifecycle. Do not rerun or remodel generic lifecycle scenarios.
- Use the authoritative `$1.10/hour` L40S planning base and `$1.00–$1.25/hour` range from the fresh shared price inventory. Do not perform another general GPU-price search.
- Preserve exact student c32 throughput `734.557` output tok/s, the cache-off 8,192-input/1,024-output workload, 64-request/89.218-second productive unit, 90% utilization, 5% retry reference, and `$0.514/M` target.
- Quality remains conditional on recovery; this project evaluates placement economics only.

## Scope

Run one `$0`, no-provider-mutation topology gate. Seek only current content-bound public committed terms, existing quote artifacts, or an explicitly available written quote for an 8–64-GPU L40S deployment. Bind what the quoted GPU rate includes and separately account for the minimum CPU, RAM, boot/model storage, network/egress, orchestration/control, and any mandatory support or reservation charges. Bind interruption/SLA, replacement, restart, billing-minimum, and storage-persistence semantics strongly enough to decide whether one or two cold lifecycles belong in an 8- or 24-hour background session.

Do not contact a vendor, log in, accept terms, request a private quote, create a resource, refresh unrelated accelerator prices, or infer missing costs as zero. If no public or already-available content-bound topology rate exists, return an explicit unbound result rather than broad market research. Separate production committed pricing from experimental/preemptible rates.

## Decision contract

For the 90%-utilization/5%-loss reference, preserve an 8-hour L40S placement only if total all-in rate is at most `$1.113384/hour` and restart evidence supports one cold lifecycle; preserve the 24-hour placement only if total rate is at most `$1.145885/hour` under the bound restart count. A rate above the relevant cap, an extra restart that pushes COGS over `$0.514/M`, or materially unpriced mandatory components closes that production envelope while leaving the measured architecture and alternative-hardware mechanisms intact.

The result changes the next portfolio step: a pass preserves L40S as the post-recovery qualification venue; a fail makes cheaper A40/RTX-class placement evidence the production priority after quality recovery. It does not authorize a long reliability run.

## Artifact contract

Produce `STUDENT39_L40S_ALL_IN_GATE.json`, a minimal reproducible calculator or bound, and a concise `RESEARCH_LOG.md`, labeling rates as measured, quoted, public, derived, inferred, or unbound.

## Available resources

Use the completed lifecycle project, shared fresh price inventory, campaign provider artifacts, and factory economics tools. Budget is `$0`; provider mutation and external communication are prohibited.
