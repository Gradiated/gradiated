# Matching the same image at two PL0 rates

Median board-side completion changed -4.99% to -4.98% across the three prompts. Pooled mixed-block gross module energy changed -4.60% per verified answer.

Linux configured PL0 at 50,000,000 Hz and 52,631,579 Hz. Both rates used the same image, model and workload. All 200 timed replies, 36 warm-ups and nine smokes matched the reference output, EOS, work and exact device counters.

The configured rate ratio predicts a -5.00% change in device time for fixed clock counts. The host-inference elapsed time was at least the device-cycle time at each configured rate. That consistency check uses independent CPU timestamps and the configured rate. It provides no external clock-frequency reading.

## Request timing

| Prompt | TTFT, ms | Decode, tokens/s | Completion, ms | Paired completion change | Calculated device completion, ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hello | 5.886 → 5.603 | 1377.233 → 1449.721 | 71.397 → 67.838 | -4.99% to -4.97% | 71.176 → 67.617 |
| Six-byte prompt | 6.971 → 6.626 | 1263.941 → 1330.463 | 103.716 → 98.536 | -5.00% to -4.97% | 103.480 → 98.306 |
| 48-byte prompt | 65.257 → 62.034 | 943.529 → 993.190 | 175.673 → 166.930 | -5.00% to -4.96% | 175.203 → 166.443 |

First, last and completion counters stayed identical at both rates.

| Prompt | Positions | Scores consumed | Skipped positions | First clocks | Last clocks | Completion clocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 101 | 29,120 | 10 | 283,256 | 3,514,339 | 3,558,785 |
| Six-byte prompt | 135 | 39,360 | 12 | 336,800 | 5,123,370 | 5,174,020 |
| 48-byte prompt | 201 | 33,600 | 96 | 3,239,400 | 8,697,576 | 8,760,172 |

## Gross VCC_SOM module energy

| Scope | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | 3.11295 → 3.12456 | 3.01383 → 3.02221 | 0.366122 → 0.349272 | 0.00347584 → 0.00331587 | 287.7 → 301.58 |
| Hello | 3.12018 → 3.12009 | 3.02052 → 3.01549 | 0.224491 → 0.213374 | 0.00249434 → 0.00237083 | 400.907 → 421.794 |
| Six-byte prompt | 3.11628 → 3.11883 | 3.01708 → 3.01363 | 0.325276 → 0.309373 | 0.00266619 → 0.00253585 | 375.066 → 394.345 |
| 48-byte prompt | 3.11203 → 3.11686 | 3.01919 → 3.0158 | 0.548944 → 0.522423 | 0.00527831 → 0.0050233 | 189.455 → 199.072 |

The active integral spans first admission through final verification. The 20 Hz INA260 trace uses a 75 ms contributing-gap limit. Configured-clock probes bracket the active interval. The shifted alignments may include power samples influenced by those probes. The five alignments below show paired gross J/answer changes.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read start | Read end |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -4.83% to -4.34% | -4.73% to -4.19% | -4.91% to -4.32% | -4.83% to -4.34% | -4.83% to -4.34% |
| Hello | -5.15% to -4.75% | -4.66% to -4.59% | -5.22% to -4.74% | -5.15% to -4.75% | -5.16% to -4.75% |
| Six-byte prompt | -5.14% to -4.64% | -5.07% to -4.70% | -5.12% to -4.64% | -5.14% to -4.64% | -5.14% to -4.64% |
| 48-byte prompt | -5.03% to -4.63% | -4.97% to -4.73% | -5.10% to -4.61% | -5.03% to -4.63% | -5.03% to -4.63% |

The sampler missed 0 scheduled slots. All 20 powered blocks passed the gap check.

Peripheral counters changed in `p3-candidate` +672 ms SPI1 and +0 TPM transfers. The brackets do not locate activity inside the active integral.

Temperature brackets ranged ams/temp1 24.5–28.0 °C, ams/temp2 24.9–27.6 °C, ams/temp3 24.0–25.0 °C.

The 3 mixed pairs with steady SPI1 and TPM counters changed gross J/answer by -4.83% to -4.34% at midpoint alignment.

The Mac retained 5 serial status receipts while the supervisor was running. A conservative timing audit found no overlap with the active power windows.

## Routed image and restoration

| Configured PL0 rate | Timing period, ns | Setup slack, ns | Hold slack, ns | Pulse-width slack, ns |
| --- | ---: | ---: | ---: | ---: |
| 50,000,000 Hz | 20.000 | 1.390 | 0.005 | 8.500 |
| 52,631,579 Hz | 18.999 | 0.389 | 0.005 | 7.999 |

The common image uses 39,376 LUTs, 15,712 registers, 58 DSPs and 39 BRAM tiles.

The timing record qualifies the same programmed image at both settings. [Vivado timing evidence](../attention-clock-v1-original-sta-20261120T003417Z/findings.md)

The supervisor verified the original firmware, weights, UIO permissions and all 320 BOS scores. A separate stock receipt reconfirmed the original FPGA image, 50 MHz driver and firmware divider readbacks, overlay and device mapping, empty owner lists and temporary image cleanup. The restored clock fingerprint matched all 198 unrelated clock identities.

[Run record](run.json) · [Protocol](../../experiments/kv260-clock-frequency-v1.md)
