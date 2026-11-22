# Experiments and measurements

Aidan adopted **`attention-value-pair-v1`** as the selected circuit comparison baseline on 20 November 2026 after [Experiment 23](kv260-attention-value-pair-v1.md), superseding Experiment 22 (`projections-read-ahead-v1`). Earlier versions, result records and their dated selection statements remain historical evidence. Adoption does not change the circuit currently loaded on the board or authorise new experiments. [Exact baseline pins](../implementations/kv260/README.md#selected-circuit-comparison-baseline).

An experiment asks one concrete question. Record the hypothesis, baseline, variants, fixed controls, correctness/quality gate, resource budget, timeout, repetition plan and success criterion before execution. Keep the definition small, with stable IDs and a concise findings file.

The first [autonomous KV260 comparison](kv260-autonomous-v1.md) moves prompt sequencing, argmax and token feedback from Arm into FPGA logic, keeping the model, prompts, arithmetic, clock target and output limits fixed. Exact simulation, the offline build and the [physical comparison](../results/autonomous-prefill-decode-20261115T210134Z-97efcb/findings.md) have passed. The comparison records first-token latency, output rate and VCC_SOM module energy. Whole-board energy remains unmeasured.

A run is one execution. Every run gets a unique ID and a record satisfying `schemas/run.schema.json`. Pin model, implementation and workload manifests by SHA-256. Record the source commit and any patch artifact. Device identity and operating settings must be explicit. `device.configuration_sha256` hashes the UTF-8 JSON encoding of `configuration` with sorted keys, no whitespace separators, Unicode preserved and non-finite values rejected. Use `configuration_digest` in `tools/records.py` to produce it. Preserve raw sample values and their units alongside summaries.

The [prefill-skip-v1 comparison](kv260-prefill-skip-v1.md), branching from the adopted autonomous-v1 baseline, is complete. Matched simulation, the routed build and [physical measurements](../results/prefill-skip-20261115T224422Z-754f19/findings.md) passed. The original circuit and weights were restored and checked. Aidan adopted `prefill-skip-v1` on 15 November 2026. Experiment 3, [exact scalar multiplication acceleration](kv260-scalar-mul-v1.md), subsequently passed simulation, the routed build and its [physical comparison](../results/scalar-mul-20261116T001133Z-268099/findings.md). The original circuit and weights were restored and checked. Aidan adopted `scalar-mul-v1` on 16 November 2026 as the new selected baseline. Experiment 4, [exact scalar division](kv260-scalar-div-v1.md), subsequently passed simulation, the routed build and its [physical comparison](../results/scalar-div-20261116T105755Z-3c2ae0/findings.md), with an independent audit and verified original-circuit/weight restoration. Aidan adopted scalar-div-v1 on 16 November 2026 as the selected baseline, preserving scalar-mul-v1 and all earlier evidence. Later optimisation experiments require their own agreed plan. [Completed handoff](kv260-scalar-div-handoff.md). DSP sharing remains a separate future proposal. [Completed handoff](kv260-prefill-skip-handoff.md)

## Experiment 5: final token-score pipelining

Completed on 16 November 2026 against scalar-div-v1 using inference-measurements-v1. The final vocabulary projection overlaps the next operand read with the current multiply and accumulation, retaining one arithmetic lane and exact outputs. [Physical results](../results/logits-pipeline-20261116T143416Z-2592fd/findings.md) show 7.3–11.1% higher decode rate, 4.6–9.4% shorter complete requests and 6.6–6.7% less VCC_SOM energy per output token. The routed circuit adds 14 LUTs and 11 registers, with DSP and block RAM unchanged. Original circuit and weights are restored and verified. Scalar-div-v1 remains selected. See the [completed handoff](kv260-logits-pipeline-handoff.md). No automatic baseline promotion is included.

## Experiment 10: attention and cache reads

The [attention profile](kv260-attention-profile-v1.md) measures the adopted circuit’s full attention schedule in simulation before selecting one exact change. The [profile](../results/attention-profile-rtl-20261117T104256Z/findings.md) found that the cache always returned on schedule. The [cache-overlap replay](../results/attention-cache-pipeline-rtl-20261117T105443Z/findings.md) matched all seven cases and used 4.9–7.0% fewer complete-request cycles across the three natural prompts. The [routed build](../results/attention-cache-pipeline-build-20261117T105651Z/findings.md) meets 50 MHz. The [physical comparison](../results/attention-cache-pipeline-20261117T112139Z-daeb2e/findings.md) matched all 36 timed requests and 108 hardware counters. Across the three prompts, time to first token fell 0.6–4.9%, decode rate rose 5.5–8.8%, and completion time fell 4.9–7.0%. Gross VCC_SOM energy per verified answer fell 6.1–6.7% across three paired blocks. The original circuit and weights passed restoration.

## Experiment 9: pipeline the feed-forward down projection

Aidan authorised the [down-projection comparison](kv260-ff-down-pipeline-v1.md) against the adopted `ff-exp-div-v1` baseline. The candidate retains one arithmetic lane and overlaps the read for the next pair with the current multiply-accumulate. The preregistered target is 4,064 clocks saved per processed position. Experiment 9’s [exact simulation](../results/ff-down-rtl-20261117T000318Z/findings.md) matched all seven cases and saved 4,064 clocks per processed position. The [routed 50 MHz build](../results/ff-down-pipeline-build-20261117T000146Z/findings.md) adds 14 LUTs and two registers overall, with DSP and block RAM counts unchanged. The [physical comparison](../results/ff-down-pipeline-20261117T095726Z-1092a6/findings.md) at 50 MHz matched all 36 timed requests and their cycle counts. Across three prompts, median first-token time fell 6.2–9.2%, decode rate rose 3.6–6.1%, and completion time fell 4.4–6.0%. Gross VCC_SOM module energy per verified answer fell 4.9–5.0% across three paired blocks. The original circuit and weights were restored and checked. Aidan subsequently selected `ff-down-pipeline-v1` as the next comparison baseline.

## Experiment 8: exact feed-forward exponential division

Experiment 8 completed on one KV260 at 50 MHz after the USB serial connection passed two short probes, full archive verification and a fresh board health check. Across three fixed prompts, median time to first token fell 12.5–17.4%, decode rate rose 8.0–13.2%, and complete requests took 9.2–12.1% less time. Gross VCC_SOM energy per verified answer fell 10.2–10.8% across three paired blocks. All 36 timed requests matched the expected output and cycle counts. The original circuit and weights were restored and verified. Aidan subsequently adopted `ff-exp-div-v1`. [Physical results](../results/ff-exp-div-20261116T230715Z-0969cc/findings.md) · [Experiment handoff](kv260-ff-exp-div-handoff.md).

## Feed-forward diagnostic after experiment 7

The feed-forward breakdown on the adopted logits-8-lanes-v1 baseline is complete. Simulation replayed seven cases and 716 token positions with all 11 RTL modules unchanged. Exact outputs, cache contents, bus events and phase/cycle records match the archived baseline. Each position takes 34,306 feed-forward cycles: 25,728 (75.0%) in scalar activation/gating send and wait states, 8,256 (24.1%) in the final down projection, 193 in gate/up pair handling and 129 in storage/start control. These are disjoint elapsed controller windows. Child arithmetic overlaps them and must not be added again.

The exponential's three divisions by the fixed denominator 45,426 occupy 12,672 cycles (36.9% of feed-forward time). The sigmoid's separate runtime division occupies another 4,224. Gate and up projections each execute 8,320 arithmetic/read/rounding cycles, but all except 65 overlap scalar processing. Accelerating them alone has less than 0.1% whole-request potential under this unchanged schedule. The next candidate for discussion is an exact specialised divider for the feed-forward exponential, with down-projection READ/MAC overlap as a simpler separate option. These are proposals, not implemented speed-ups. Preserve exact quotient, remainder, rounding and supported input-domain behaviour, not just the operands seen in this profile. No acceleration is selected or authorised by this diagnostic. [Findings](../results/ff-profile-rtl-20261116T211748Z/findings.md) · [Protocol](kv260-feed-forward-profile-v1.md). The selected baseline remains logits-8-lanes-v1. Stop for Aidan's decision before implementation.

## Experiment 7: eight versus four final token-score lanes

Experiment 7 compared eight lanes directly with the saved four-lane implementation. Matched simulation, the routed 50 MHz build and the independently audited physical comparison passed. Decode rate rose 1.1–1.7%, complete-request time fell 0.7–1.6%, and gross VCC_SOM energy per answer/output token fell 0.66–1.05% across three paired blocks. These are small observed differences on three prompts in one board boot, not a general energy guarantee. The whole circuit adds a net 393 LUTs, 322 registers and four DSPs, with block RAM unchanged. Original circuit and weights are restored and checked. Scalar-div-v1 remains selected. [Physical findings](../results/logits-8-lanes-20261116T202250Z-44df9d/findings.md) · [Completed handoff](kv260-logits-eight-handoff.md). Ethernet and broader serving benchmarks remain deferred.

## Experiment 6: parallel final token-score arithmetic

Experiment 6 compared one, two and four lanes in the final token-score projection. [Two-lane physical results](../results/logits-2-lanes-20261116T164332Z-6c4968/findings.md) show 4.2–6.5% higher decode rate and 3.6–4.3% less gross module energy per answer. [Four-lane results](../results/logits-4-lanes-20261116T170727Z-020546/findings.md) show 6.4–10.0% higher decode rate and 5.7–6.1% less energy. Each is paired separately with the one-lane logits-pipeline-v1 control. Exact simulation, routed 50 MHz builds, physical checks and independent audits passed. Original circuit and weights are restored and verified. Scalar-div-v1 remains selected. [Completed handoff](kv260-logits-lanes-handoff.md). Article prose is outside this experiment's write scope.

## Broader benchmark preparation

On 16 November 2026 Aidan authorised preparation of the prompt/context-length suite, request-load test and longer repeatability run, with no execution. These are baseline characterisation suites, not a new circuit optimisation or automatic adoption of experiment 5. See the [benchmark roadmap](benchmark-roadmap.md) and [preparation handoff](kv260-milestone-preparation.md). Scalar-div-v1 remains the target baseline.

## Potential future experiment: share DSPs between stages

Proposed on 15 November 2026, not scheduled or authorised to run. Test whether stages whose arithmetic does not overlap can share physical DSP blocks without reducing inference speed. The prefill-skip-v1 build uses ten DSPs across separate modules, but this is not a proven minimum. First identify actual overlap from the execution schedule, then choose one sharing change. Do not assume all ten can be replaced by one without a performance cost.

Keep the frozen model, exact numerical behaviour, workloads and clock target fixed. Use the standard measurement scorecard, with particular attention to DSP savings, extra LUT/register and routing costs, timing closure, additional cycles, TTFT, decode rate and module energy. Fewer allocated DSPs alone do not establish an energy saving. Keep this separate from the proposed experiment 3, which accelerates the existing scalar multiplier.

## Experiment 14 · Output projection weights from DDR4

The [protocol](kv260-output-projection-ddr4-v1.md) is complete. The [physical comparison](../results/output-projection-ddr4-20261118T232351Z-c820f6/findings.md) on one 50 MHz fixture matched 188 timed replies. One outstanding read per weight increased median complete-answer time by 21.73%–27.00% across three prompts. Paired gross mixed-block module joules per verified answer increased 23.99%–24.28%. All additional FPGA clocks reconciled to the output projection weight waits. The original circuit and every original BOS score passed restoration. Experiment 13 remains the selected comparison baseline.

## Experiment 15 · Beat reuse and row bursts

The [protocol](kv260-output-projection-ddr4-burst-v1.md) is complete. The [physical comparison](../results/output-projection-ddr4-burst-20261119T111700Z-e69dad/findings.md) matched 400 timed replies. Row bursts changed median completion time from scalar reads by -20.24% to -16.98% across the three prompts and changed gross mixed-block module joules per answer by -18.49%. Experiment 13 remains the comparison baseline.

## Experiment 16 · Final logits from DDR4

The [protocol](kv260-logits-ddr4-burst-v1.md) is complete. All 200 timed replies matched the reference and original restoration verified all 320 BOS scores. Median completion changed +5.41% to +11.58% across the three prompts. Gross mixed-block VCC_SOM joules per verified answer changed +8.55%. The routed design used 39 on-chip control BRAM tiles and 31 candidate BRAM tiles, with the input embedding retained on-chip. Experiment 13 remains selected. [Physical findings](../results/logits-ddr4-burst-20261119T121954Z-31256a/findings.md)

## Experiment 17 · Overlap DDR4 weight reads with final scoring

The [protocol](kv260-logits-ddr4-prefetch-v1.md) is complete. Both circuits returned exact outputs in all 200 timed replies. Across three prompts, median completion took 1.26–2.54% less time. Gross mixed-block VCC_SOM energy per answer changed -1.87%. The prefetch circuit used 31 block RAM tiles and the original image, weights and HP0 settings passed restoration. [Physical findings](../results/logits-ddr4-prefetch-20261119T151537Z-9eeb65/findings.md)

## Experiment 18 · Shorten exact attention probability division

Experiment 18 tested exact shortened attention probability division against the selected on-chip Experiment 13 circuit at 50 MHz. Across three prompts, median completion took 4.80–7.64% less time. Pooled gross mixed-block VCC_SOM joules per verified answer changed -6.46%. All 200 timed replies and their FPGA clocks matched. The original circuit and all 320 BOS scores passed restoration. [Physical findings](../results/probability-div-20261119T161808Z-5b91c1/findings.md) · [Protocol](kv260-probability-div-v1.md) · [Prior forecast](kv260-attention-context-cost-v1/findings.md)

## Experiment 19 · Accelerate exact feed-forward scalar multiplication

Experiment 19 compared the exact feed-forward DSP multiplier with the selected Experiment 18 circuit at 50 MHz. Across three prompts, median completion took 7.21–8.70% less time. Pooled gross mixed-block VCC_SOM joules per verified answer changed -8.09%. All 200 timed responses and their FPGA counters matched. The original firmware and all 320 BOS scores passed restoration. [Physical findings](../results/ff-scalar-mul-dsp-20261119T171509Z-1b23a4/findings.md) · [Protocol](kv260-scalar-product-opportunity-v1.md)

## Experiment 20 · Accelerate exact normalization multiplication

Experiment 20 compared exact DSP multiplication in the three normalization stages with Experiment 19 at 50 MHz. Across three prompts, median completion took 6.20–7.58% less time. Pooled gross mixed-block VCC_SOM joules per verified answer changed -6.95%. All 200 timed replies and their FPGA counters matched. The original firmware and all 320 BOS scores passed restoration. [Physical findings](../results/norm-mul-dsp-20261119T181907Z-22daa1/findings.md) · [Protocol](kv260-norm-mul-dsp-v1.md)

## Experiment 21 · Share the exact normalization multiplier

Experiment 21 compared one shared exact normalization multiplier with Experiment 20's dedicated multipliers at 50 MHz. Across three prompts, median completion changed -0.02% to +0.01%. Pooled gross mixed-block VCC_SOM joules per verified answer changed +0.06%. All 200 timed replies and their FPGA counters matched. The original firmware and all 320 BOS scores passed restoration. The shared design changed routed DSP use from 89 to 57. [Physical findings](../results/norm-mul-shared-20261119T184132Z-42cf65/findings.md) · [Protocol](kv260-norm-mul-shared-v1.md)

## Standard scorecard

New experiments follow [inference-measurements-v2](measurement-standard-v2.md) and the [comparison template](comparison-template.md). Keep [v1](measurement-standard.md) for historical results. The standard separates the required core scorecard for physical inference comparisons from experiment-specific diagnostics. Record explicit coverage gaps and reuse unchanged static reports. Preserve completed records and existing baselines. The standard adds no authority to run experiments.

## Fair comparison

The protocol ID identifies an immutable version of the benchmark. Task, model, workload, quality gate, tokenizer, batch/concurrency, context, warm-up and measurement boundary form its comparison contract. Changing one requires a new protocol or an explicitly reviewed comparison. Different implementations and devices can be compared under the same contract, but their settings must remain visible.

Distinguish correctness from model quality. An integer implementation may exactly match its reference while the reference model performs poorly. Precision changes need a quality gate. Runs that fail correctness or quality cannot support an unqualified speedup claim.

Measure warm-up and steady-state deliberately. Repeat runs according to the protocol, retain variability and record environmental drift. Do not infer whole-board energy from chip power or treat timing closure as measured inference throughput. Report missing measurements as missing, never zero.

Keep observations separate from derived metrics. Energy divided by completed output tokens gives joules per token under the declared boundary. Estimated cost additionally depends on hardware price, electricity, service life and utilisation. Store those assumptions and calculation version separately.

## History and execution

Retain failures, timeouts, negative results and aborted runs with their status. Corrections create a new record with `supersedes`; do not overwrite a completed run. Select baselines through an explicit decision after relevant checks, not simply the newest timestamp.

Only one process may configure or measure a board at once. Identify its owner and run ID before launch, use bounded commands and release ownership after collecting evidence. Recover source, manifests and unique artifacts from temporary hosts before retirement. Preserve logs needed to interpret failures.

Experiment 22 compared projection read-ahead with the adopted Experiment 21 circuit. Read-ahead in the query/key/value, attention output and feed-forward gate/up projections saved 2,976, 992 and 31 exposed clocks per position in isolated simulations. The combined design saved exactly 3,999 clocks per position in simulation and in the three physical workload cases. Median complete replies took 7.86–9.75% less time across the three prompts. Gross mixed-workload VCC_SOM energy per verified reply changed -8.52%. The design used 48 more LUTs and 10 fewer flip-flops, with 57 DSPs and 39 BRAM tiles in both circuits. The original circuit, original weights and 320 original BOS scores passed restoration. [Physical comparison](../results/projections-read-ahead-20261119T195431Z-008bba/findings.md) · [Isolated and combined RTL](../results/projections-read-ahead-v1-rtl-20261119T192912Z/findings.md) · [Routed build](../results/projections-read-ahead-v1-build-20261119T193229Z/findings.md)

Experiment 23 compared two attention value-mixing lanes with the one-lane Experiment 22 baseline. The two lanes share one attention probability and read adjacent coordinates from even and odd value banks. The combined circuit added 1,198 LUTs, 117 flip-flops and one DSP, with 39 BRAM tiles in both designs. The standard board counters matched the simulated saving of 32D + 16 clocks per processed position at occupied cache depth D. Across the three prompts, median complete replies took 4.44–6.92% less time. Mixed-workload gross VCC_SOM energy per verified answer changed -5.89%. All 200 timed replies matched, and all 320 original BOS scores matched after restoration. [Physical comparison](../results/attention-value-pair-20261119T234247Z-e21df0/findings.md) · [Cache-depth and exact RTL results](../results/attention-value-pair-v1-rtl-20261119T203052Z/findings.md) · [Routed build](../results/attention-value-pair-v1-build-20261119T203714Z/findings.md)
