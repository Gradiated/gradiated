# Read-ahead projections in RTL

All six arms matched on the seven frozen cases, including the full context. Each arm checked 103,360 autonomous scores, 4,480 legacy BOS scores and 274,944 ordered projection rows. Per-term read addresses, cache values and addresses, attention, shared-normalization and feed-forward numerical traces, output bytes and stops matched.

| Isolated change | Read-only clocks removed per row | Exposed clocks saved per position |
| --- | ---: | ---: |
| Q/K/V, 96 rows | 31 | 2,976 |
| Attention output, 32 rows | 31 | 992 |
| Feed-forward gate and up, two parallel 128-row lanes | 31 per lane | 31 |

The feed-forward consumer's initial pair wait fell from 65 to 34 clocks. No later pair delayed the consumer. The read-ahead gate and up lanes each held their later results for 3,937 more clocks per position. The combined 3,999-clock saving matched the sum of the isolated effects at every measured boundary. Front-end wait moved from 6,690 to 3,714 clocks, output projection wait from 2,112 to 1,120, and feed-forward wait from 16,674 to 16,643. All other top-level phase counts matched.

| Request | Exp21 control, clocks | Q/K/V and output, clocks | All three, clocks | All-three reduction |
| --- | ---: | ---: | ---: | ---: |
| Hello | 4,129,132 | 3,728,364 | 3,725,233 | 9.78% |
| Six bytes | 6,009,805 | 5,474,125 | 5,469,940 | 8.98% |
| 48 bytes | 10,216,819 | 9,419,251 | 9,413,020 | 7.87% |
| BOS only | 30,443 | 26,475 | 26,444 | 13.14% |
| Hello, cap 0 | 329,533 | 285,885 | 285,544 | 13.35% |
| Hello, cap 1 | 329,533 | 285,885 | 285,544 | 13.35% |
| Full 256-position context | 14,307,892 | 13,292,084 | 13,284,148 | 7.16% |

| Prompt | First useful byte, clocks | Last useful byte, clocks |
| --- | ---: | ---: |
| Hello | 329,533 → 285,544 | 4,077,439 → 3,677,539 |
| Six bytes | 391,907 → 339,920 | 5,950,820 → 5,414,954 |
| 48 bytes | 3,780,951 → 3,393,048 | 10,143,776 → 9,343,976 |

The selected route includes all three scopes. The gate/up change adds 31 exposed clocks of savings per position to the Q/K/V and output arm with the same single read port and MAC in each lane. The omission arm preserves the option to trade the marginal savings for simpler RTL scope. Across caps and EOS the saved clocks follow the number of completed positions at each boundary. Cap-zero cases retain absent first and last output counters. The one-byte cap retains equal first, last and completion counters.

Directed tests checked 196,608 ordered signed products and running sums, 6,144 row results, and 24 cancellations with fresh restarts. Tests covered ties in both signs, clipping, row-edge addressing, rejecting invalid load indices, backpressure and reset at the next row's prime. Human attention and AI usage costs were unavailable.

[Run record](run.json) · [Implementation and reproduction](../../implementations/kv260/variants/projections-read-ahead-v1/README.md) · [Protocol](../../experiments/kv260-projections-read-ahead-v1.md)
