# Routed DDR4 output-projection fixture at 50 MHz

Vivado 2025.2 routed both memory modes into one KV260 image. The native AXI4 read master connects directly to PS HP0 on `clk_pl_0`. Both interfaces use 64-bit data, 49-bit addresses and six-bit IDs. The assigned aperture is the 2 GiB low DDR segment. The routed PS8 checkpoint shows read ID and write-address valid held at zero, nonsecure data protection `010`, and a single 8-byte beat per read. The [RTL run](../output-projection-ddr4-rtl-20261118T225153Z/findings.md) covers the operand selection and both modes.

| Routed resource or timing | Adopted pair-v2 | DDR4 fixture |
| --- | ---: | ---: |
| LUTs | 38,329 | 38,860 |
| Registers | 14,464 | 14,850 |
| DSPs | 41 | 41 |
| Block RAM tiles | 39 | 39 |
| Setup slack at 20 ns | +5.544 ns | +4.521 ns |
| Hold slack at 20 ns | +0.012 ns | +0.005 ns |

The fixture adds 531 LUTs and 386 registers and retains one RAMB18E2 for the BRAM control matrix. These are whole-image costs. A separate DDR4-only route would be needed to measure BRAM savings. The routed report lists zero design-rule errors or critical warnings, routing gaps and unconstrained internal endpoints. Generation logged the read-only project lock and stale module-reference warnings before copying the project and refreshing the reference. It also flagged the excluded HP0 address segments and the absent AXI write-user signal. Synthesis reported the unused HP0 write-response ports. The routed audit confirms the write-address channel is held inactive.

The generated PS init adds only the HP0 width fields at `0xfd380000` and `0xfd380014`. The candidate interface overlay sets both to 64-bit mode. The DMA overlay inside the recovered Vivado archive is a template. The separately compiled `kv260-ddr4-dma-direct.dtbo` includes the driver's verified direct mapping marker for the checked boot. The AFI restore overlay returns both width fields to the captured zero setting, with exact register readback handled separately during board qualification.

The `output-projection-ddr4-preflight-20261118T224353Z` attempt validated interface generation using stub master ports. The `output-projection-ddr4-build-20261118T224726Z` attempt stopped during synthesis after review found that its AXI protection bits requested secure reads. The corrected build and firmware conversion completed in 988 seconds. The Mac recovered the archive after resuming one interrupted SSH stream and verified all 384 archived files and the converted firmware payload. This record covers offline implementation. Board timing and energy belong to the physical run.

[Run record](run.json) · [Verified artifact manifest](audit-manifest.json) · [Adopted routed control](../attention-exp-pair-v2-build-20261117T225852Z/findings.md) · [Build and recovery instructions](../../implementations/kv260/variants/output-projection-ddr4-v1/build/README.md)
