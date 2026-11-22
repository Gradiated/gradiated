# Routed final-score DDR4 comparison at 50 MHz

The separate DDR4 candidate removes all eight RAMB36E2 banks for the 20 KiB final-score matrix. Total mapped use falls from 39 to 31 BRAM tiles, a 20.5% reduction for this circuit. The input embedding table still occupies its original six RAMB36E2 and one RAMB18E2. All eight final-score DSPs remain in the candidate.

| Routed resource or timing | Exp13 BRAM control | Exp16 DDR4 candidate |
| --- | ---: | ---: |
| FPGA LUTs | 38,329 | 38,978 |
| FPGA registers | 14,464 | 14,844 |
| FPGA DSPs | 41 | 41 |
| FPGA BRAM tiles | 39 | 31 |
| Accelerator LUTs | 37,746 | 38,394 |
| Accelerator registers | 13,754 | 14,134 |
| Logits LUTs | 1,156 | 1,217 |
| Logits registers | 665 | 667 |
| Logits DSPs | 8 | 8 |
| Logits RAMB36E2 | 8 | 0 |
| Setup slack at 20 ns | +5.544 ns | +5.215 ns |
| Hold slack at 20 ns | +0.012 ns | +0.012 ns |

The new reader occupies 302 LUTs, including 80 LUTRAM LUTs, and 73 registers. It uses two 32×64-bit local storage banks for one 512-byte group. The reader has zero BRAM, URAM and DSPs. Both scorers use 10 LUTRAM LUTs for the input vector. The whole-device LUT and register deltas include the control and integration logic.

The reused Exp13 control matches all eleven exact RTL input hashes. A fresh census re-opened its archived routed checkpoint in the same Vivado version on the same K26 part and confirmed its complete 20 ns route. The candidate's direct native 64-bit HP0 uses PL0, ID zero, nonsecure data, and eight-beat incrementing reads. The assigned segment is the unremapped low 2 GiB of DDR. At the last admitted base, the final 64-byte burst starts at `0x7fffffc0` and ends at `0x7fffffff`. The [exact RTL replay](../logits-ddr4-burst-rtl-20261119T120140Z/findings.md) verifies address and operand order. Candidate reports show zero routing gaps, unconstrained internal endpoints and design-rule errors or critical warnings. Vivado warned about deliberately excluded HP0 segments and unused write-channel signals.

The candidate's generated PS register writes match Exp15. Its interface and AFI restoration overlays are byte-identical to Exp15. The new program overlay names the candidate bitstream and the direct DMA overlay matches the logits driver. The Mac verified the firmware and route evidence from a small subset within the original recovery window. The full archive timed out in transfer. Recovery resumed from the retained bytes under the approved extension, and all 386 full-archive members verified. The transfer extension is separate from the synthesis and route elapsed time. The build and RTL records pin the protocol bytes admitted for those runs. A later wording clarification describes the physical driver's DMA allocation.

These results establish mapped resource use and timing closure. Physical inference timing, power and DDR service latency are measured on the board.

[Run record](run.json) · [Verified artifact manifest](audit-manifest.json) · [Reused Exp13 route](../attention-exp-pair-v2-build-20261117T225852Z/findings.md) · [Build and recovery](../../implementations/kv260/variants/logits-ddr4-burst-v1/build/README.md)
