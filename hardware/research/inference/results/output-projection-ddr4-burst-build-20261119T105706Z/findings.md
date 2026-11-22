# Routed DDR4 burst fixture at 50 MHz

Vivado routed BRAM, a single-weight DDR4 read, reuse of all four weights in one beat, and an eight-beat row burst into one comparison image. The 64-bit AXI4 master connects directly to native PS HP0. It uses the unremapped low 2 GiB DDR aperture on PL0. All three low `ARLEN` bits share one routed register output and the other bits are grounded. The resulting lengths are one and eight beats. The native port carries an incrementing 8-byte beat, ID 0 and nonsecure data protection. Its write address and data valid pins are grounded. The [exact RTL replay](../output-projection-ddr4-burst-rtl-20261119T110106Z/findings.md) checks lengths, lane and row ordering, bounds and fault recovery.

| Routed resource or timing | Exp14 fixture | Exp15 fixture |
| --- | ---: | ---: |
| LUTs | 38,860 | 39,133 |
| Registers | 14,850 | 15,362 |
| DSPs | 41 | 41 |
| Block RAM tiles | 39 | 39 |
| Setup slack at 20 ns | +4.521 ns | +4.826 ns |
| Hold slack at 20 ns | +0.005 ns | +0.014 ns |

The combined fixture adds 273 LUTs and 512 registers. One RAMB18E2 still holds the original BRAM control matrix. The complete route has zero routing gaps, unconstrained internal endpoints, or design-rule errors and critical warnings. Generation logged the expected excluded HP0 segments and absent write-user signal. Synthesis reported unused HP0 write outputs. The native audit confirmed the read clock and active read channels.

The ordered generated PS register writes match Exp14 exactly. The AFI/UIO and restoration overlays are byte-identical to Exp14. The new program overlay names this firmware, and the new direct DMA overlay identifies the burst driver with the same register window and verified direct mapping marker. The admitted archive was recovered to the Mac and checked against its byte and member hashes. The converted firmware matched an independent reconstruction from the raw bitstream. The generation-only preflight `output-projection-ddr4-burst-preflight-20261119T105446Z` is retained separately.

Timing and resources describe the combined implementation. Per-mode area and physical performance require separate evidence.

[Run record](run.json) · [Verified artifact manifest](audit-manifest.json) · [Exp14 routed reference](../output-projection-ddr4-build-20261118T225153Z/findings.md) · [Build and recovery instructions](../../implementations/kv260/variants/output-projection-ddr4-burst-v1/build/README.md)
