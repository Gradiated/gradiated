# Inference measurement standard

Standard ID: `inference-measurements-v2`, prepared 16 November 2026.

This version extends the unchanged [version 1](measurement-standard.md) with baseline milestone coverage and explicit serving-load, workload-diversity, recovery and cross-device contracts. Use v2 for newly prepared protocols. Earlier protocols and results retain their recorded v1 identity and meaning. Preparation and local synthetic harness checks do not authorise model inference, simulation, circuit builds or physical execution.

Use this standard for new experiment plans and result comparisons. It extends the [experiment contract](README.md), [run schema](../schemas/run.schema.json) and existing artifact storage. Use the [comparison template](comparison-template.md) to plan coverage before execution and present findings afterwards. This standard does not authorise experiments, choose their order or require a new baseline programme.

Completed protocols and run records remain immutable. Existing results are valid within their recorded scope. Do not rename their metrics, infer missing timestamps or recalculate them under a different boundary without a separately identified derived record and explicit source references.

## What is required

Every experiment must identify its question, baseline, changed variable, fixed controls, evidence type, correctness/quality gate, repetition plan, budget, stop rules and coverage of the scorecard below. Record unsuccessful and inconclusive outcomes too.

For each new **physical inference comparison**, collect the core timing, output, reliability and power/energy measurements for both arms. Include resource and memory evidence for each implementation. An unavailable measurement needs an explicit reason and limits the claims we can make. A missing power measurement, for example, permits a latency result but no measured energy-efficiency claim. Do not let optional instrumentation become a prerequisite for every experiment.

For software-reference tests, RTL simulations, build-only runs and component experiments, use the same coverage sheet but mark physical or complete-model metrics not applicable, with a reason. Measure the component's relevant behaviour and do not present it as complete-request performance. A build report is not measured board speed.

Each coverage entry uses one of these states:

| State | Meaning |
| --- | --- |
| `measured` | Observations collected for this run, with samples and method. |
| `derived` | Calculated from identified observations using a recorded formula and boundary. |
| `reused` | Unchanged static evidence, with its source, hash and reason for applicability. |
| `not_measured` | Applicable but unavailable, with the reason and resulting claim limitation. |
| `not_applicable` | Does not apply to this experiment or evidence type, with the reason. |

Never encode missing data as zero. A genuine zero, such as zero failures, is an observation. Dynamic timing, power and temperature observations cannot be reused as new measurements. Historical baseline results remain useful, but new comparisons should include a bounded matched control under the new run conditions. Do not repeat the whole baseline programme or keep repeating until a preferred threshold passes.

## Core scorecard for physical inference comparisons

The keys below identify coverage families. For separate baseline and candidate records, use identical metric names, units, kinds and methods for comparable quantities, since `records.py compare` matches by name. Put arm identity in the record ID and `conditions`. Use matching case/boundary suffixes where needed. A combined record may use arm-specific metric names, with the pairing made explicit in its findings.

| Coverage key | Human-readable result | Requirement |
| --- | --- | --- |
| `correctness` | Correct answers | Exact-reference checks for unchanged arithmetic, plus their coverage and failures. A precision/model change also requires a separately agreed model-quality gate. |
| `output_counts` | Work completed | Input tokens/bytes, generated output tokens/bytes, completed requests and stop reasons per case. Exclude prompt tokens and special end markers from useful output counts. |
| `ttft` | Time to first token, ms | Measure the declared request-start event to delivery of the first useful output token at the declared boundary. |
| `decode_tps` | Generation speed, tokens/s | Measure output after the first token using the definition below. Keep it separate from input processing and whole-workload throughput. |
| `completion_time` | Complete-answer time, ms | Measure the declared request-start event to completion signalling, including stopping work. Report correctness-checking overhead separately. |
| `active_power` | Average active power, W | Measure over the declared request or workload interval at the named power boundary. |
| `idle_power` | Ready-but-idle power, W | Measure a matched idle interval with the same loaded model, circuit, power configuration and logger setting. Record cache state and settling. |
| `energy_per_answer` | Energy per answer, J | Integrate measured power over the declared interval. Label individual-request values and multi-request block averages distinctly. |
| `tokens_per_joule` | Energy efficiency, tokens/J | Divide useful generated output count by gross energy over that same interval, including input-processing energy. |
| `resources` | Circuit resources, counts and % | For FPGA implementations, report LUTs, registers, DSPs and block RAM separately, with device capacity and report identity. Reuse the exact build report for an unchanged circuit. Other devices use relevant resource evidence or an explained not-applicable entry. |
| `memory` | Memory footprint and capacity, bytes | Identify weights, allocated KV cache, valid cache contents at the tested lengths and working buffers. Separate accelerator and CPU memory. Reuse unchanged static accounting, but establish any changed allocation or peak usage. |
| `repeatability` | Variation and failures | Preserve individual observations, request/run counts, run order, median and spread, errors, timeouts and incomplete requests. State how warm-ups and failures affect each summary. |
| `operating_conditions` | Clock and temperature | Record configured and available reported clocks, their source, cooling and start/end/max observed temperatures with sensor/sample cadence. Missing telemetry must be explicit. A reported clock is not proof of a constant measured clock. |

No single FPGA utilisation percentage represents all circuitry. Do not convert LUT/DSP/BRAM percentages into physical silicon area. Report mm² only with a defensible source and mapping, as a separate estimate or measurement.

## When to run the broader tests

The core scorecard above remains required for each physical inference comparison. Use the conditional measurements when the intervention or claim calls for them. A small isolated circuit change does not require the whole benchmark suite.

A **baseline milestone** is a separately planned characterisation of a selected model and implementation. It adds prompt/context coverage, offered-load behaviour, longer repeatability and independent-session replication. Perform it when establishing a baseline for broader performance claims, before publishing serving-capacity claims, or after a change likely to alter those behaviours. Selecting a circuit baseline does not imply these tests passed. Record coverage as pending until measured. Reuse prior milestone evidence only as historical evidence, with the exact version and scope. Repeat affected families when scheduling, cache handling, memory allocation, interfaces or arithmetic behaviour changes.

The [benchmark roadmap](benchmark-roadmap.md) distinguishes prepared work, future tests and unavailable measurements. Freeze a bounded protocol and workload before each execution. A diagnostic smoke test, a longer stability test and a capacity sweep are distinct workloads and must not be pooled as one result.

## Timing and counting definitions

Use a monotonic clock and record its resolution and instrumentation. Define the measurement boundary before the run, such as board-side request acceptance and CPU-visible output, or client submission and client-visible output. Record whether input encoding, queuing, transfers, buffering and verification are included. Compare matching boundaries. Client/laptop transport is a separate measurement when it is outside the core boundary.

Let `t0` be the protocol’s declared request-start event, `t1` delivery of the first useful output token at its declared observation point, `tN` delivery of the last useful output token, `tdone` completion signalling and `N` the useful generated-token count. For the board-side boundary, `t0` can be acceptance of prepared input. Client submission may precede encoding, transport and queuing, so these are different boundaries. Prior KV260 first-output observations at board-side byte selection must not be relabelled as client delivery. Define the corresponding timestamps explicitly:

- TTFT = `t1 - t0`.
- Decode TPS = `(N - 1) / (tN - t1)`, with time in seconds. It is undefined for fewer than two output tokens or unresolved/non-positive elapsed time. Record the reason, not zero or infinity.
- Complete-answer time = `tdone - t0`. It includes input processing and stopping, but excludes model/circuit loading unless the protocol explicitly measures a cold start.
- Time between tokens = successive delivery timestamp differences. It requires individual delivery timestamps. TTFT and the last-token timestamp alone do not establish the distribution of gaps.
- Sustained throughput = total useful output tokens / full measured workload time, including input processing, request gaps and stopping. Requests/s uses completed requests over that same window. Neither is decode TPS.

For zero-output cases, TTFT is undefined and completion time remains meaningful. An undefined metric on a valid short/EOS completion is not a failed measurement. Record EOS, limits, cancellation or failure explicitly. If an interface returns the whole answer at once, do not invent streamed token timings from internal compute timestamps. Report the actual delivery behaviour and label internal timings separately.

For `chip-joke-text-20261109`, ordinary output tokens represent bytes, so output tokens/s equals output bytes/s when special markers are excluded. Input hex encoding has a different count. Across other models, pin the tokenizer and output counts, and do not rank unlike tokenizers by TPS or TPJ alone.

Freeze case selection before optimisation. Preserve the historical three-prompt aggregate as its own workload. Additional cases need a new workload identity and results by case/length. Natural completions assess the application. Fixed-length, forced-sequence or equal-window tests isolate context effects and must be labelled as distinct workloads, with their own exact references.

## Power and energy definitions

Always name the electrical boundary, sensor, units/scaling, sampling interval, timestamps, alignment method, resolution and available accuracy information. Preserve power samples and workload markers. Record missed samples and the integration/gap policy, and assess sensitivity to time alignment when material. Never substitute a rated power figure for measured inference energy.

- Gross energy `E` = integral of power over the declared interval, including idle consumption during that interval.
- Average active power = `E / interval duration`.
- For a successful repeated block, energy/answer = `E / completed requests` and TPJ = `total useful generated tokens / E`. These are block averages, not per-prompt energy measurements.
- Energy/output token = `E / total useful generated tokens`. It is the reciprocal of TPJ only for exactly the same positive totals and interval.
- Optional energy above idle = `E - idle_power * interval duration`. Keep it alongside gross energy. A negative noisy estimate must remain signed and be treated as unresolved, never clamped to zero or promoted to an efficiency gain.

If requests fail or abort, retain their energy/time and report the failure rate. For efficiency claims, default to counting useful output only from valid completed requests in the numerator, while retaining failed work’s time and energy in the denominator. State this policy explicitly. Partial-output analyses require a separately labelled definition. Any successful-only analysis must be labelled and cannot quietly remove failed work from system-efficiency totals. Efficiency ratios with zero denominators are undefined. Report only precision supported by the sensor and sampling method. For requests too short to resolve independently, use explicitly labelled repeated blocks rather than fabricated per-request energy values.

Current KV260 readings cover **VCC_SOM module power**, not whole-board or FPGA-only power. Follow the [power telemetry record](../devices/kv260-power-telemetry.md). Whole-board input energy needs an external measurement accounting for other power paths. Keep each boundary separate. Logging and correctness work must be treated consistently in both arms. If verification remains inside an existing measured interval, label the result as verified-workload energy/time rather than silently calling it inference-only.

For new KV260 three-prompt circuit comparisons, retain the historical mixed-prompt energy block for continuity. Also measure a separate block of repeated requests for each prompt, clearing context between replies with weights resident. Plan the block lengths before the comparison so even the shortest block spans many sensor updates. Repeat matched blocks on the control and candidate, balancing prompt and circuit order to limit drift. Use the same verification, idle and integration boundaries in both arms. Save each block’s prompt ID, gross module joules, completed replies and useful output tokens. For each prompt, report J/answer and J/output token from the corresponding totals and show variation across paired blocks. Label missing per-prompt coverage explicitly. Give the extended protocol its own identity and preserve the historical mixed-workload records.

For future KV260 energy comparisons, record timestamped SPI1 active time and TPM transfer counts just outside each integration window to flag possible overlap. [SPI1 clock diagnosis](../devices/kv260-spi1-clock-diagnosis.md)

## Measurements required when relevant

Select these before execution when the changed variable or intended claim calls for them. Otherwise mark them not applicable in the template. One grouped reason can cover unrelated conditional families, including for simulations and build-only runs. Additional observer circuitry is not mandatory for an elapsed-time comparison.

| Coverage key | Measure | Required for |
| --- | --- | --- |
| `token_gaps` | Individual token gaps, typical and long gaps | Streaming smoothness, jitter or tail-latency claims. |
| `prefill` | Input-processing time and input tokens/s, excluding decode | Context-length, input processing or prefill optimisation. |
| `sustained_throughput` | Output tokens/s and completed requests/s over repeated workloads | Resident serving, batching, concurrency, scheduling or throughput claims. State batch/concurrency and any queue/load policy. |
| `startup` | Model loading, circuit loading and ready-to-serve time separately | Cold-start, loading, reconfiguration or setup changes. Keep outside warm inference otherwise and reference existing evidence if useful. |
| `cache_capacity` | Cache bytes/position, allocation/valid occupancy, tested context/model limits | Memory placement, cache format, context or capacity changes. Do not equate a theoretical capacity with a tested limit. |
| `communication` | Bytes, transfer time, CPU selection and feedback time | CPU offload, token selection, host software or interface changes. |
| `stage_cycles` | Operation/stage cycles and waits | Stage-level attribution or local cycle-saving claims. Use suitable simulation traces or existing counters where sufficient. Do not require a new observer build just to compare complete-request elapsed time. State which counters partition time and which overlap. |
| `memory_bandwidth` | Useful bytes/s and stalls at a named interface | Memory organisation, external DDR, banking or bandwidth claims. Record access pattern and achieved rate, not just nominal bandwidth. |
| `implementation_timing` | Timing closure, setup/hold slack, clock constraints and routing status | Every new circuit/clock implementation. Link the exact report. Do not convert timing slack into an untested inference frequency. |
| `idle_subtracted_energy` | Energy above matched idle and uncertainty | Claims separating workload energy from ready-state consumption. Gross energy remains primary. |
| `long_stability` | Sustained variation, failures, temperature and clock changes | Thermal behaviour, sustained operation or reliability claims beyond the short comparison. State tested duration. |
| `model_quality` | Task quality against the frozen evaluation and threshold | Changed model, precision, approximation or other changes that relax exact equivalence. |
| `physical_area` | Defensible physical area in mm² | Area claims only, with method and uncertainty. Never derive it directly from FPGA utilisation percentages. |
| `estimated_cost` | Cost/answer or million output tokens | Economic claims, using versioned equipment price, electricity, service life and utilisation assumptions. Label derived estimates. |
| `workload_coverage` | Per-class prompt, output and context lengths, counts and performance | Baseline milestones and claims beyond the original three-prompt workload. |
| `serving_load` | Offered/admitted/completed rates, queue wait, response targets, rejection and timeout rates | Capacity, concurrent-user, scheduler or latency-under-load claims. |
| `client_delivery` | Client submission to actual output delivery, transport and encoding costs | User-experience, network or client-to-answer claims. Board timestamps alone are insufficient. |
| `recovery` | Cancellation, timeout, malformed-input handling, reset/reload and request isolation | Service robustness and changes to lifecycle, queueing, batching or context management. |
| `cross_session` | Repeat the same workload after independent reloads/boots, preserving session-level results | Baseline milestone reproducibility and claims beyond one session. |
| `power_validation` | Named supply boundary, external energy comparison and sensor response/uncertainty | Whole-board/wall-energy or calibration claims. Distinct electrical boundaries are not direct calibration checks. |
| `cross_device_comparison` | Common workload, output quality, numeric formats, service targets and accounting | Comparisons between different chips or complete systems. |

For every development experiment, also record prospective human attention, elapsed build/test time and available AI usage/cost in a short effort note. Unknown values remain unknown. This is descriptive context, not a universal customisation score. Do not invent historical effort estimates.

## Prompt, output and context coverage

Preserve the historical three-prompt workload unchanged. New suites specify exact UTF-8 bytes or token IDs, tokenizer, counts before and after encoding, case families, weighting, output caps, stop rules and seed. Include short, medium and near-limit contexts within the implementation's actual limits. A nominal context capacity is not evidence that all lengths were exercised.

Separate natural completions from controlled work. An output cap is only a maximum, not a guarantee of that many generated tokens. To isolate context-dependent cost, define a separate fixed replay/teacher-forced workload with exact input sequence and measured positions. Do not suppress EOS, alter the runtime or add a forced-length path without a separately reviewed implementation and exact reference. New cases need reference generation and correctness qualification before timed runs. A manifest prepared without inference must mark those references pending, never fabricate them.

Report each length/class before any aggregate, freeze aggregate weights and count completed useful work. Do not select easy prompts after seeing results. Broad semantic claims need representative held-out tasks, not just repeated filler strings or this joke model.

## Serving load and response targets

Record the workload mix, arrival process/seed, planned arrivals, actual submission times, scheduler start, first/last output, completion and correctness decision on a common monotonic timebase. If clocks differ, specify synchronisation uncertainty. The load generator schedules arrivals independently of completions. A serial producer that waits for each response before sending the next request is a closed-loop workload and cannot establish response times at a fixed offered rate.

Measure scheduling lateness separately. Delayed or missed submissions must remain visible rather than moving the planned timestamps or silently lowering the offered load. If the generator cannot maintain its declared schedule within its predeclared tolerance, mark that load point invalid for a capacity claim. Distinguish planned-arrival response time, actual-submission response time, queue wait and service-only time to first token. Only call a boundary client-visible when it was observed at that client.

Declare maximum waiting-queue length, running-worker count, supported active contexts, admission/rejection policy, per-request deadline, global timeout and bounded drain before execution. A queue feeding one inference engine still has one executing request at a time. It does not demonstrate independent concurrent KV caches, batching or multiple hardware engines. Where those are supported later, report context memory, scheduling policy, fairness and per-request decode speed as well as aggregate throughput.

For each offered rate and repetition report:

- Offered, submitted, admitted, completed-valid, rejected, timed-out, failed, cancelled and unfinished requests, with conservation checks and explicit categories that avoid double counting. Keep every offered request's final outcome or censoring reason.
- Queue length over time, queue wait, dispatch lateness, per-request TTFT/completion times and token gaps. Report median/spread and supported tail percentiles by class and repetition.
- Aggregate useful output tokens/s, completed requests/s, and per-request decode TPS. Define admission and completion windows, report backlog at their boundaries and do not mix arrival-window counts with drain-inclusive time without labelling it.
- A predeclared service-level objective (SLO), such as TTFT and completion deadlines, optionally a per-request decode floor, plus required success fraction. Count rejected, failed, timed-out and unfinished requests as failures of the offered-request objective. Report valid requests meeting all targets per second as **goodput**, with its exact denominator/window.
- Gross energy per valid completed request and useful output token over the same stated full workload interval, including failed work and required drain. Keep the standard supply-boundary limits. Retain idle and average power as separate observations.

Report the **highest tested offered rate** that satisfies all predeclared response/success targets, queue-stability criteria and load-generation checks. A bounded queue can remain flat by rejecting requests, so queue stability alone is insufficient. Record nearby failed rate points and do not extrapolate an exact maximum between them. A finite test establishes capacity only for its workload, duration and conditions. Set minimum observation counts and a percentile estimator before measuring. Short samples may support descriptive medians/ranges, not reliable p99 claims.

Do not report a bare number of users. If translating requests/s to active users, state the assumed request frequency, think time, prompt/output mix and bursts. Mark the result as derived. Multiple independent users are not necessarily simultaneous executing requests.

## Longer operation and independent sessions

Freeze duration, request budget, warm-up, session count, workload rotation, cooling and stop rules. Record clock and available temperature telemetry, memory high-water marks, errors, timeouts and latency/throughput/energy trends in fixed windows. Preserve intervals with drift instead of averaging them away. Missing temperatures mean thermal conclusions remain unavailable. A short successful run cannot establish general hardware reliability.

Within-session repetition tests drift and variability. Independent reloads or boots test reproducibility and must be recorded separately, with fresh qualification and restoration. Do not treat many requests within one session as many independent boards or sessions. Optional cancellation and overload recovery probes get their own bounded protocol and never silently enter a timed performance sample.

## Comparisons between chips and services

Choose one of two contracts before the comparison. A same-model comparison fixes model/weights, numerical behaviour or declared equivalence/quality threshold, tokenizer, workload, output rules and service objectives. Allow each device's declared implementation and resource configuration, including batching, while keeping the comparison question clear. A service comparison may use different models but requires a shared held-out task and quality threshold. It measures complete systems, not an isolated chip advantage.

Report hardware/software versions, device count, host, batch/concurrency, context capacity, actual output lengths, queue and response targets, correctness/quality, resource/memory use and power boundary. Byte tokens and subword tokens are not interchangeable. When tokenizers differ, show tokens with their tokenizer identity alongside common completed tasks and output bytes or other meaningful task units. Bytes alone do not establish equal answer quality.

Do not compare KV260 module-supply energy with a GPU-only or whole-server measurement as though the electrical boundaries match. Use equivalent boundaries for an energy ranking, or show scoped figures separately without a whole-system efficiency claim. A whole-board external meter also cannot calibrate a module sensor directly because it includes different loads. Economic comparisons need versioned price, utilisation, lifetime and electricity assumptions in addition to measured capacity and energy.

## Fair summaries and acceptance

Keep the frozen model, numerical rules, input/output contract, clock target and software identical except for the declared intervention. A separately named software baseline, such as the tested slicing variant, can be used consistently in both arms. Retain the original baseline and identify every source/build pin.

Before running, specify repetitions, warm-ups, run order and stopping rules. Report per-case observations and comparable aggregates, with the aggregation method. Pooled TPS uses total counted decode intervals divided by total corresponding decode time. Pooled TPJ uses total useful output divided by total matching energy. Do not silently average ratios or combine unrelated prompt lengths. Report typical values and spread, retaining outliers with explanations where known. Tail percentiles require enough observations and an explicit estimator. A descriptive ±2% band is not a statistical equivalence test.

Show baseline, candidate, units, relative change and variation for each applicable metric. Percentage change is undefined when the baseline is zero. State the evidence scope, including boards, boots and sessions. Count correctness verification consistently. Diagnostic full-score checks can be separate from timed compact delivery, but both timed arms need an equivalent acceptance boundary. Fewer checks are not an inference speed-up.

Counters and logging can affect the system. Identify the instrumented circuit/software and its overhead evidence. Confirm important performance claims without extra diagnostic instrumentation where practical, or state that the claim covers the instrumented implementation. Faster local arithmetic is not automatically faster complete inference.

## Where the standard and results live

- Put the planned measurement coverage in `experiments/<experiment-id>.md` and pin that protocol for execution.
- Keep completed numerical samples in the existing `results/<run-id>/run.json` format. Use `metrics` for supported observed/derived non-negative samples with explicit units and methods. Do not change the v1 schema or old runs to accommodate this standard.
- For new records, set `conditions.measurement_standard` to `inference-measurements-v2` and use `conditions.measurement_coverage` for the coverage keys above. Each entry records its state, metric names or source references, and a reason where necessary. Use separate entries or references when arms/cases differ. Correctness and quality results still belong in the existing top-level fields.
- Put source paths and SHA-256 pins for reused reports in the coverage entry and artifact references. Record signed values such as negative timing slack or noisy idle-subtracted energy in `conditions` or a pinned artifact with units and method, since v1 metric samples are non-negative. Never take an absolute value merely to fit the schema.
- Use the comparison template in `results/<run-id>/findings.md`, or link multiple completed run IDs from the experiment's findings. Report missing core measurements and claim limitations visibly.
- Preserve large raw logs, timestamps, power traces and build artifacts in checksum-verified artifact storage. Git holds the compact records and references. Current verified Mac copies remain the storage arrangement, with shared backup pending.

The existing `records.py check` validates schemas, pins and selections. It does **not** yet enforce this coverage vocabulary, metric formulas or completeness. `records.py compare` checks model, workload, protocol, evidence type and metric definitions, but does not establish equivalence of `conditions` or device configuration. Review those settings manually, allowing only the declared intervention. Put changed measurement boundaries, verification treatment and workloads into new protocol/method/workload identities as applicable, not only into `conditions`. Its ordinary sample means are descriptive, so retain per-case and paired results and spread in findings. Review the filled template and coverage entries before accepting a new comparison. No shared CI change or new runner is introduced by this standard.
