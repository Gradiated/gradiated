# Homogeneous H200 prefill/decode disaggregation bound

## Question

Can homogeneous H200 prefill/decode disaggregation lower sustainable cost per
request by at least 20% for the exact Gemma 4 31B background workload, at equal
GPU count and hourly price, without worsening p95 completion time at the same
offered load?

## Why this matters

The active DFlash experiment is the strongest direct GPU route, but its pinned
runtime is still building. The next independent literature-backed mechanism is
prefill/decode disaggregation. It is exact serving, but it adds KV transfer,
pool fragmentation, and an extra scheduling boundary; those costs can make it
economically negative even when each phase batches better. A calibrated
steady-state simulation can reject or nominate this topology before another
provider allocation.

This is materially different from the closed operation-overlap, persistent-KV,
native-NGRAM, and static multi-token graph lines. It changes fleet scheduling
and phase placement, not model arithmetic or token semantics.

Use `$experiment-run` and consume `DIRECTOR_BINDING.json`.

## Bound experiment

Build one content-addressed discrete-event simulator for repeated exact-workload
traffic:

- model `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`;
- 4,214 prompt tokens, 358 output tokens, 12.6958% cached prompt tokens, and
  temperature-zero non-reasoning text;
- the measured c32 tied-head endpoint is the authoritative monolithic
  comparator: 32 requests in `20.8585050230 s`, or
  `0.6518282820 s/request`;
- the older scope-matched Nsight and request-phase artifacts are phase-shape
  evidence only. Recalibrate their total work to the authoritative endpoint;
  do not claim a direct delta across those runtime iterations;
- use homogeneous H200 pools at the shared committed planning rate. Compare
  disaggregated and monolithic service with the same total number of GPUs and
  the same headroom policy;
- include request admission, prefill and decode batching, KV transfer bytes and
  latency, queueing, pipeline bubbles, failures/reloads as explicit sensitivity,
  and replicas/headroom. Do not assume zero transfer or perfect batching;
- evaluate at least 8-GPU and 16-GPU fleets over offered load from 50% through
  the highest stable utilization. Keep the fixed workload primary and report
  the 10K-input Artificial Analysis geometry separately as a sensitivity.

First reproduce the measured monolithic c32 batch within 1% when configured as
one saturated worker. Then compare Pareto surfaces for cost per completed
request, throughput, TTFT, and p95 completion time.

## Decision

Nominate exactly one prefill:decode allocation and offered-load point for a
later paid experiment only if all of the following hold under conservative
transfer and headroom assumptions:

- at least 20% lower cost per completed request than the calibrated monolithic
  fleet at the same offered load;
- no worse p95 completion time;
- stable queues and at least 99% completed requests;
- the result remains positive across the preregistered uncertainty envelope,
  not only at an optimistic point estimate.

Otherwise close homogeneous H200 disaggregation for this workload. A topology
nomination is not a production or quality claim.

## Resources and limits

- Profile: `execution`.
- Spend: `$0`.
- Compute: at most 2 local CPU-hours.
- Wall clock: at most 90 minutes from researcher start.
- Storage: at most 1 GiB project-local.
- Artifacts: simulator source and tests, content manifest, calibrated inputs,
  scenario table, Pareto summary, terminal decision, and uncertainty labels.
- Provider mutation and GPU claims are forbidden.
- Do not inspect, wait for, restart, or modify the active DFlash owner or its
  independent H200.
