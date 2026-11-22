# Reading attention output weights from DDR4

Fetching each attention output weight from DDR4 increased median complete-answer time by 21.73%–27.00% across the three prompts. The added FPGA clocks matched the clocks spent waiting for output weights on every request. All 188 timed replies matched the frozen outputs and stop reasons. The mixed workload contributed 36 timed replies and 18 warm-ups. The single-prompt energy blocks contributed 152 timed replies and 12 warm-ups. Six smoke replies passed before timing.

Both modes used the same routed circuit at 50 MHz. BRAM mode reproduced the adopted Experiment 13 cycle counts. DDR4 mode sent one read at a time through HP0 and selected one signed 16-bit value from each aligned 64-bit response. One projection consumed 2,048 useful bytes in 1,024 responses carrying 8,192 bytes at the AXI interface. [RTL comparison](../output-projection-ddr4-rtl-20261118T225153Z/findings.md) · [Routed build](../output-projection-ddr4-build-20261118T225153Z/findings.md)

## Work and timing

The table shows six timed observations per mode and prompt. TTFT starts at board CPU admission before encoding and any previous-context clear. Decode counts useful byte intervals from first to last output. Completion ends at the observed stop and drain.

| Prompt | Input IDs including BOS | Useful output tokens | Positions | Stop reason |
| --- | ---: | ---: | ---: | --- |
| Hello | 11 | 90 | 101 | eos |
| Six-byte prompt | 13 | 122 | 135 | eos |
| 48-byte prompt | 97 | 104 | 201 | eos |

| Prompt | TTFT, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 8.570 → 11.601 (+35.37%) | 954.4 → 755.6 (-20.83%) | 103.106 → 130.945 (+27.00%) | +26.96% to +27.01% |
| Six-byte prompt | 10.155 → 13.739 (+35.29%) | 875.9 → 705.6 (-19.45%) | 149.759 → 186.958 (+24.84%) | +24.83% to +24.84% |
| 48-byte prompt | 95.421 → 122.145 (+28.01%) | 653.4 → 553.7 (-15.26%) | 254.854 → 310.241 (+21.73%) | +21.73% to +21.73% |

| Prompt | DDR reads and beats | DDR AXI bytes | Median added cycles | Median cycles per weight | Median request cycles, BRAM → DDR4 | Added FPGA / wall ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 103,424 | 827,392 | 1,392,130 | 13.46 | 5,142,970 → 6,535,100 | 27.843 / 27.840 |
| Six-byte prompt | 138,240 | 1,105,920 | 1,860,396 | 13.46 | 7,475,095 → 9,335,492 | 37.208 / 37.199 |
| 48-byte prompt | 205,824 | 1,646,592 | 2,769,842 | 13.46 | 12,716,857 → 15,486,700 | 55.397 / 55.388 |

The two transport clocks per read, address stalls and response waits sum to the extra projection clocks. No address stalls occurred in the 18 timed DDR4 mixed-workload replies. Each read added about 13.46 clocks, made up of two transport clocks and about 11.46 clocks waiting for the response. The total projection counter was 2,112 cycles per position plus the added clocks. The bus count measures transfers at the PL/PS boundary. The run collected no DDR controller traffic counter. Matrix allocation, upload and mode selection took 0.508–0.543 ms across the six arms, before warm-up.

## Module energy

INA260 recorded the VCC_SOM module rail in six-reply mixed blocks with two matched ready-idle windows per mode and pair. Gross energy includes the request gaps and verification within each block. Pooled energy ratios divide summed block joules by total answers or useful tokens. Active power divides summed joules by summed block time. Idle power averages equal-length windows.

| Metric | BRAM | DDR4 | Change |
| --- | ---: | ---: | ---: |
| Gross active power, W | 3.1229 | 3.1372 | +0.46% |
| Ready-idle power, W | 3.0343 | 3.0376 | +0.11% |
| Gross energy per answer, J | 0.531005 | 0.659372 | +24.17% |
| Gross energy per output token, J | 0.00504118 | 0.00625986 | +24.17% |
| Output tokens per joule | 198.37 | 159.75 | -19.47% |

DDR4 changed total active block time by +23.61% and average active power by +0.46%. Gross energy reflects both changes. Paired gross energy per verified answer changed +24.28%, +24.25%, +23.99%. The five sample alignments across all pairs gave changes from +23.91% to +24.34%.

| Block | SPI1 active-time change, ms | TPM transfer change | Before / after gaps, ms |
| --- | ---: | ---: | ---: |
| p1-bram | 0 | 0 | 0.221 / 0.131 |
| p1-ddr | 0 | 0 | 0.188 / 0.135 |
| p2-ddr | 0 | 0 | 0.228 / 0.135 |
| p2-bram | 0 | 0 | 0.189 / 0.127 |
| p3-bram | 1,022 | 0 | 0.195 / 0.122 |
| p3-ddr | 0 | 0 | 0.197 / 0.128 |

SPI1 active time increased by 1,022 ms in the third BRAM block bracket. TPM transfers stayed unchanged in all six mixed brackets. The counters include the bracket edges and cannot isolate SPI1 energy.

### Single-prompt energy

Two matched pairs per prompt, with one untimed warm-up per block. The historical mixed timing samples remain separate. The question here is the gross energy cost of repeating one verified prompt at a time.

| Prompt | Replies per block | J/answer, BRAM → DDR4 | J/output token, BRAM → DDR4 | Paired J/answer changes | Five-alignment range |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hello | 18 | 0.325135 → 0.413778 | 0.00361261 → 0.00459753 | +27.52%, +27.01% | +27.01% to +27.52% |
| Six-byte prompt | 12 | 0.471336 → 0.589813 | 0.00386341 → 0.00483454 | +24.92%, +25.35% | +24.92% to +25.36% |
| 48-byte prompt | 8 | 0.798944 → 0.976818 | 0.00768215 → 0.00939248 | +22.12%, +22.41% | +22.02% to +22.44% |

SPI1 active time increased by 395 ms in the second 48-byte DDR4 block bracket. TPM transfers stayed unchanged in all twelve single-prompt brackets.

## Resources and restoration

| Routed resource, both modes | Used | Available | Utilization | Change from adopted control |
| --- | ---: | ---: | ---: | ---: |
| LUTs | 38,860 | 117,120 | 33.18% | +531 |
| Registers | 14,850 | 234,240 | 6.34% | +386 |
| DSPs | 41 | 1,248 | 3.29% | +0 |
| Block RAM tiles | 39 | 144 | 27.08% | +0 |

Worst setup slack was 4.521 ns and worst hold slack was 0.005 ns at the 20 ns clock constraint. The fixture retains the BRAM bank and adds the DDR4 reader. The host owns a private page for the 2 KiB packed weights. A DDR4-only route would establish the resource savings from removing the BRAM bank.

The original research image and weights passed restoration, including all 320 BOS scores. The module was unloaded after verified DMA release. Final kernel taint on the measured boot was 12288. Evidence covers this board, boot and three fixed prompts.

The first attempt stopped before inference when the kernel rejected a 31-bit direct DMA mask. The retry negotiated a 32-bit mask, then checked the entire mapped range against the same routed 2 GiB DDR aperture before programming the base. [Probe-aborted attempt](../output-projection-ddr4-20261118T231117Z-e79741/findings.md)

Temperature snapshots taken before and after the arms covered three AMS channels. ams/temp1 26.3 °C first, 25.5 °C last, 26.6 °C maximum observed. ams/temp2 26.9 °C first, 25.7 °C last, 27.0 °C maximum observed. ams/temp3 24.5 °C first, 24.4 °C last, 24.8 °C maximum observed.

The selected circuit comparison baseline remains Experiment 13’s attention-exp-pair-v2.

[Run record](run.json) · [Protocol](../../experiments/kv260-output-projection-ddr4-v1.md)
