# Reading attention output weights in beats and row bursts

Row bursts cut median completion time by 16.98%–20.24% compared with one DDR4 read per weight, while taking 1.06%–1.32% longer than BRAM. Gross mixed-block energy per answer fell 18.49% versus scalar DDR4 and rose 1.16% versus BRAM. The four modes matched all 400 timed replies, 72 warm-ups and 12 smoke replies. Both the added whole-request FPGA clocks and the added output-projection clocks reconciled to the measured transport waits.

All modes shared the routed 50 MHz fixture, arithmetic and workload. One projection applies a 32-by-32 matrix of signed 16-bit weights. Beat reuse supplies four operands from each 64-bit response. Row reuse serves 32 operands from one eight-beat AXI burst. [Routed fixture](../output-projection-ddr4-burst-build-20261119T105706Z/findings.md) · [Exact RTL replay](../output-projection-ddr4-burst-rtl-20261119T110106Z/findings.md)

| Mode | AR transactions per projection | R beats per projection | AXI bytes | Useful DDR bytes |
| --- | ---: | ---: | ---: | ---: |
| BRAM | 0 | 0 | 0 | 0 |
| DDR scalar | 1,024 | 1,024 | 8,192 | 2,048 |
| DDR beat | 256 | 256 | 2,048 | 2,048 |
| DDR row | 32 | 256 | 2,048 | 2,048 |

AXI bytes describe the HP0 interface. The experiment used no DDR-controller traffic counter. Added clocks equal twice the number of accepted addresses plus address stalls, response waits and accepted nonfinal beats. The BRAM projection itself takes 2,112 clocks per invocation.

| Mode | Median address stalls | Median response waits | Nonfinal beats | Median added clocks |
| --- | ---: | ---: | ---: | ---: |
| BRAM | 0.00 | 0.00 | 0.00 | 0.00 |
| DDR scalar | 0.00 | 11,733.24 | 0.00 | 13,781.24 |
| DDR beat | 0.00 | 2,917.15 | 0.00 | 3,429.15 |
| DDR row | 0.00 | 383.77 | 224.00 | 671.77 |

Each entry is per projection invocation, calculated on each mixed reply and then summarized over replies. The row burst removed about 95% of the FPGA clocks added by scalar DDR reads. It also cut the extra clocks by about 80% compared with beat reuse, at the same AXI byte count.

## Mixed timing and FPGA clocks

Eight timed observations per prompt and mode. Values are medians. The board CPU observed the first byte, useful-byte stream and completion. The hardware autonomously recorded its own clocks.

| Prompt | Mode | First byte, ms | Decode, tokens/s | Completion, ms | Request clocks | Added projection clocks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Hello | BRAM | 8.564 | 954.4 | 103.100 | 5,142,970 | 0 |
| Hello | DDR scalar | 11.623 | 755.6 | 130.969 | 6,535,250 | 1,392,280 |
| Hello | DDR beat | 9.311 | 895.7 | 110.022 | 5,489,420 | 346,450 |
| Hello | DDR row | 8.718 | 942.3 | 104.463 | 5,210,814 | 67,844 |
| Six-byte prompt | BRAM | 10.145 | 875.9 | 149.749 | 7,475,095 | 0 |
| Six-byte prompt | DDR scalar | 13.741 | 705.6 | 186.969 | 9,335,690 | 1,860,595 |
| Six-byte prompt | DDR beat | 11.039 | 826.3 | 159.003 | 7,938,026 | 462,932 |
| Six-byte prompt | DDR row | 10.313 | 865.7 | 151.557 | 7,565,842 | 90,747 |
| 48-byte prompt | BRAM | 95.403 | 653.4 | 254.835 | 12,716,857 | 0 |
| 48-byte prompt | DDR scalar | 122.148 | 553.7 | 310.236 | 15,486,449 | 2,769,592 |
| 48-byte prompt | DDR beat | 102.061 | 625.4 | 268.626 | 13,405,932 | 689,075 |
| 48-byte prompt | DDR row | 96.720 | 647.8 | 257.548 | 12,851,802 | 134,945 |

| Prompt | Beat vs scalar completion | Row vs beat | Row vs scalar | Row vs BRAM | Row added FPGA ms | Row added wall ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | -16.13% to -15.96% | -5.07% to -5.02% | -20.37% to -20.20% | +1.28% to +1.36% | 1.357 | +1.364 |
| Six-byte prompt | -15.01% to -14.93% | -4.69% to -4.67% | -18.99% to -18.92% | +1.20% to +1.21% | 1.815 | +1.808 |
| 48-byte prompt | -13.42% to -13.40% | -4.13% to -4.12% | -16.99% to -16.97% | +1.05% to +1.07% | 2.699 | +2.713 |

Each range spans the four within-round changes in median completion time. Comparing row and beat isolates the change in address issue and burst response schedule with the same AXI payload bytes.

## Gross module energy

The INA260 measured the VCC_SOM rail. Active power divides pooled energy by pooled active block time. Gross energy per answer and per token divide summed joules by the corresponding completed work, including context clear, request gaps and verification. Idle power averages the equal-duration ready-idle windows. Mixed and single-prompt blocks use separate pools.

| Mode | Active W | Ready-idle W | Gross J/answer | J/output token | Tokens/J |
| --- | ---: | ---: | ---: | ---: | ---: |
| BRAM | 3.1125 | 3.0184 | 0.529261 | 0.00502463 | 199.02 |
| DDR scalar | 3.1244 | 3.0174 | 0.656895 | 0.00623634 | 160.35 |
| DDR beat | 3.1107 | 3.0222 | 0.559991 | 0.00531637 | 188.10 |
| DDR row | 3.1127 | 3.0172 | 0.535414 | 0.00508304 | 196.73 |

Relative to scalar mode, row mode changed total mixed-block duration by -18.19% and active power by -0.37%. Both changes enter the gross block energy.

| Prompt | Mode | Replies per block | Gross J/answer | J/output token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: |
| Hello | BRAM | 18 | 0.322586 | 0.00358428 | 279.00 |
| Hello | DDR scalar | 18 | 0.410446 | 0.00456051 | 219.27 |
| Hello | DDR beat | 18 | 0.344422 | 0.00382691 | 261.31 |
| Hello | DDR row | 18 | 0.326731 | 0.00363034 | 275.46 |
| Six-byte prompt | BRAM | 12 | 0.469204 | 0.00384594 | 260.01 |
| Six-byte prompt | DDR scalar | 12 | 0.587069 | 0.00481204 | 207.81 |
| Six-byte prompt | DDR beat | 12 | 0.498206 | 0.00408366 | 244.88 |
| Six-byte prompt | DDR row | 12 | 0.473220 | 0.00387885 | 257.81 |
| 48-byte prompt | BRAM | 8 | 0.794358 | 0.00763806 | 130.92 |
| 48-byte prompt | DDR scalar | 8 | 0.969168 | 0.00931892 | 107.31 |
| 48-byte prompt | DDR beat | 8 | 0.837689 | 0.00805471 | 124.15 |
| 48-byte prompt | DDR row | 8 | 0.803757 | 0.00772843 | 129.39 |

| Scope | Beat vs scalar J/answer | Row vs beat | Row vs scalar | Row vs BRAM | Row vs scalar five-alignment range |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -15.36% to -14.35% | -4.60% to -4.01% | -19.25% to -17.78% | +0.67% to +1.86% | -19.28% to -17.75% |
| Hello | -16.10% to -16.08% | -5.14% to -5.13% | -20.40% to -20.39% | +1.26% to +1.31% | -20.42% to -20.37% |
| Six-byte prompt | -15.36% to -14.91% | -5.27% to -4.76% | -19.40% to -19.39% | +0.82% to +0.89% | -19.42% to -19.38% |
| 48-byte prompt | -13.75% to -13.38% | -4.17% to -3.93% | -17.35% to -16.78% | +0.80% to +1.57% | -17.38% to -16.78% |

SPI1 active time increased by 1,033 ms in the fourth mixed row-mode bracket and by 1,807 ms in the second six-byte BRAM bracket. In the first 48-byte row-mode bracket, SPI1 active time increased by 294 ms and TPM logged 104 transfers. The other 37 brackets recorded zero change in both counters. These brackets include the reading edges and cannot isolate peripheral energy. All four mixed row/BRAM pairs are shown, including the three with steady SPI1 and TPM counters.

## Routed resources and restoration

| Routed resource, all four modes | Used / available | Utilization | Change from Experiment 14 fixture |
| --- | ---: | ---: | ---: |
| LUTs | 39,133 / 117,120 | 33.41% | +273 |
| Registers | 15,362 / 234,240 | 6.56% | +512 |
| DSPs | 41 / 1,248 | 3.29% | 0 |
| Block RAM tiles | 39 / 144 | 27.08% | 0 |

The worst setup and hold slacks were 4.826 ns and 0.014 ns at the 20 ns target. Both fixtures retain the same BRAM matrix, so the resource change covers the added reuse paths and control. [Experiment 14 routed fixture](../output-projection-ddr4-build-20261118T225153Z/findings.md)

The DMA setup range across the 40 powered arms was 0.581–0.618 ms, before warm-up. Linux reported a 50 MHz PL clock. Temperatures were sampled before and after each powered arm. The three AMS channels showed first, last and maximum sampled values of 25.6 / 25.3 / 27.3 °C, 26.8 / 26.5 / 27.6 °C and 25.1 / 24.5 / 25.1 °C respectively.

The original image and weights were restored after the final verified DMA release. All 320 original BOS scores matched. Final kernel taint was 12288. Evidence covers this board and boot. Experiment 13 remains the selected circuit comparison baseline.

[Run record](run.json) · [Protocol](../../experiments/kv260-output-projection-ddr4-burst-v1.md)
