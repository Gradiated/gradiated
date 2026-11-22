# Routed attention cache pipeline at 50 MHz

The candidate met the 20 ns clock period with +3.815 ns setup slack and +0.013 ns hold slack. Vivado reported full timing coverage, a complete route and no design-rule errors or critical warnings.

| Routed resources | Adopted down-projection circuit | Attention cache pipeline |
| --- | ---: | ---: |
| LUTs | 34,799 | 34,769 |
| Registers | 13,648 | 13,652 |
| DSPs | 37 | 37 |
| Block RAM tiles | 38 | 38 |
| Attention LUTs | 5,898 | 5,874 |
| Attention registers | 1,406 | 1,409 |
| Attention DSPs | 5 | 5 |
| Attention RAMB18 blocks | 2 | 2 |
| Attention RAMB36 blocks | 0 | 0 |

The result retains eight DSPs and the eight weight memory banks in the final score projection. The attention scheduler overlaps each next eligible cache request with the current arithmetic. The synthesis comparison separately shows the whole circuit and the attention hierarchy.

All 318 archived files, the programming image and the loading overlay passed their pin checks and independent review.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Exact RTL replay](../attention-cache-pipeline-rtl-20261117T105443Z/findings.md)
