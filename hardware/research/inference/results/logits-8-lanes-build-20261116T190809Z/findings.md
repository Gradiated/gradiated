# Eight-lane final scoring in the routed design

The eight-lane design routed at the 50 MHz target, with +2.747 ns setup slack and +0.011 ns hold slack. Vivado reported complete timing coverage, no routing gaps and no DRC errors or critical warnings.

| Routed resources | Four lanes | Eight lanes |
| --- | ---: | ---: |
| LUTs | 34,795 | 35,188 |
| Registers | 13,367 | 13,689 |
| DSP blocks | 33 | 37 |
| Block RAM tiles | 38 | 38 |

The scoring projection uses eight DSPs. Its eight independently read weight banks map to 8 36-Kibit and 0 18-Kibit RAM primitives. The primitive counts per bank are 1, 1, 1, 1, 1, 1, 1, 1. Both designs store the same 10,240 signed weights. The physical comparison measures performance and module energy separately.

All 318 archive members and the programmer image passed local and independent checks. The fixed-target route provides evidence at 50 MHz.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Exact RTL simulation](../logits-eight-rtl-20261116T190922Z/findings.md) · [Four-lane routed control](../logits-4-lanes-build-20261116T161510Z/findings.md)
