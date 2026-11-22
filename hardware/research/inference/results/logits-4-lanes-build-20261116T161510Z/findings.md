# Four-lane final token-score projection

The four-lane circuit placed and routed at 50 MHz, with +4.776 ns setup slack and +0.018 ns hold slack. Vivado reported complete timing coverage, no routing gaps and no DRC errors or critical warnings.

| Routed resources | One lane | Two lanes | Four lanes |
| --- | ---: | ---: | ---: |
| LUTs | 34,547 | 34,603 | 34,795 |
| Registers | 13,123 | 13,202 | 13,367 |
| DSP blocks | 30 | 31 | 33 |
| Block RAM tiles | 36.5 | 38 | 38 |

The projection maps to four DSP blocks, 8 36-Kibit RAM primitives and 0 18-Kibit RAM primitives. Four banks hold the same 10,240 weights and support simultaneous reads.

All 318 recovered files and the programming image passed local and independent checks. The matched board protocol covers physical performance separately.

[Run record](run.json) · [Independent audit receipt](audit-manifest.json) · [Exact RTL simulations](../logits-lanes-rtl-20261116T161210Z/findings.md) · [Two-lane routed build](../logits-2-lanes-build-20261116T161050Z/findings.md)
