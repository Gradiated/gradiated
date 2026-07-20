# Exact v0.5.13 FP8+QKV residual profile and intervention

## Question

On the proven Gemma 4 31B v0.5.13 dynamic-FP8 plus QKV endpoint, what non-overlapping kernel/runtime boundary now dominates exact c32 service time, and can one source-justified change reduce endpoint time toward `<=0.6381105231 s/request`?

## Why this matters

The current stack is `0.6928421805 s/request`, while sustainable `$0.14/M` H200 economics at 90% utilization require another 7.90% reduction. Old BF16 attribution is not transferable: the current run averages 97.3% GPU utilization, 564 W, and about 123 GB HBM after dynamic FP8 and QKV fusion. Profiling alone is not a result; the same project must immediately test one change at the hottest measured boundary.

## Bound evidence and scope

- Exact model, runtime, representation, source bytes, and workload are fixed by `BINDINGS.json`.
- Use the authoritative reconciled QKV terminal only as prior evidence. Establish a fresh exact v0.5.13 FP8+QKV c32 control on H200 before judging the intervention.
- Attribute non-overlapping wall time across prefill/decode, FP8 linear families, attention/KV, normalization/activation, cache conversion/write, launch, synchronization, and scheduler gaps.
- Start with Nsight Systems or equivalent. Collect only the minimum Nsight Compute counters on the top one or two kernels needed to distinguish tensor-core compute, HBM/L2 traffic, occupancy/register/shared-memory pressure, underfilled grids, and synchronization.
- After attribution, implement exactly one source-justified intervention at the hottest boundary. Admissible classes include fused FP8 GEMM epilogues, activation/normalization fusion, attention/KV dataflow, launch elimination, or persistent execution. Do not optimize a boundary below 5% attributed relevance and do not run a flag sweep.

## Immediate experiment

After the harness durably reserves this project and the director registers one H200 bench, use one bounded durable owner to stage the exact checkpoint and pinned image. Run one profiled exact c32 FP8+QKV control, persist a non-overlapping attribution table and the minimum decisive counters, select and implement one intervention, then run one contemporaneous unprofiled control/candidate pair. Require 32/32 valid rows, exact token/cache accounting, FP8 consumer proof, QKV epilogue proof, and candidate-path invocation proof. Repair ordinary pre-invocation defects in place; do not replay a consumed arm.

## Decision rule

- Promote the candidate if it is semantically valid and `<=0.6381105231 s/request` against its contemporaneous control.
- Retain a stable simple gain of at least 5% even if it misses the full ceiling, then move to the next independently attributed bottleneck.
- Close the chosen boundary if its valid endpoint gain is below 5%, and return the attribution so the director can select a materially different route.

## Budgets and resources

- Researcher profile: `deep` for causal attribution through the first exact intervention result.
- Wall clock: 210 minutes.
- H200 claim: at most 135 minutes, plus 15 minutes reserved for retrieval and release.
- Compute: at most 2.25 H200 GPU-hours and 6 local CPU-hours.
- Storage: one 250-GiB boot disk; at most 20 GiB retained profiles and compact endpoint artifacts.
- Authorized spend: `$8.00`; one allocation only.
- Provider creation is forbidden until the reservation is durable and a director-registered bench exists.
