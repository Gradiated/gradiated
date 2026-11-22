# Overlapping final-score weight reads with scoring

The sequential and prefetch circuits returned exact outputs in all 200 timed replies on one KV260 at 50 MHz. Median completion took 1.26–2.54% less time across the three prompts. The prefetch circuit used 31 block RAM tiles, compared with 31 for the sequential DDR4 circuit and 39 for the historical on-chip circuit. Pooled mixed-block gross module energy per verified answer changed -1.87%. [Routed build](../logits-ddr4-prefetch-build-20261119T145535Z/findings.md) · [Exact RTL replay](../logits-ddr4-prefetch-rtl-20261119T150027Z/findings.md)

## Request timing

Each arm supplied eight mixed-block observations per prompt. Timing begins at board CPU admission. Decode rate counts useful byte intervals from the first useful byte to the last. Completion ends before verification.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 8.689 → 8.678 (-0.13%) | 848.3 → 872.1 (+2.81%) | 115.033 → 112.108 (-2.54%) | -2.57% to -2.51% |
| Six-byte prompt | 10.287 → 10.241 (-0.45%) | 785.8 → 806.1 (+2.58%) | 165.854 → 161.896 (-2.39%) | -2.40% to -2.38% |
| 48-byte prompt | 95.542 → 95.510 (-0.03%) | 601.9 → 613.8 (+1.98%) | 268.595 → 265.216 (-1.26%) | -1.27% to -1.24% |

## Memory service and overlap

Both arms issued 320 read addresses and received 2,560 beats carrying 20,480 matrix bytes per scored position. The FPGA counter reports exposed wait. Subtracting exposed wait from measured address, beat and stall cycles gives inferred overlap. The projection-busy counter equals 1,680 clocks of arithmetic and control per scored position plus exposed wait. The change in request clocks matched the change in projection-busy clocks on every paired reply. Bus-service clocks sum accepted addresses, accepted beats, address stalls and response waits. Launch and capture cancel in this counter identity. Service varied slightly between the two arms and also contributed to the measured savings. In RTL replay, direct event traces counted 1,599 overlapping clocks per scored position, including 663 clocks with an accepted AXI address or response. The physical run derives overlap from request counters.

| Prompt | Scored positions | HP0 bytes per reply | Service clocks per position | R wait per position | AR stall per position | Exposed clocks per position | Inferred hidden clocks per position | Projection clocks per position | Completion change in FPGA time, ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 91 | 1,863,680 | 6,550.8 → 6,538.6 | 3,670.8 → 3,658.6 | 0.0 → 0.0 | 6,550.8 → 4,939.6 | 0.0 → 1,599.0 | 8,230.8 → 6,619.6 | -2.932 |
| Six-byte prompt | 123 | 2,519,040 | 6,542.5 → 6,538.0 | 3,662.5 → 3,658.0 | 0.0 → 0.0 | 6,542.5 → 4,939.0 | 0.0 → 1,599.0 | 8,222.5 → 6,619.0 | -3.944 |
| 48-byte prompt | 105 | 2,150,400 | 6,547.9 → 6,536.5 | 3,667.9 → 3,656.5 | 0.0 → 0.0 | 6,547.9 → 4,937.5 | 0.0 → 1,599.0 | 8,227.9 → 6,617.5 | -3.382 |

Accepted HP0 bytes divided by projection busy time gave 124.4 → 154.7 MB/s for Hello, 124.5 → 154.7 MB/s for Six-byte prompt, 124.5 → 154.7 MB/s for 48-byte prompt. This phase-specific rate includes scoring time. DMA bases differed in 7 of the 10 paired blocks. The run record lists each allocation.

## Gross VCC_SOM energy

Energy is the gross trace integral across the active block, including inter-reply verification and matched DDR counter reads. Active watts divide joules by block duration. Mixed-block active power averaged 3.1155 W sequential and 3.1150 W prefetch. Idle watts average the settled brackets at equal context. Median in-block post-verification counter-check totals were 0.817 ms sequential and 0.834 ms prefetch in mixed blocks.

| Scope | Mode | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | Sequential | 3.1155 | 3.0150 | 0.573225 | 0.00544201 | 183.76 |
| Mixed | Prefetch | 3.1150 | 3.0171 | 0.562499 | 0.00534018 | 187.26 |
| Hello | Sequential | 3.1076 | 3.0158 | 0.359576 | 0.00399529 | 250.29 |
| Hello | Prefetch | 3.1116 | 3.0127 | 0.350994 | 0.00389994 | 256.41 |
| Six-byte prompt | Sequential | 3.1135 | 3.0156 | 0.518994 | 0.00425405 | 235.07 |
| Six-byte prompt | Prefetch | 3.1037 | 3.0076 | 0.505060 | 0.00413984 | 241.56 |
| 48-byte prompt | Sequential | 3.1107 | 3.0175 | 0.838216 | 0.00805977 | 124.07 |
| 48-byte prompt | Prefetch | 3.1086 | 3.0104 | 0.827077 | 0.00795266 | 125.74 |

Each column gives the minimum and maximum paired J/answer change across the matching blocks. Mixed has four pairs and each single prompt has two.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -2.08% to -1.63% | -2.13% to -1.67% | -2.04% to -1.60% | -2.08% to -1.63% | -2.08% to -1.63% |
| Hello | -2.76% to -2.01% | -2.76% to -2.00% | -2.76% to -2.02% | -2.76% to -2.01% | -2.76% to -2.01% |
| Six-byte prompt | -2.74% to -2.63% | -2.75% to -2.64% | -2.74% to -2.63% | -2.74% to -2.63% | -2.74% to -2.63% |
| 48-byte prompt | -1.43% to -1.23% | -1.49% to -1.24% | -1.42% to -1.22% | -1.43% to -1.23% | -1.43% to -1.23% |

SPI1 and TPM counters were steady in all mixed-block brackets. homogeneous-p2-encoded-hello-prefetch logged +654 ms of SPI1 active time and +104 TPM transfers. The timing relative to the active window is unresolved. ams/temp1 was 25.5 °C at entry, 26.1 °C at exit, and peaked at 27.1 °C in the measured brackets. ams/temp2 was 25.1 °C at entry, 25.1 °C at exit, and peaked at 27.0 °C in the measured brackets. ams/temp3 was 24.4 °C at entry, 24.1 °C at exit, and peaked at 24.7 °C in the measured brackets.

## Routing and restoration

| Resource | Sequential | Prefetch | Change |
| --- | ---: | ---: | ---: |
| LUTs | 38,978 | 39,050 | +72 |
| Registers | 14,844 | 14,850 | +6 |
| DSPs | 41 | 41 | +0 |
| Block RAM tiles | 31 | 31 | +0 |
| Reader LUTRAM | 80 | 148 | +68 |

The nine smoke replies and 36 warm-ups passed. The board ran ABBA across three image loads. The temporary DMA mapping was released before each switch. The original image, HP0/FPD/SMMU words, weights and all 320 original BOS scores passed restoration. Completion time in the record is the first observed complete supervisor receipt.

[Run record](run.json) · [Protocol](../../experiments/kv260-logits-ddr4-prefetch-v1.md)
