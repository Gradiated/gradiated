# Routed down-projection pipeline at 50 MHz

The candidate placed and routed at 50 MHz, with +4.929 ns setup slack and +0.017 ns hold slack. Vivado reported complete timing coverage, no routing gaps and no DRC errors or critical warnings.

| Routed resources | Adopted divider control | Down-projection pipeline |
| --- | ---: | ---: |
| LUTs | 34,785 | 34,799 |
| Registers | 13,646 | 13,648 |
| DSP blocks | 37 | 37 |
| Block RAM tiles | 38 | 38 |

The final token-score projection retains eight DSPs and all eight weight memory banks. The down projection preserves the original ordered arithmetic and overlaps the next operand read with the current accumulation. The table reports net chip-wide implementation results from independent routes at the same target.

Within the down projection itself, routed use changed from 324 to 330 LUTs and from 80 to 80 registers. The hierarchy retained 2 36-Kibit block RAMs and 1 DSP block.

All 318 recovered files and the programming image passed local and independent checks.

[Run record](run.json) · [Independent route audit](audit-manifest.json) · [Exact RTL simulation](../ff-down-rtl-20261117T000318Z/findings.md) · [Adopted control build](../ff-exp-div-build-20261116T213813Z/findings.md)
