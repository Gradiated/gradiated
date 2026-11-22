# Inference experiment comparison template

Use with [inference-measurements-v2](measurement-standard-v2.md). Copy the planning fields into the existing experiment protocol and the result fields into its findings. Do not create a second numerical source of truth or fill placeholders with invented results. This template is not a runnable experiment or completed record.

## Plan before execution

- Experiment ID and question:
- Baseline and candidate identities, source/build/model pins:
- One intended change and fixed controls:
- Evidence type and authorised scope:
- Frozen workload ID/hash, per-case input/output counts, tokenizer, context, decoding/stopping:
- Batch size, concurrency, warm-ups, repetitions, run order, boots/sessions:
- Test tier: core circuit comparison, conditional diagnostic or baseline milestone:
- Workload length/classes and aggregate weights, natural vs fixed replay, reference readiness:
- For load tests: arrival process/seed, rates, queue/worker limits, admission/deadline/drain policy:
- Response targets, success fraction, queue-stability/lateness criteria, observation counts and percentile estimator:
- For cross-device work: same-model or service-quality contract, tokenizer and power boundaries:
- Start, first-output, last-output and completion boundaries, clock/resolution:
- Loading, transport, queuing, verification and logger inclusion/exclusion:
- Power boundary, sensor/cadence, idle state, integration/alignment and missing-sample policy:
- For the KV260 three-prompt comparison, specify the historical mixed block and the repeated single-prompt blocks. Report gross J/answer and J/output token for each prompt and for the mix, with paired variation or a coverage gap.
- Correctness/quality checks and acceptance thresholds:
- Primary question/metric, useful improvement and resource/energy trade-offs:
- Budget, timeout, stop rules and restoration responsibilities if applicable:
- Coverage below, including justified gaps and reused evidence:

## Required scorecard

Fill both arms. State is `measured`, `derived`, `reused`, `not_measured` or `not_applicable`. A plan says what will be collected. Only a completed record may claim it was measured. Missing core metrics must carry a reason and claim limitation. Reuse is for unchanged static evidence, not new dynamic observations.

| Coverage key | Unit | Baseline value/state | Candidate value/state | Change and variation | Evidence or gap reason |
| --- | --- | --- | --- | --- | --- |
| correctness | pass/fail and coverage | | | | |
| output_counts | input/output tokens and bytes, requests, stop reasons | | | | |
| ttft | ms | | | | |
| decode_tps | output tokens/s | | | | |
| completion_time | ms | | | | |
| active_power | W, named boundary | | | | |
| idle_power | W, matched ready state | | | | |
| energy_per_answer | J/answer, request or block average | | | | |
| tokens_per_joule | output tokens/J, gross energy | | | | |
| resources | LUT/FF/DSP/BRAM counts and %, or device equivalent | | | | |
| memory | weight/cache/buffer bytes, CPU separate | | | | |
| repeatability | counts, median/spread, failures/timeouts | | | | |
| operating_conditions | MHz, temperature °C, cooling, telemetry source | | | | |

## Conditional coverage

Identify the applicable rows and link measurements or explain gaps. One grouped reason can cover the unrelated rows, avoiding repetitive explanations or unnecessary instrumentation. Definitions and triggers are in the standard.

| Coverage key | Applies and why | Measurement/source or reason unavailable |
| --- | --- | --- |
| token_gaps | | |
| prefill | | |
| sustained_throughput | | |
| startup | | |
| cache_capacity | | |
| communication | | |
| stage_cycles | | |
| memory_bandwidth | | |
| implementation_timing | | |
| idle_subtracted_energy | | |
| long_stability | | |
| model_quality | | |
| physical_area | | |
| estimated_cost | | |
| workload_coverage | | |
| serving_load | | |
| client_delivery | | |
| recovery | | |
| cross_session | | |
| power_validation | | |
| cross_device_comparison | | |

Development effort: human attention, build/test elapsed time, available AI usage/cost, or explicit unknowns.

## Result and interpretation

- Run IDs and immutable `run.json` paths, with matching metric names/definitions across separate arm records:
- Raw artifact manifest paths/hashes and verified storage:
- Correctness/quality outcome, including failed cases:
- Main finding, baseline/candidate values, variation and scope:
- Offered/admitted/completed/rejected/failed/timed-out/unfinished counts and response-target goodput when applicable:
- Per-class and per-session distributions, queue/thermal/memory trends and censored observations:
- Per-case findings and aggregate formula, including failure handling:
- Changed resource/memory costs and implementation timing evidence:
- Missing measurements, unresolved variation and instrument limitations:
- Restoration/final state where applicable:
- What the evidence supports, and what remains unknown:

Before accepting the comparison, check every core entry and conditional trigger, verify reused evidence still matches, run the existing record validation, and review definitions, conditions and device settings manually. The comparison command does not establish equivalence of conditions or device configuration. Put changed measurement boundaries or verification treatment into new protocol/method identities. A valid JSON record alone does not establish measurement coverage. Keep completed records immutable. Any next experiment requires its own agreed plan.
