# Exact feed-forward divider in the routed design

The candidate placed and routed at 50 MHz, with +4.148 ns setup slack and +0.018 ns hold slack. Vivado reported complete timing coverage, no routing gaps and no DRC errors or critical warnings.

| Routed resources | Adopted eight-lane control | Feed-forward divider |
| --- | ---: | ---: |
| LUTs | 35,188 | 34,785 |
| Registers | 13,689 | 13,646 |
| DSP blocks | 37 | 37 |
| Block RAM tiles | 38 | 38 |

The final token-score projection retains eight DSPs and all eight weight memory banks. The feed-forward scalar clone retains the original restoring recurrence and changes only how its three exponential divisions begin. The table reports net chip-wide implementation results from independent routes at the same target.

All 318 recovered files and the programming image passed local and independent checks.

[Run record](run.json) · [Independent route audit](audit-manifest.json) · [Exact RTL simulation](../ff-exp-div-rtl-20261116T214222Z/findings.md) · [Adopted control build](../logits-8-lanes-build-20261116T190809Z/findings.md)
