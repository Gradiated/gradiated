# Where the feed-forward block spends its cycles

The observation-only replay used the adopted eight-lane inference circuit. All 716 processed positions across seven exact cases showed the same feed-forward schedule. The original AXI events, BOS scores, cache snapshots and phase counters were byte-identical. The original harness also verified the retained scores, generated tokens and stop conditions.

## Cycles per processed position

| Feed-forward controller work | Cycles | Share of feed-forward time |
| --- | ---: | ---: |
| Gate and up pair collection | 193 | 0.6% |
| Exponential command | 15,744 | 45.9% |
| Sigmoid division command | 4,608 | 13.4% |
| Gating and hidden multiplies and shifts | 5,376 | 15.7% |
| Store hidden values | 128 | 0.4% |
| Launch down projection | 1 | <0.1% |
| Down projection | 8,256 | 24.1% |
| **Feed-forward processing** | **34,306** | **100%** |

The parent `FF_START` handshake took one separate clock. The 32 normalised input transfers occurred inside `N2_WAIT`, which also performs normalisation. No input, launch, scalar command, scalar result or down projection output was blocked. Weight loading and both legacy BOS checks are outside the timed window.

| Natural prompt | Processed positions | Feed-forward cycles | Complete request cycles |
| --- | ---: | ---: | ---: |
| Hello | 101 | 3,464,906 | 7,799,105 |
| Six-byte prompt | 135 | 4,631,310 | 11,611,357 |
| 48-byte prompt | 201 | 6,895,506 | 20,482,387 |

## What is exposed on the schedule

The exponential spends 12,672 cycles dividing by the same constant, 45,426. Range reduction, table address calculation and interpolation each account for 4,224 of those cycles. The separate sigmoid division uses a variable denominator and takes another 4,224 divider cycles. Together the internal division states occupy 49.3% of feed-forward cycles. These counts follow the actual arithmetic states, with handshake and other command clocks accounted for separately.

The gate and up projections each perform 8,320 read, multiply-accumulate and rounding clocks. They operate together. Of those clocks, 8,255 overlap the scalar send or wait states and only 65 occur while the controller waits for a pair. Gate and up each separately hold completed row results for 17,399 clocks. The controller handles the previous row during those held-result clocks. Eliminating the 65 visible arithmetic clocks would save under 0.1% of any of the three complete requests under the current schedule.

The down projection starts once the hidden values are ready. Its 8,256 cycles are 4,096 operand reads, 4,096 multiply-accumulates, 32 rounding clocks and 32 output handshakes. They sit on the schedule after the scalar work.

## Candidate for the next decision

First consider replacing the three fixed-denominator divisions inside the feed-forward exponential with exact arithmetic specialised for 45,426. Check quotient, remainder, rounding, sign and branch boundaries across supported inputs before comparing the original seven full-model cases. Limit the comparison to this feed-forward instance because other sublayers also use the scalar module. A candidate should show fewer exponential-substate clocks with exact output and cache parity and unchanged unaffected phase counts.

Deleting every observed exponential division clock would save at most 12,672 clocks per processed position, or 36.9% of feed-forward time. That is a ceiling of 12.4–16.4% of the three complete simulated requests under the current schedule. Any exact replacement retains computation and may expose gate/up work that is currently hidden, so its actual effect requires a separate replay.

Overlapping operand reads with accumulation in the down projection is the next distinct candidate. Its current reads account for at most 4,096 exposed clocks per position. Keeping one starting read for each of the 32 rows and hiding the other reads gives an analytical target of 4,064 fewer clocks per position. Actual savings and timing depend on a separately verified implementation. The cycle diagnostic concludes here. Routed timing, board latency and energy require separate evidence.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Diagnostic protocol](../../experiments/kv260-feed-forward-profile-v1.md)
