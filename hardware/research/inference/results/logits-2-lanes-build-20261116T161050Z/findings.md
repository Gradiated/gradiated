# Two-lane final token-score projection

The two-lane circuit placed and routed at 50 MHz, with +3.766 ns setup slack and +0.013 ns hold slack. Vivado reported full clock coverage, no routing gaps and no DRC errors or critical warnings.

| Routed resources | One lane | Two lanes |
| --- | ---: | ---: |
| LUTs | 34,547 | 34,603 |
| Registers | 13,123 | 13,202 |
| DSP blocks | 30 | 31 |
| Block RAM tiles | 36.5 | 38 |

The projection uses two DSPs and eight 36-Kibit block RAM primitives, split evenly across the two independently read weight banks. Both designs store the same 10,240 weights. The one-lane projection uses six 36-Kibit primitives and one 18-Kibit primitive.

All 318 archive members and the programmer image passed local and independent checks. Physical timing and energy are covered separately by the matched board protocol.

[Run record](run.json) · [Independent audit receipt](audit-manifest.json) · [Exact RTL simulations](../logits-lanes-rtl-20261116T161210Z/findings.md) · [One-lane routed build](../logits-pipeline-build-20261116T130030Z/findings.md)
