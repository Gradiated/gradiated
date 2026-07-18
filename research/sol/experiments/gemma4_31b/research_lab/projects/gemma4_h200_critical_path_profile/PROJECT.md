# Gemma 4 H200 critical-path profile

## Question

Where does whole-request wall time go for the exact Gemma 4 31B checkpoint on the measured H200 SGLang path, and which concrete source/kernel boundary offers the largest quality-preserving cost reduction?

## Why it matters

The stock H200 c32 result is economically close but has insufficient margin. Existing component bounds do not explain the full `0.363303 s/request` result well enough to choose architecture, kernel, scheduler, or placement changes. The retained H200 already has the exact checkpoint and pinned image, so profiling can reach evidence without another transfer.

## Work

Claim the retained H200 bench. Reproduce the exact 4,214/358 background workload at useful c16/c32 geometry and preserve the separate 10K single-stream view. Capture bounded request/GPU timelines and the smallest useful Nsight or framework counters to attribute prefill, decode, linears, hybrid local/global attention and KV traffic, tied head, launch/synchronization, scheduler/queueing, HBM/L2 behavior, utilization, and power. Use existing artifacts rather than replaying setup. If full endpoint profiling stalls after one material repair, switch to the shortest exact-shape discriminator for the suspected dominant boundary.

Return a measured critical-path decomposition, causal source/chip explanation, and at most three ranked interventions. Run the cheapest discriminating performance arm when it fits the session. No generic quality suite; require only valid nonempty output and numerical sanity sufficient to reject a broken measurement.

## Limits

55 wall minutes, 45 retained-H200 minutes, `$2.25`, 4 local CPU-hours, and 3 GiB retained artifacts. Preserve the bench and release without teardown.
