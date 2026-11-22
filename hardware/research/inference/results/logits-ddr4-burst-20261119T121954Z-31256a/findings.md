# Moving the final-score weight matrix to DDR4

The DDR4 candidate matched all 200 timed replies and restored the original research image and its 320 BOS scores. The routed design changed block RAM use from 39 to 31 tiles. Gross mixed-block module energy per verified answer changed +8.55%. The input embedding table stayed on-chip. The Mac serial connection paused during the run. Completion and restoration were verified from the checksummed board outcome, supervisor log and a fresh stock-state readback. The record uses the first resumed stock-state readback time as an upper bound on completion. [Routed build and hierarchy census](../logits-ddr4-burst-build-20261119T115915Z/findings.md) · [Exact RTL replay](../logits-ddr4-burst-rtl-20261119T120140Z/findings.md)

## Mixed timings and the scored positions

Eight observations per mode and prompt. Each entry shows the median from on-chip to DDR4. First-byte and completion times are measured by the board CPU. Decode counts useful output byte intervals.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 8.558 → 8.694 (+1.58%) | 954.4 → 848.3 (-11.12%) | 103.095 → 115.033 (+11.58%) | +11.57% to +11.61% |
| Six-byte prompt | 10.146 → 10.305 (+1.57%) | 875.9 → 785.7 (-10.30%) | 149.750 → 165.900 (+10.78%) | +10.76% to +10.79% |
| 48-byte prompt | 95.407 → 95.546 (+0.15%) | 653.4 → 601.9 (-7.89%) | 254.839 → 268.617 (+5.41%) | +5.40% to +5.42% |

| Prompt | Fully scored positions | Accepted AR | Accepted R beats | HP0 bytes | Median R waits | Median AR stalls | Median added FPGA clocks | FPGA time added, ms | HP0 MB/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 91 | 29,120 | 232,960 | 1,863,680 | 334,262 | 0 | 596,342 | 11.927 | 124.37 |
| Six-byte prompt | 123 | 39,360 | 314,880 | 2,519,040 | 451,592 | 0 | 805,832 | 16.117 | 124.40 |
| 48-byte prompt | 105 | 33,600 | 268,800 | 2,150,400 | 385,880 | 0 | 688,280 | 13.766 | 124.35 |

Each complete scoring projection uses 40 groups of eight rows. It issues 320 burst addresses, accepts 2,560 beats and consumes 20,480 useful bytes. Prompt-only steps that skip final scores neither issue reads nor consume matrix bytes. The candidate adds 2,880 launch and staging clocks per fully scored position, plus measured address stalls and response waits. That sum matched the entire added request time in FPGA clocks on every reply. The on-chip control reproduced the selected circuit's exact first, last and complete request counters. HP0 throughput divides accepted bytes by projection busy time at 50 MHz.

## Gross VCC_SOM energy

The 20 powered blocks used matched ready-idle brackets. Mixed blocks and single-prompt blocks are pooled separately. Active watts divide integrated joules by block time and idle watts average the settled brackets. The same gross block joules are divided by verified answers and by useful tokens. The sequential calculation uses no independent DDR-only power sensor.

| Scope | Mode | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | On-chip | 3.1138 | 3.0279 | 0.529107 | 0.00502316 | 199.08 |
| Mixed | DDR4 | 3.1214 | 3.0267 | 0.574331 | 0.00545251 | 183.40 |
| Hello | On-chip | 3.1189 | 3.0251 | 0.323345 | 0.00359272 | 278.34 |
| Hello | DDR4 | 3.1205 | 3.0268 | 0.361121 | 0.00401246 | 249.22 |
| Six-byte prompt | On-chip | 3.1163 | 3.0292 | 0.468762 | 0.00384231 | 260.26 |
| Six-byte prompt | DDR4 | 3.1271 | 3.0269 | 0.521243 | 0.00427248 | 234.06 |
| 48-byte prompt | On-chip | 3.1167 | 3.0279 | 0.796527 | 0.00765891 | 130.57 |
| 48-byte prompt | DDR4 | 3.1198 | 3.0253 | 0.840681 | 0.00808347 | 123.71 |

| Scope | Paired change in gross J/answer | Five-alignment range |
| --- | ---: | ---: |
| Mixed | +8.41% to +8.79% | +8.39% to +8.84% |
| Hello | +11.65% to +11.71% | +11.65% to +11.72% |
| Six-byte prompt | +11.01% to +11.39% | +11.00% to +11.41% |
| 48-byte prompt | +5.44% to +5.65% | +5.43% to +5.65% |

A contiguous energy block includes inter-reply verification and counter-check gaps. The median sum of the in-block post-verification check times in the mixed blocks was 0.145 ms on-chip and 0.766 ms on DDR4. Only the candidate reads the DDR-specific counters. The per-reply completion times end earlier. homogeneous-p1-encoded-fu2p2q-ddr logged +2,001 ms of SPI1 active time and +0 TPM transfers. homogeneous-p2-encoded-fu2p2q-bram logged +690 ms of SPI1 active time and +106 TPM transfers.

## Resources and operating conditions

| Resource | On-chip | DDR4 | Change |
| --- | ---: | ---: | ---: |
| LUTs | 38,329 | 38,978 | +649 |
| Registers | 14,464 | 14,844 | +380 |
| DSPs | 41 | 41 | +0 |
| Block RAM tiles | 39 | 31 | -8 |

The candidate retains the on-chip input embedding and adds a 512-byte staging buffer for each group. Exact hierarchy counts and timing slacks are in the routed build. Median native model setup was 570.3 ms on-chip and 568.1 ms on DDR4. The separate DMA page allocation, upload and mode setup took 0.655–0.688 ms. Neither setup enters the timed arms. ams/temp1 first/last/max 27.7/27.0/29.7 °C. ams/temp2 first/last/max 27.8/28.1/28.8 °C. ams/temp3 first/last/max 25.9/25.7/26.6 °C.

Nine smoke replies and 36 warm-ups passed. The four logical sessions ran in ABBA order with three comparison image loads on one boot. After the last checked DMA release, the original FPGA image, HP0 state, weights and all 320 original BOS scores passed restoration. Kernel taint remained 12288, the same value admitted after Experiment 15. Experiment 13 remains selected.

[Run record](run.json) · [Executed protocol](../../experiments/kv260-logits-ddr4-burst-v1.md)
