# Reading projection weights ahead of the multiply-accumulate

The comparison completed all 200 timed replies on one KV260 at 50 MHz. Median completion took 7.86–9.75% less time across the three fixed prompts. Pooled mixed-block gross VCC_SOM joules per verified answer changed -8.52%. The routed blocks and both arms' replay pins are available in the [routed build](../projections-read-ahead-v1-build-20261119T193229Z/findings.md) and [exact RTL qualification](../projections-read-ahead-v1-rtl-20261119T192912Z/findings.md).

## Request timing

The board CPU starts timing before request encoding and context clear. Decode rate uses the intervals between useful bytes. Completion includes stopping and drain. Each arm contributed eight mixed-block observations per prompt. The range is the min/max of four round-paired median changes.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 6.829 → 5.951 (-12.85%) | 1187.3 → 1311.9 (+10.49%) | 82.821 → 74.745 (-9.75%) | -9.77% to -9.72% |
| Six-byte prompt | 8.079 → 7.028 (-13.01%) | 1088.3 → 1192.1 (+9.53%) | 120.438 → 109.629 (-8.97%) | -8.98% to -8.96% |
| 48-byte prompt | 76.133 → 68.348 (-10.23%) | 809.4 → 865.4 (+6.92%) | 204.851 → 188.749 (-7.86%) | -7.86% to -7.85% |

## Exact work and FPGA clocks

The three natural prompts reached EOS with the same output bytes in both arms. Each timed reply, warm-up and smoke was checked against its own replay first, last and completion clocks.

| Prompt | Encoded input tokens | Useful output tokens | Positions | Scored positions | First | Last | Done | Done clocks saved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 11 | 90 | 101 | 91 | 329,533 → 285,544 | 4,077,439 → 3,677,539 | 4,129,132 → 3,725,233 | 403,899 |
| Six-byte prompt | 13 | 122 | 135 | 123 | 391,907 → 339,920 | 5,950,820 → 5,414,954 | 6,009,805 → 5,469,940 | 539,865 |
| 48-byte prompt | 97 | 104 | 201 | 105 | 3,780,951 → 3,393,048 | 10,143,776 → 9,343,976 | 10,216,819 → 9,413,020 | 803,799 |

The paired RTL replay isolated 2,976 clocks per processed position in query, key and value projection, 992 in attention output projection, and 31 exposed clocks in the first feed-forward gate/up pair. Later gate/up work overlapped the scalar consumer in the retained cases. The selected combined design saved 3,999 clocks per processed position across the seven exact replays. All three board request counter differences matched this accounting.

## Gross VCC_SOM energy

The INA260 trace integrates the active block from first admission through final exact verification, including gaps between replies. Idle power averages equal settled brackets with the same loaded weights and context count. Gross ratios pool joules and their matching work totals.

| Scope | Arm | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | Experiment 21 | 3.1206 | 3.0244 | 0.426699 | 0.00405094 | 246.86 |
| Mixed | Projection read-ahead | 3.1213 | 3.0265 | 0.390331 | 0.00370568 | 269.86 |
| Hello | Experiment 21 | 3.1202 | 3.0324 | 0.260171 | 0.00289079 | 345.93 |
| Hello | Projection read-ahead | 3.1253 | 3.0240 | 0.235352 | 0.00261502 | 382.41 |
| Six-byte prompt | Experiment 21 | 3.1218 | 3.0253 | 0.378174 | 0.00309978 | 322.60 |
| Six-byte prompt | Projection read-ahead | 3.1204 | 3.0278 | 0.344206 | 0.00282136 | 354.44 |
| 48-byte prompt | Experiment 21 | 3.1206 | 3.0312 | 0.641355 | 0.00616688 | 162.16 |
| 48-byte prompt | Projection read-ahead | 3.1190 | 3.0251 | 0.590923 | 0.00568195 | 176.00 |

Each alignment cell reports the range of paired gross J/answer changes. Mixed has four pairs, and each fixed-prompt block has two.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -8.88% to -8.12% | -8.82% to -8.08% | -8.82% to -8.15% | -8.88% to -8.12% | -8.88% to -8.12% |
| Hello | -9.63% to -9.45% | -9.65% to -9.43% | -9.65% to -9.48% | -9.63% to -9.45% | -9.63% to -9.45% |
| Six-byte prompt | -8.99% to -8.97% | -9.00% to -9.00% | -8.99% to -8.95% | -8.99% to -8.97% | -8.99% to -8.97% |
| 48-byte prompt | -7.88% to -7.84% | -7.92% to -7.88% | -7.90% to -7.85% | -7.88% to -7.84% | -7.88% to -7.84% |

The 20 Hz sampler skipped 0 scheduled slots. Every integration used the same 75 ms limit on the gap between contributing samples. SPI1 active time and TPM transfer counts were steady in all active-window brackets.

The 4 mixed pairs with steady SPI1 and TPM counters showed gross energy-per-answer changes from -8.88% to -8.12%.

Active-block temperature brackets showed ams/temp1 26.9 → 26.9 °C (peak 28.8 °C), ams/temp2 27.8 → 27.9 °C (peak 29.8 °C), ams/temp3 25.6 → 26.0 °C (peak 26.3 °C).

## Routing and restoration

| Routed resource | Experiment 21 | Projection read-ahead | Change |
| --- | ---: | ---: | ---: |
| LUTs | 38,130 (32.56%) | 38,178 (32.60%) | +48 |
| Registers | 15,605 (6.66%) | 15,595 (6.66%) | -10 |
| DSPs | 57 (4.57%) | 57 (4.57%) | +0 |
| Block RAM tiles | 39 (27.08%) | 39 (27.08%) | +0 |
| Setup slack, ns | 5.418 | 4.027 | -1.391 |
| Hold slack, ns | 0.017 | 0.012 | -0.005 |

| Routed hierarchy | LUTs | Registers | DSPs | Block RAM tiles |
| --- | ---: | ---: | ---: | ---: |
| Query, key and value projection | 135 → 150 | 82 → 80 | 1 → 1 | 2 → 2 |
| Attention output projection | 252 → 265 | 78 → 78 | 1 → 1 | 0.5 → 0.5 |
| Feed-forward gate projection | 167 → 194 | 80 → 80 | 1 → 1 | 2 → 2 |
| Feed-forward up projection | 181 → 185 | 80 → 80 | 1 → 1 | 2 → 2 |

Both images use on-chip weights and the same model upload of 117,124 bytes. The allocated KV cache is 32,768 bytes. Valid KV contents reached 12,928, 17,280 and 25,728 bytes respectively. [Logical storage accounting](../../implementations/kv260/resource-memory-baseline.md)

The board ran ABBA across three comparison image loads. Nine smoke replies and 36 warm-ups passed. The original image, original weights and all 320 original BOS scores passed restoration on the same boot. The board supervisor verified the original UIO device permissions during restoration. A separate stock check confirmed the UIO device mapping and ownership, clock, firmware and overlay identities, and the absence of both temporary images.

[Run record](run.json) · [Protocol](../../experiments/kv260-projections-read-ahead-v1.md)
