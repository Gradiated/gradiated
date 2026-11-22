# Routed attention exponential divider at 50 MHz

The routed KV260 candidate met the 20 ns constraint with +4.019 ns setup slack and +0.012 ns hold slack. Vivado reported full timing coverage, complete routing and no design-rule errors or critical warnings.

| Routed resources | Adopted cache pipeline | Specialised attention exponential |
| --- | ---: | ---: |
| LUTs | 34,769 | 34,516 |
| Registers | 13,652 | 13,581 |
| DSPs | 37 | 37 |
| Block RAM tiles | 38 | 38 |
| Attention LUTs | 5,874 | 5,624 |
| Attention registers | 1,409 | 1,343 |
| Attention DSPs | 5 | 5 |
| Attention RAMB18 blocks | 2 | 2 |

All 318 archive members and the programmer image and overlay passed local and independent checksum and admission checks. The initial archive download timed out. Resuming the remote copy produced the complete original archive and matched its original checksum.

[Run record](run.json) · [Independent build audit](audit-manifest.json) · [Exact RTL replay](../attention-exp-div-rtl-20261117T131434Z/findings.md)
