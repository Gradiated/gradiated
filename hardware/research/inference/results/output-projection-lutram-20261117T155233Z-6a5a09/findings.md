# Moving one weight matrix from block RAM to LUTRAM

Moving this matrix freed one RAMB18 (half a block RAM tile) and used 397 more LUTs and seven more registers. With the same access schedule and 50 MHz clock, both designs used exactly the same number of cycles, and measured decode rates were effectively unchanged. The three paired energy changes went in both directions, so this run shows no consistent module-energy advantage. Both builds met timing, and the routed reports do not isolate the delay from the target memory to its arithmetic operands. The `attention-exp-div-v1` circuit remains the comparison baseline.

The candidate moved the 2 KiB output-projection weight array from one RAMB18E2 to LUTRAM. The routed census lists 16 RAM64M, 32 RAM64M8, 320 RAMD64E under the target. These names can include both primitive groupings and leaf cells. The remaining 1,582 named memory cells matched exactly. [Routed implementation](../output-projection-lutram-build-20261117T151934Z/findings.md)

All 36 timed requests and 18 warm-ups matched their reference outputs. Both circuits used exactly the same 108 first, last and completion counters at 50 MHz. The directed dense test and all seven exact RTL cases also matched. [RTL comparison](../output-projection-lutram-rtl-20261117T152505Z/findings.md)

## Board timing

Six timed samples per arm and prompt, measured at the board. The last column shows the full range of the three paired completion-time changes. These wall-time samples include CPU-side observation while the internal clock counts are equal.

| Prompt | Time to first token, ms | Decode, output tokens/s | Time to complete, ms | Pairwise completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 8.628 → 8.653 (+0.29%) | 908.2 → 908.2 (0.00%) | 108.000 → 108.025 (+0.02%) | -0.01% to +0.02% |
| Six-byte prompt | 10.227 → 10.218 (-0.08%) | 824.8 → 824.8 (0.00%) | 158.514 → 158.506 (-0.01%) | -0.02% to +0.01% |
| 48-byte prompt | 99.995 → 99.992 (0.00%) | 599.6 → 599.6 (0.00%) | 273.766 → 273.762 (0.00%) | within 0.005% |

## Module energy and routed resources

Gross VCC_SOM energy per verified answer averaged 0.562792 J with block RAM and 0.562571 J with LUTRAM. The three paired block changes were -0.33%, +0.19%, +0.02%. Across five sample alignments in each pair, the range was -0.38% to +0.21%. Mean active module power was 3.1130 W and 3.1116 W respectively. Mean idle power was 3.0161 W and 3.0203 W. Energy per useful output token was 0.00534296 J and 0.00534086 J. These figures describe one board boot and measure the module rail, including inter-request gaps and verification.

| Routed resource | Block RAM design | LUTRAM design |
| --- | ---: | ---: |
| LUTs | 34516 (29.47%) | 34913 (29.81%) |
| Registers | 13581 (5.80%) | 13588 (5.80%) |
| DSPs | 37 (2.96%) | 37 (2.96%) |
| Block RAM tiles | 38 (26.39%) | 37.5 (26.04%) |

## Peripheral checks and restoration

| Arm | SPI1 active time change, ms | TPM transfer change | Before / after bracket gaps, ms |
| --- | ---: | ---: | ---: |
| p1-candidate | 0 | 0 | 0.188 / 0.023 |
| p1-control | 0 | 0 | 0.253 / 0.020 |
| p2-candidate | 0 | 0 | 0.235 / 0.014 |
| p2-control | 0 | 0 | 0.225 / 0.014 |
| p3-candidate | 0 | 0 | 0.202 / 0.019 |
| p3-control | 0 | 0 | 0.200 / 0.019 |

The reads bracket the active energy window. All six blocks remain in the comparison. SPI1 active time and transfer counts describe peripheral activity. The energy trace cannot isolate that peripheral's contribution.

The original 50 MHz research circuit and weights were restored. All 320 original BOS scores and the separate post-restoration UART, overlays and clock checks passed.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Protocol](../../experiments/kv260-output-projection-lutram-v1.md)
