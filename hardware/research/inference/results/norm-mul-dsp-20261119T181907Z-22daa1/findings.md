# Accelerating exact normalization multiplication

The comparison completed all 200 timed replies on one KV260 at 50 MHz. Median completion took 6.20–7.58% less time across the three fixed prompts. Pooled mixed-block gross VCC_SOM joules per verified answer changed -6.95%. The routed blocks and both arms' replay pins are available in the [routed build](../norm-mul-dsp-v1-build-20261119T175758Z/findings.md) and [exact RTL qualification](../norm-mul-dsp-v1-rtl-20261119T175201Z/findings.md).

## Request timing

The board CPU starts timing before request encoding and context clear. Decode rate uses the intervals between useful bytes. Completion includes stopping and drain. Each arm contributed eight mixed-block observations per prompt. The range is the min/max of four round-paired median changes.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 7.572 → 6.840 (-9.67%) | 1099.4 → 1187.3 (+7.99%) | 89.623 → 82.832 (-7.58%) | -7.61% to -7.55% |
| Six-byte prompt | 8.961 → 8.086 (-9.77%) | 1014.0 → 1088.3 (+7.33%) | 129.534 → 120.445 (-7.02%) | -7.04% to -7.00% |
| 48-byte prompt | 82.657 → 76.109 (-7.92%) | 767.6 → 809.4 (+5.45%) | 218.376 → 204.827 (-6.20%) | -6.20% to -6.19% |

## Exact work and FPGA clocks

The three natural prompts reached EOS with the same output bytes in both arms. Each timed reply, warm-up and smoke was checked against its own replay first, last and completion clocks.

| Prompt | Encoded input tokens | Useful output tokens | Positions | Scored positions | First | Last | Done | Done clocks saved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 11 | 90 | 101 | 91 | 366,559 → 329,533 | 4,414,039 → 4,077,439 | 4,469,098 → 4,129,132 | 339,966 |
| Six-byte prompt | 13 | 122 | 135 | 123 | 435,665 → 391,907 | 6,401,864 → 5,950,820 | 6,464,215 → 6,009,805 | 454,410 |
| 48-byte prompt | 97 | 104 | 201 | 105 | 4,107,453 → 3,780,951 | 10,816,976 → 10,143,776 | 10,893,385 → 10,216,819 | 676,566 |

Each processed position invokes three normalization stages. Each stage performs 96 direct products and six products inside reciprocal square root. Each product saves 11 clocks. The dedicated multipliers save 3,366 FPGA clocks per processed position, including intermediate prompt positions. All three complete-request counter differences matched that accounting.

## Gross VCC_SOM energy

The INA260 trace integrates the active block from first admission through final exact verification, including gaps between replies. Idle power averages equal settled brackets with the same loaded weights and context count. Gross ratios pool joules and their matching work totals.

| Scope | Arm | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | Experiment 19 | 3.1159 | 3.0176 | 0.456638 | 0.00433517 | 230.67 |
| Mixed | Dedicated normalization multipliers | 3.1076 | 3.0178 | 0.424914 | 0.00403399 | 247.89 |
| Hello | Experiment 19 | 3.1118 | 3.0216 | 0.280694 | 0.00311882 | 320.63 |
| Hello | Dedicated normalization multipliers | 3.1130 | 3.0209 | 0.259579 | 0.00288421 | 346.72 |
| Six-byte prompt | Experiment 19 | 3.1099 | 3.0134 | 0.405031 | 0.00331993 | 301.21 |
| Six-byte prompt | Dedicated normalization multipliers | 3.1128 | 3.0181 | 0.377038 | 0.00309048 | 323.57 |
| 48-byte prompt | Experiment 19 | 3.1033 | 3.0161 | 0.679824 | 0.00653677 | 152.98 |
| 48-byte prompt | Dedicated normalization multipliers | 3.1096 | 3.0185 | 0.639195 | 0.00614610 | 162.70 |

Each alignment cell reports the range of paired gross J/answer changes. Mixed has four pairs, and each fixed-prompt block has two.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -7.55% to -6.65% | -7.55% to -6.64% | -7.56% to -6.68% | -7.55% to -6.65% | -7.55% to -6.65% |
| Hello | -7.53% to -7.51% | -7.50% to -7.47% | -7.56% to -7.54% | -7.53% to -7.51% | -7.53% to -7.51% |
| Six-byte prompt | -6.95% to -6.87% | -6.97% to -6.87% | -6.94% to -6.87% | -6.95% to -6.87% | -6.95% to -6.87% |
| 48-byte prompt | -6.08% to -5.87% | -6.07% to -5.89% | -6.09% to -5.84% | -6.08% to -5.87% | -6.08% to -5.87% |

The 20 Hz sampler skipped 0 scheduled slots. Every integration used the same 75 ms limit on the gap between contributing samples. SPI1 or TPM counters changed in `p4-candidate` +821 ms SPI1, +0 TPM transfers. The brackets cannot resolve activity inside the integration window.

The 3 mixed pairs with steady SPI1 and TPM counters showed gross energy-per-answer changes from -6.90% to -6.65%.

Active-block temperature brackets showed ams/temp1 25.3 → 25.3 °C (peak 27.8 °C), ams/temp2 27.7 → 25.9 °C (peak 27.7 °C), ams/temp3 24.1 → 23.8 °C (peak 24.6 °C).

## Routing and restoration

| Routed resource | Experiment 19 | Dedicated normalization multipliers | Change |
| --- | ---: | ---: | ---: |
| LUTs | 38,350 (32.74%) | 39,132 (33.41%) | +782 |
| Registers | 14,978 (6.39%) | 16,492 (7.04%) | +1,514 |
| DSPs | 53 (4.25%) | 89 (7.13%) | +36 |
| Block RAM tiles | 39 (27.08%) | 39 (27.08%) | +0 |
| Setup slack, ns | 4.060 | 4.069 | +0.009 |
| Hold slack, ns | 0.015 | 0.011 | -0.004 |

| Routed hierarchy | LUTs | Registers | DSPs | Block RAM tiles |
| --- | ---: | ---: | ---: | ---: |
| First normalization | 6,356 → 6,537 | 1,689 → 2,185 | 4 → 16 | 1 → 1 |
| Second normalization | 6,314 → 6,525 | 1,687 → 2,185 | 4 → 16 | 1 → 1 |
| Final normalization | 6,246 → 6,537 | 1,688 → 2,185 | 4 → 16 | 1 → 1 |

Both images use on-chip weights and the same model upload of 117,124 bytes. The allocated KV cache is 32,768 bytes. Valid KV contents reached 12,928, 17,280 and 25,728 bytes respectively. [Logical storage accounting](../../implementations/kv260/resource-memory-baseline.md)

The board ran ABBA across three comparison image loads. Nine smoke replies and 36 warm-ups passed. The original image, original weights and all 320 original BOS scores passed restoration on the same boot. Original UIO permissions, clock, firmware and overlay identities were verified.

[Run record](run.json) · [Protocol](../../experiments/kv260-norm-mul-dsp-v1.md)
