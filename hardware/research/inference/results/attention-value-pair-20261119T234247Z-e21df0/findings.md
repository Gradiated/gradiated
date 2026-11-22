# Pairing lanes in attention value mixing

The comparison completed all 200 timed replies on one KV260 at 50 MHz. Median completion took 4.44–6.92% less time across the three fixed prompts. Pooled mixed-block gross VCC_SOM joules per verified answer changed -5.89%. The routed blocks and both arms' replay pins are available in the [routed build](../attention-value-pair-v1-build-20261119T203714Z/findings.md) and [exact RTL qualification](../attention-value-pair-v1-rtl-20261119T203052Z/findings.md).

## Request timing

The board CPU starts timing before request encoding and context clear. Decode rate uses the intervals between useful bytes. Completion includes stopping and drain. Each arm contributed eight mixed-block observations per prompt. The range is the min/max of four round-paired median changes.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 5.953 → 5.920 (-0.54%) | 1311.9 → 1377.2 (+4.98%) | 74.747 → 71.431 (-4.44%) | -4.52% to -4.42% |
| Six-byte prompt | 7.031 → 6.971 (-0.85%) | 1192.1 → 1263.9 (+6.03%) | 109.632 → 103.716 (-5.40%) | -5.40% to -5.38% |
| 48-byte prompt | 68.357 → 65.285 (-4.49%) | 865.4 → 943.5 (+9.03%) | 188.758 → 175.701 (-6.92%) | -6.92% to -6.91% |

## Exact work and FPGA clocks

The three natural prompts reached EOS with the same output bytes in both arms. Each timed reply, warm-up and smoke was checked against its own replay first, last and completion clocks.

| Prompt | Encoded input tokens | Useful output tokens | Positions | Scored positions | First | Last | Done | Done clocks saved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 11 | 90 | 101 | 91 | 285,544 → 283,256 | 3,677,539 → 3,514,339 | 3,725,233 → 3,558,785 | 166,448 |
| Six-byte prompt | 13 | 122 | 135 | 123 | 339,920 → 336,800 | 5,414,954 → 5,123,370 | 5,469,940 → 5,174,020 | 295,920 |
| 48-byte prompt | 97 | 104 | 201 | 105 | 3,393,048 → 3,239,400 | 9,343,976 → 8,697,576 | 9,413,020 → 8,760,172 | 652,848 |

RTL replay attributes all saved request clocks to the attention phase. At occupied depth D, pairing the value products saves 32D + 16 clocks while preserving the weighted terms and exact output. A request processing positions 1 through n saves 16n(n+2) clocks. All three board request boundaries matched their qualified replay. The controlled RTL sweep tested depths 1, 16, 64, 128 and 256.

The stage-cycle attribution and controlled context-length sweep use RTL replay. The board comparison measured the three frozen natural prompts and their complete FPGA request boundaries.

## Gross VCC_SOM energy

The INA260 trace integrates the active block from first admission through final exact verification, including gaps between replies. Idle power averages equal settled brackets with the same loaded weights and context count. Gross ratios pool joules and their matching work totals.

| Scope | Arm | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | Experiment 22 | 3.1158 | 3.0195 | 0.389705 | 0.00369973 | 270.29 |
| Mixed | Two-lane attention value mixing | 3.1175 | 3.0205 | 0.366761 | 0.00348191 | 287.20 |
| Hello | Experiment 22 | 3.1179 | 3.0211 | 0.234782 | 0.00260869 | 383.33 |
| Hello | Two-lane attention value mixing | 3.1153 | 3.0186 | 0.224212 | 0.00249124 | 401.41 |
| Six-byte prompt | Experiment 22 | 3.1159 | 3.0267 | 0.343688 | 0.00281712 | 354.97 |
| Six-byte prompt | Two-lane attention value mixing | 3.1214 | 3.0228 | 0.325932 | 0.00267157 | 374.31 |
| 48-byte prompt | Experiment 22 | 3.1228 | 3.0178 | 0.591795 | 0.00569034 | 175.74 |
| 48-byte prompt | Two-lane attention value mixing | 3.1103 | 3.0223 | 0.548665 | 0.00527562 | 189.55 |

Each alignment cell reports the range of paired gross J/answer changes. Mixed has four pairs, and each fixed-prompt block has two.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -6.25% to -5.26% | -6.26% to -5.25% | -6.26% to -5.28% | -6.25% to -5.26% | -6.25% to -5.26% |
| Hello | -4.51% to -4.50% | -4.90% to -4.49% | -4.48% to -4.48% | -4.51% to -4.50% | -4.51% to -4.50% |
| Six-byte prompt | -5.46% to -4.87% | -5.42% to -4.82% | -5.51% to -4.88% | -5.46% to -4.87% | -5.46% to -4.87% |
| 48-byte prompt | -7.38% to -7.20% | -7.38% to -7.19% | -7.38% to -7.20% | -7.38% to -7.20% | -7.38% to -7.20% |

The 20 Hz sampler skipped 0 scheduled slots. Every integration used the same 75 ms limit on the gap between contributing samples. SPI1 or TPM counters changed in `p2-control` +751 ms SPI1, +0 TPM transfers. The brackets cannot resolve activity inside the integration window.

The 3 mixed pairs with steady SPI1 and TPM counters showed gross energy-per-answer changes from -6.08% to -5.26%.

Active-block temperature brackets showed ams/temp1 26.5 → 26.5 °C (peak 28.4 °C), ams/temp2 26.5 → 26.7 °C (peak 28.0 °C), ams/temp3 25.4 → 25.0 °C (peak 25.7 °C).

## Routing and restoration

| Routed resource | Experiment 22 | Two-lane attention value mixing | Change |
| --- | ---: | ---: | ---: |
| LUTs | 38,178 (32.60%) | 39,376 (33.62%) | +1,198 |
| Registers | 15,595 (6.66%) | 15,712 (6.71%) | +117 |
| DSPs | 57 (4.57%) | 58 (4.65%) | +1 |
| Block RAM tiles | 39 (27.08%) | 39 (27.08%) | +0 |
| Setup slack, ns | 4.027 | 1.390 | -2.637 |
| Hold slack, ns | 0.012 | 0.005 | -0.007 |

| Routed hierarchy | LUTs | Registers | DSPs | Block RAM tiles |
| --- | ---: | ---: | ---: | ---: |
| Attention | 9,442 → 10,613 | 2,220 → 2,335 | 9 → 10 | 2 → 2 |
| KV cache | 299 → 324 | 28 → 29 | 0 → 0 | 8 → 8 |
| Frontend | 1,502 → 1,530 | 1,337 → 1,335 | 4 → 4 | 12 → 12 |

Both images use on-chip weights and the same model upload of 117,124 bytes. The allocated KV cache is 32,768 bytes. Valid KV contents reached 12,928, 17,280 and 25,728 bytes respectively. [Logical storage accounting](../../implementations/kv260/resource-memory-baseline.md)

The candidate keeps one 8,192 × 16 K bank and splits V into two 4,096 × 16 parity banks. The exact routed mapping accounted for every identified cache RAM primitive in those BRAM banks. [Routed bank counts and connectivity](../attention-value-pair-v1-build-20261119T203714Z/findings.md)

The board ran ABBA across three comparison image loads. Nine smoke replies and 36 warm-ups passed. The original image, original weights and all 320 original BOS scores passed restoration on the same boot. The supervisor verified the original UIO permissions. The separate stock check confirmed the UIO device mapping, FPGA clock, original firmware and overlays. It also confirmed the absence of active owners and both temporary FPGA images.

[Run record](run.json) · [Protocol](../../experiments/kv260-attention-value-pair-v1.md)
