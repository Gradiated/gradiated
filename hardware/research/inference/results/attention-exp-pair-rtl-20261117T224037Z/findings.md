# Two exponentials per attention head in RTL

The same seven model cases and 716 processed positions matched, including the full 256-position context. Ordered scores, exponentials, running sums, probabilities, returned scores, output bytes and cache checkpoints were exact. All non-attention model phase counts stayed fixed.

| Prompt | Adopted clock count | Two-unit clock count | Fewer clocks |
| --- | ---: | ---: | ---: |
| Hello | 5,387,671 | 5,142,970 | 4.54% |
| Six bytes | 7,913,385 | 7,475,095 | 5.54% |
| 48 bytes | 13,663,329 | 12,716,857 | 6.93% |

The directed fixture independently checked 33,344 signed products, 1,042 scores, exponentials and probabilities, and 288 context values. It includes both mixed cutoff orders, the exact cutoff and its neighbours, odd and full lengths, rejected and accepted table writes, and cancellation with the second unit still running.

The Hello request spent 518,202 clocks in the serial exponential schedule and 273,501 with two units. Both units were actively calculating in 239,568 of those 273,501 clocks. One-position heads use the original single-unit schedule. The occupancy record preserves every context length.

[Run record](run.json) · [Protocol](../../experiments/kv260-attention-exp-pair-v1.md)
