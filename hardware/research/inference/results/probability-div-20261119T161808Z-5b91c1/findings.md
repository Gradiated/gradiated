# Shortening exact attention probability division

The exact shortened divider completed all 200 timed replies on one KV260 at 50 MHz. Median completion took 4.80–7.64% less time across the three fixed prompts. Pooled mixed-block gross VCC_SOM joules per verified answer changed -6.46%. The routed blocks and both arms' replay pins are available in the [routed build](../probability-div-v1-build-20261119T155633Z/findings.md) and [exact RTL qualification](../probability-div-v1-rtl-20261119T160135Z/findings.md).

## Request timing

The board CPU starts timing before request encoding and context clear. Decode rate uses the intervals between useful bytes. Completion includes stopping and drain. Each arm contributed eight mixed-block observations per prompt. The range is the min/max of four round-paired median changes.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 8.562 → 8.497 (-0.75%) | 954.4 → 1006.0 (+5.41%) | 103.097 → 98.152 (-4.80%) | -4.80% to -4.79% |
| Six-byte prompt | 10.146 → 10.048 (-0.97%) | 875.9 → 934.0 (+6.64%) | 149.750 → 140.926 (-5.89%) | -5.90% to -5.86% |
| 48-byte prompt | 95.400 → 90.859 (-4.76%) | 653.4 → 720.8 (+10.31%) | 254.832 → 235.365 (-7.64%) | -7.65% to -7.63% |

## Exact work and FPGA clocks

The three natural prompts reached EOS with the same output bytes in both arms. Every timed reply, warm-up and smoke independently checked against its own replay first, last and completion clocks.

| Prompt | Encoded input tokens | Useful output tokens | Positions | Scored positions | First | Last | Done | Done clocks saved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 11 | 90 | 101 | 91 | 416,191 → 413,023 | 5,078,839 → 4,836,439 | 5,142,970 → 4,895,722 | 247,248 |
| Six-byte prompt | 13 | 122 | 135 | 123 | 494,945 → 490,577 | 7,402,040 → 6,967,880 | 7,475,095 → 7,034,455 | 440,640 |
| 48-byte prompt | 97 | 104 | 201 | 105 | 4,745,325 → 4,517,181 | 12,626,576 → 11,661,776 | 12,716,857 → 11,742,409 | 974,448 |

For one prediction with `d` occupied cache rows, each of the two heads divides once per row. Each division saves 24 clocks, so that prediction saves `48d` clocks. A request that processes positions 1 through `d` saves `24d(d+1)` clocks in total. The paired terminal counters reconciled exactly to that prediction. The RTL audit checked all 256 occupied depths and seven complete-request forecasts. [Pre-run cache-depth analysis](../../experiments/kv260-attention-context-cost-v1/findings.md)

## Gross VCC_SOM energy

The INA260 trace integrates the active block from first admission through final exact verification, including gaps between replies. Idle power averages equal settled brackets with the same loaded weights and context count. Gross ratios pool joules and their matching work totals.

| Scope | Arm | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | Experiment 13 | 3.1175 | 3.0263 | 0.529717 | 0.00502896 | 198.85 |
| Mixed | Probability divider | 3.1195 | 3.0255 | 0.495523 | 0.00470433 | 212.57 |
| Hello | Experiment 13 | 3.1220 | 3.0244 | 0.323681 | 0.00359646 | 278.05 |
| Hello | Probability divider | 3.1187 | 3.0247 | 0.307875 | 0.00342083 | 292.33 |
| Six-byte prompt | Experiment 13 | 3.1123 | 3.0257 | 0.468151 | 0.00383730 | 260.60 |
| Six-byte prompt | Probability divider | 3.1215 | 3.0245 | 0.442036 | 0.00362325 | 276.00 |
| 48-byte prompt | Experiment 13 | 3.1164 | 3.0219 | 0.796415 | 0.00765784 | 130.59 |
| 48-byte prompt | Probability divider | 3.1173 | 3.0259 | 0.735816 | 0.00707515 | 141.34 |

Each alignment cell reports the range of paired gross J/answer changes. Mixed has four pairs, and each fixed-prompt block has two.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -6.87% to -6.00% | -6.84% to -5.94% | -6.79% to -6.03% | -6.88% to -6.00% | -6.87% to -6.00% |
| Hello | -4.96% to -4.81% | -4.98% to -4.82% | -4.94% to -4.80% | -4.96% to -4.81% | -4.96% to -4.81% |
| Six-byte prompt | -5.74% to -5.41% | -5.74% to -5.40% | -5.73% to -5.42% | -5.74% to -5.41% | -5.74% to -5.41% |
| 48-byte prompt | -7.68% to -7.54% | -7.66% to -7.58% | -7.71% to -7.52% | -7.68% to -7.54% | -7.68% to -7.54% |

The 20 Hz sampler skipped 0 scheduled slots. Every integration used the same 75 ms limit on the gap between contributing samples. SPI1 or TPM counters changed in `p1-candidate` +954 ms SPI1, +0 TPM transfers, `homogeneous-p2-encoded-fu2p2q-candidate` +1646 ms SPI1, +106 TPM transfers. The brackets cannot resolve activity inside the integration window.

The three mixed pairs with unchanged SPI1 and TPM counters each used 6.0–6.9% less gross VCC_SOM energy per verified answer.

Active-block temperature brackets showed ams/temp1 27.3 → 27.1 °C (peak 28.6 °C), ams/temp2 28.6 → 27.9 °C (peak 28.7 °C), ams/temp3 26.1 → 25.8 °C (peak 26.3 °C).

## Routing and restoration

| Routed resource | Experiment 13 | Probability divider | Change |
| --- | ---: | ---: | ---: |
| LUTs | 38,329 (32.73%) | 38,383 (32.77%) | +54 |
| Registers | 14,464 (6.17%) | 14,466 (6.18%) | +2 |
| DSPs | 41 (3.29%) | 41 (3.29%) | +0 |
| Block RAM tiles | 39 (27.08%) | 39 (27.08%) | +0 |
| Setup slack, ns | 5.544 | 4.211 | -1.333 |
| Hold slack, ns | 0.012 | 0.013 | +0.001 |

| Routed hierarchy | LUTs | Registers | DSPs | Block RAM tiles |
| --- | ---: | ---: | ---: | ---: |
| Attention | 9,397 → 9,444 | 2,220 → 2,223 | 9 → 9 | 2 → 2 |
| Primary scalar | 4,911 → 5,032 | 982 → 983 | 4 → 4 | 1 → 1 |
| Second exponent | 3,788 → 3,709 | 855 → 854 | 4 → 4 | 1 → 1 |

Both images use on-chip weights and the same model upload of 117,124 bytes. The allocated KV cache is 32,768 bytes. Valid KV contents reached 12,928, 17,280 and 25,728 bytes respectively. [Logical storage accounting](../../implementations/kv260/resource-memory-baseline.md)

The board ran ABBA across three comparison image loads. Nine smoke replies and 36 warm-ups passed. The original image, original weights and all 320 original BOS scores passed restoration on the same boot. Original UIO permissions, clock, firmware and overlay identities were verified.

[Run record](run.json) · [Protocol](../../experiments/kv260-probability-div-v1.md)
