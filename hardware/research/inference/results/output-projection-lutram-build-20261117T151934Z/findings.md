# Routed block RAM and LUTRAM comparison at 50 MHz

The 2 KiB output-projection weight matrix moved from one RAMB18E2 to 320 RAMD64E leaf cells, grouped into RAM64M and RAM64M8 macros. The full routed inventories have identical names and primitive types for the other 1,582 memory cells and macros.

| Routed resource | Block RAM design | LUTRAM design |
| --- | ---: | ---: |
| LUTs | 34,516 | 34,913 |
| Registers | 13,581 | 13,588 |
| DSPs | 37 | 37 |
| Block RAM tiles | 38 | 37.5 |
| Projection logic LUTs | 241 | 318 |
| Projection LUTRAM LUTs | 10 | 330 |
| Projection registers | 78 | 82 |

The candidate met the same 20 ns constraint with +4.482 ns setup and +0.028 ns hold slack, versus +4.019 ns and +0.012 ns for the control. These are the worst slack values across the whole design. The target weight-to-operand register path could not be isolated in the routed netlists because the named operand register endpoints were unavailable. Vivado reported complete routing and timing coverage with no design-rule errors or critical warnings.

The original remote checksum matched the resumed Mac archive. All 318 original members, both memory inventories and the programming image and overlay were verified.

[Run record](run.json) · [Independent build audit](audit-manifest.json) · [RTL comparison](../output-projection-lutram-rtl-20261117T152505Z/findings.md)
