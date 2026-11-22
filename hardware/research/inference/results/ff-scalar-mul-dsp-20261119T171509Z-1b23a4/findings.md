# Accelerating exact feed-forward scalar multiplication

The DSP multiplier trial completed all 200 timed replies on one KV260 at 50 MHz. Median completion took 7.21–8.70% less time across the three fixed prompts. Pooled mixed-block gross VCC_SOM joules per verified answer changed -8.09%. The routed blocks and both arms' replay pins are available in the [routed build](../ff-scalar-mul-dsp-v1-build-20261119T165358Z/findings.md) and [exact RTL qualification](../ff-scalar-mul-dsp-v1-rtl-20261119T165532Z/findings.md).

## Request timing

The board CPU starts timing before request encoding and context clear. Decode rate uses the intervals between useful bytes. Completion includes stopping and drain. Each arm contributed eight mixed-block observations per prompt. The range is the min/max of four round-paired median changes.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 8.497 → 7.566 (-10.96%) | 1006.0 → 1099.4 (+9.29%) | 98.152 → 89.618 (-8.70%) | -8.72% to -8.66% |
| Six-byte prompt | 10.064 → 8.955 (-11.03%) | 934.0 → 1014.0 (+8.57%) | 140.943 → 129.527 (-8.10%) | -8.10% to -8.08% |
| 48-byte prompt | 90.839 → 82.645 (-9.02%) | 720.8 → 767.6 (+6.48%) | 235.344 → 218.365 (-7.21%) | -7.22% to -7.20% |

## Exact work and FPGA clocks

The three natural prompts reached EOS with the same output bytes in both arms. Every timed reply, warm-up and smoke independently checked against its own replay first, last and completion clocks.

| Prompt | Encoded input tokens | Useful output tokens | Positions | Scored positions | First | Last | Done | Done clocks saved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 11 | 90 | 101 | 91 | 413,023 → 366,559 | 4,836,439 → 4,414,039 | 4,895,722 → 4,469,098 | 426,624 |
| Six-byte prompt | 13 | 122 | 135 | 123 | 490,577 → 435,665 | 6,967,880 → 6,401,864 | 7,034,455 → 6,464,215 | 570,240 |
| 48-byte prompt | 97 | 104 | 201 | 105 | 4,517,181 → 4,107,453 | 11,661,776 → 10,816,976 | 11,742,409 → 10,893,385 | 849,024 |

At each processed position, including intermediate prompt positions, the feed-forward scalar processes 128 elements. It computes three products per element for exponential interpolation, gating and the hidden value. Each product saves 11 clocks, for 4,224 fewer FPGA clocks per position. All three complete-request deltas matched that count. This corrects the archived report generator's factorisation. [Exact RTL replay](../ff-scalar-mul-dsp-v1-rtl-20261119T165532Z/findings.md)

## Gross VCC_SOM energy

The INA260 trace integrates the active block from first admission through final exact verification, including gaps between replies. Idle power averages equal settled brackets with the same loaded weights and context count. Gross ratios pool joules and their matching work totals.

| Scope | Arm | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | Experiment 18 | 3.1156 | 3.0196 | 0.494885 | 0.00469827 | 212.84 |
| Mixed | DSP multiplier | 3.1040 | 3.0155 | 0.454834 | 0.00431805 | 231.59 |
| Hello | Experiment 18 | 3.1101 | 3.0197 | 0.307024 | 0.00341138 | 293.14 |
| Hello | DSP multiplier | 3.1166 | 3.0139 | 0.281073 | 0.00312303 | 320.20 |
| Six-byte prompt | Experiment 18 | 3.1134 | 3.0144 | 0.440989 | 0.00361466 | 276.65 |
| Six-byte prompt | DSP multiplier | 3.1083 | 3.0173 | 0.404690 | 0.00331713 | 301.46 |
| 48-byte prompt | Experiment 18 | 3.1057 | 3.0200 | 0.733100 | 0.00704904 | 141.86 |
| 48-byte prompt | DSP multiplier | 3.1065 | 3.0149 | 0.680537 | 0.00654362 | 152.82 |

Each alignment cell reports the range of paired gross J/answer changes. Mixed has four pairs, and each fixed-prompt block has two.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -8.68% to -7.82% | -8.74% to -7.88% | -8.66% to -7.81% | -8.68% to -7.82% | -8.68% to -7.82% |
| Hello | -8.81% to -8.10% | -8.81% to -8.09% | -8.82% to -8.11% | -8.81% to -8.10% | -8.81% to -8.10% |
| Six-byte prompt | -8.60% to -7.86% | -8.61% to -7.89% | -8.61% to -7.87% | -8.60% to -7.86% | -8.60% to -7.86% |
| 48-byte prompt | -7.41% to -6.93% | -7.38% to -6.95% | -7.43% to -6.93% | -7.41% to -6.93% | -7.41% to -6.93% |

The 20 Hz sampler skipped 0 scheduled slots. Every integration used the same 75 ms limit on the gap between contributing samples. SPI1 active time and TPM transfer counts were steady in all active-window brackets.

The 4 mixed pairs with steady SPI1 and TPM counters showed gross energy-per-answer changes from -8.68% to -7.82%.

Active-block temperature brackets showed ams/temp1 26.3 → 26.3 °C (peak 27.5 °C), ams/temp2 26.6 → 25.8 °C (peak 27.7 °C), ams/temp3 24.5 → 24.8 °C (peak 25.2 °C).

## Routing and restoration

| Routed resource | Experiment 18 | DSP multiplier | Change |
| --- | ---: | ---: | ---: |
| LUTs | 38,383 (32.77%) | 38,350 (32.74%) | -33 |
| Registers | 14,466 (6.18%) | 14,978 (6.39%) | +512 |
| DSPs | 41 (3.29%) | 53 (4.25%) | +12 |
| Block RAM tiles | 39 (27.08%) | 39 (27.08%) | +0 |
| Setup slack, ns | 4.211 | 4.060 | -0.151 |
| Hold slack, ns | 0.013 | 0.015 | +0.002 |

| Routed hierarchy | LUTs | Registers | DSPs | Block RAM tiles |
| --- | ---: | ---: | ---: | ---: |
| Feed-forward | 5,466 → 5,419 | 1,506 → 2,010 | 7 → 19 | 7 → 7 |
| Feed-forward scalar | 4,757 → 4,709 | 988 → 1,492 | 4 → 16 | 1 → 1 |

Both images use on-chip weights and the same model upload of 117,124 bytes. The allocated KV cache is 32,768 bytes. Valid KV contents reached 12,928, 17,280 and 25,728 bytes respectively. [Logical storage accounting](../../implementations/kv260/resource-memory-baseline.md)

The board ran ABBA across three comparison image loads. Nine smoke replies and 36 warm-ups passed. The original image, original weights and all 320 original BOS scores passed restoration on the same boot. Original UIO permissions, clock, firmware and overlay identities were verified.

[Run record](run.json) · [Protocol](../../experiments/kv260-scalar-product-opportunity-v1.md)
