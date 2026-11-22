# Running two exponentials at once in attention

The candidate evaluates two adjacent scores at a time within one head. Each unit has its own copy of the 257-word lookup table. Results still reach the running sum in score order. The final score projection, software, model and clock target were shared. [Routed implementation](../attention-exp-pair-v2-build-20261117T225852Z/findings.md)

All 36 timed requests and 18 warm-ups matched their reference outputs. The 108 board counters matched the respective RTL first, last and completion clocks at 50 MHz. Across the three prompts the two units saved 4.54–6.93% of complete-request clocks. [RTL comparison](../attention-exp-pair-v2-rtl-20261117T230104Z/findings.md)

The RTL replay below shows the exponential schedule at selected points in the same 256-position request. Results for one-position heads and odd tails still use a single unit. Both-unit occupancy counts time when both units are calculating, excluding the time that a finished result waits for its turn to be written.

| Context positions | Serial exponential clocks | Paired exponential clocks | Both units calculating |
| ---: | ---: | ---: | ---: |
| 1 | 102 | 102 | 0% |
| 3 | 306 | 208 | 46.2% |
| 16 | 1,632 | 848 | 90.6% |
| 64 | 6,480 | 3,391 | 89.2% |
| 128 | 12,960 | 6,782 | 89.2% |
| 255 | 25,722 | 13,559 | 87.8% |
| 256 | 25,824 | 13,566 | 88.5% |

## Board timing

Six timed samples per arm and prompt, measured at the board. The last column shows the full range of the three paired completion-time changes. These wall times are observed by the CPU on the board. The FPGA separately records its own clock counts.

| Prompt | Time to first token, ms | Decode, output tokens/s | Time to complete, ms | Pairwise completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 8.616 → 8.554 (-0.72%) | 908.2 → 954.4 (+5.08%) | 107.987 → 103.090 (-4.53%) | -4.56% to -4.52% |
| Six-byte prompt | 10.236 → 10.146 (-0.88%) | 824.8 → 875.9 (+6.19%) | 158.524 → 149.750 (-5.53%) | -5.56% to -5.52% |
| 48-byte prompt | 99.995 → 95.394 (-4.60%) | 599.6 → 653.4 (+8.97%) | 273.765 → 254.828 (-6.92%) | -6.92% to -6.91% |

## Module energy and routed resources

Gross VCC_SOM energy per verified answer averaged 0.565601 J with one exponential unit and 0.532596 J with two exponential units. The three paired block changes were -5.46%, -6.05%, -5.99%. Across five sample alignments in each pair, the range was -6.12% to -5.46%. Mean active module power was 3.1285 W and 3.1346 W respectively. Mean idle power was 3.0340 W and 3.0390 W. Energy per useful output token was 0.00536963 J and 0.00505629 J. These figures describe one board boot and measure the module rail, including inter-request gaps and verification.

| Routed resource | One exponential unit | Two exponential units |
| --- | ---: | ---: |
| LUTs | 34516 (29.47%) | 38329 (32.73%) |
| Registers | 13581 (5.80%) | 14464 (6.17%) |
| DSPs | 37 (2.96%) | 41 (3.29%) |
| Block RAM tiles | 38 (26.39%) | 39 (27.08%) |

## Peripheral checks and restoration

| Arm | SPI1 active time change, ms | TPM transfer change | Before / after bracket gaps, ms |
| --- | ---: | ---: | ---: |
| p1-candidate | 0 | 0 | 0.191 / 0.015 |
| p1-control | 0 | 0 | 0.218 / 0.014 |
| p2-candidate | 0 | 0 | 0.224 / 0.015 |
| p2-control | 0 | 0 | 0.191 / 0.021 |
| p3-candidate | 0 | 0 | 0.224 / 0.019 |
| p3-control | 1086 | 0 | 0.191 / 0.014 |

The first two pairs showed 5.46% and 6.05% lower module energy per answer, with both peripheral counters steady. SPI1 active time increased by 1,086 ms across the third control bracket, with zero recorded TPM transfers. The third pair stays in the table. Its measured difference may include energy from that peripheral state. The module trace cannot isolate that contribution.

The original 50 MHz research circuit and weights were restored. All 320 original BOS scores and the separate post-restoration UART, overlays and clock checks passed.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Protocol](../../experiments/kv260-attention-exp-pair-v2.md)
