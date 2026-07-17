# Decision — L40S saturation and sustainable-cost gate

Generated from `calculate_gate.py`; all numeric results are derived, not endpoint measurements.

## Gate result

At the L40S committed planning rate of `$1.10/GPU-hour`, the primary campaign hurdle requires **0.717 completed requests/s** for the cheapest captured exact endpoint in the planning-base scenario (85% service utilization, 1.10 replica/headroom factor, 1.05 non-GPU factor, 1.03 failure/reload factor, and 1.03 storage/orchestration factor). The corresponding load is 3,022 prompt tokens/s, 257 output tokens/s, or 3,278 total tokens/s. Across the captured exact endpoints and AA blend hurdle, the planning-base range is 0.606–0.717 request/s. The exact figure for each market endpoint and the `$1.00–$1.25/GPU-hour` production range is in `SATURATION_GATE.json`.

The ideal no-overhead floor is about 0.50 request/s; the conservative scenario is about 1.10 request/s for the cheapest measured campaign endpoint. Therefore a later GPU result clears the economic gate when completed throughput exceeds the hurdle for the observed rate and measured availability/overhead scenario. A c4 result can be accepted if it clears the same hurdle; c8 is not a prerequisite.

## Memory result

The conservative bound is 34.35 GiB weights/scales plus 5.0 GiB runtime reservation. Primary KV is 0.712 GiB per 4,214-token request. The resulting totals are:

| concurrency | conservative total | headroom vs 44.704 GiB | interpretation |
|---:|---:|---:|---|
| c1 | 40.062 GiB | 4.642 GiB | guaranteed-fit bound |
| c2 | 40.774 GiB | 3.930 GiB | guaranteed-fit bound |
| c4 | 42.198 GiB | 2.506 GiB | guaranteed-fit bound |
| c8 | 45.046 GiB | -0.342 GiB | outside conservative bound |
| c16 | 50.742 GiB | -6.038 GiB | outside conservative bound |

The 10K single-stream arm totals 40.504 GiB and has 4.20 GiB derived headroom, matching the source accounting. Thus `max_num_seqs=8` is **not guaranteed safe under the current conservative bound**; it is only a runtime-dependent possibility if actual allocator/workspace use is at least 0.342 GiB below the bound's implied envelope. The first paid owner remains unchanged and must measure this; this project does not launch or nominate a successor.

## Interpretation gate for paid artifacts

1. Check raw completed-request throughput, actual metered rate, concurrency, GPU memory, queueing, failures/reloads, and usable completion times.
2. Compute sustainable request cost as `metered_usd_per_hour / 3600 / completed_requests_per_second` multiplied by measured non-GPU, availability, replica/headroom, storage/orchestration, and utilization factors. Compare it against each target in `SATURATION_GATE.json`.
3. If c8 clears cost and memory telemetry is below 48 GiB with no reliability issue, retain c8 as the measured knee. If c8 misses the conservative memory bound but c4 clears cost, accept c4 as the fitting economic arm. If c4 misses but c1/c2 clears, retain the lower fitting concurrency if queue/completion time remains commercially usable.
4. If every fitting concurrency misses cost, do not reject L40S from throughput alone until memory and GPU/queue telemetry show whether the miss is saturation, underfill, or a non-GPU/availability burden. A later saturation arm is justified only by that measured evidence; this gate itself does not create one.

Completion time is secondary. For orientation, at the planning-base DeepInfra hurdle, Little's-law ceilings are about 1.4, 2.8, 5.6, 11.2, and 22.3 seconds at c1/c2/c4/c8/c16. These are p50/p95 sensitivity ceilings under the stated concurrency occupancy assumption, not hard SLOs; use observed p50 and p95 to judge commercial usability.

## Evidence boundary

Measured inputs are the captured market endpoint prices, model metadata, and fresh shared GPU price inventory. Memory and throughput surfaces are derived. No CUDA runtime, quality result, provider request, or production eligibility claim follows from this artifact.
