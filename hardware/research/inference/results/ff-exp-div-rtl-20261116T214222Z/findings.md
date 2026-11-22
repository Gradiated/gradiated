# Fixed-denominator feed-forward division in simulation

The three exponential divisions use the original two-bit recurrence with a known prefix remainder. They take 3, 4 and 16 digit clocks, with the original finish clock after each. The prior circuit took 32 digit clocks for each division. The exact guard retains that full path when the prefix is too large.

The component checks passed 17,310 signed quotient and remainder cases and 3,040 scalar interface events. The latter include 1,679 exponential commands, 588 generic divide commands, 771 legal table writes and two resets. The fixtures exercised even and odd ties, INT64_MIN, both signs of interpolation with legal tables, cancellation and output stalls. The inherited scalar implementation and exact division oracle agreed for the command responses.

## Whole-request cycles

| Prompt | Adopted eight-lane control | Feed-forward divider candidate | Reduction |
| --- | ---: | ---: | ---: |
| Hello | 7,799,105 | 6,855,361 | 12.1% |
| Six-byte prompt | 11,611,357 | 10,349,917 | 10.9% |
| 48-byte prompt | 20,482,387 | 18,604,243 | 9.2% |

Both circuits passed all seven exact model cases, including cache values, retained scores, output IDs, stop conditions and legacy BOS checks. The control also reproduced the archived AXI observations and timing files. Feed-forward processing fell from 34,306 to 24,962 clocks per processed position, a saving of 9,344 clocks, or 0.18688 ms at 50 MHz. Only FF_WAIT changed. The first-output, last-output, prefix and terminal savings follow their respective processed-position counts.

The cycle results describe the simulated circuit. Routed timing, board latency and module energy are covered by their own evidence.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-ff-exp-div-v1.md)
