# Experiment 22 · Read ahead in three transformer projections

Compare three local changes with the adopted [Experiment 21 circuit](../implementations/kv260/README.md#selected-circuit-comparison-baseline). Fetch the next input and weight within the current row while accumulating the present product. Keep the prime for the first term, the final term and row boundaries explicit. Keep the frozen W16A16 model, weights, accumulation order, signed arithmetic, host, one-cycle synchronous memories and 50 MHz clock fixed.

## Isolate before combining

1. Run the exact control and three independent RTL variants. Change only the front-end query/key/value projection (one 96-row engine), the attention output projection (32 rows), or the paired feed-forward up and gate projections (two parallel 128-row engines consumed together). Preserve the existing down projection and final token-score pipeline.
2. Predict 31 read clocks removable per 32-term row before measurement: 2,976 for Q/K/V and 992 for attention output per processed position. For gate/up, distinguish earlier row availability from clocks actually spent waiting for both rows by the scalar consumer. Simultaneous work must be counted once. Measure per-stage, consumer wait and first/last/done changes. Reconcile effects per position and request.
3. After the three isolated tests, replay all three together. Compare observed request savings with the sum of isolated savings and investigate any discrepancy. If a stage saves negligible complete-request time or causes regression, replay a combination omitting it and document the choice before routing. Preserve each result. Attribute physical speed, power, resource use and timing to the design actually measured.
4. Use directed row-edge, address/data alignment, restart/reset and backpressure cases as applicable, plus the seven retained whole-model fixtures, including full context. Require identical scores, useful output, termination and cache contents, with expected changes in clocks. For hardware, use the selected combination's own RTL replay pins and the exact control from Experiment 21. Require timing closure and consistent synthesis inputs, resident memory, clock and host interfaces.

## Independent forecast before the replays

Blog Developer SOL checked the Experiment 21 gate/up trace. The scalar consumer waits 65 exposed clocks per position. If fetching ahead brings the first pair forward by 31 clocks and no later wait becomes visible, gate/up will save 31 clocks per position. Its two 128-row engines work at the same time. Adding the local savings for their rows would overstate the saving to a reply. The prediction for all three changes is 3,999 clocks per processed position.

| Natural prompt | Predicted clocks saved to first useful token | To last useful token | To completion |
| --- | ---: | ---: | ---: |
| Hello | 43,989 | 399,900 | 403,899 |
| Six bytes | 51,987 | 535,866 | 539,865 |
| 48 bytes | 387,903 | 799,800 | 803,799 |

These predictions use the encoded prompt for first output, all but the EOS-producing position for last useful output, and all processed positions for natural completion. Check the replay events independently for the capped and full-context cases.

## Physical comparison

Follow [measurement standard v2](measurement-standard-v2.md) and the [matched schedule](kv260-norm-mul-shared-v1.md). Use A1/B1/B2/A2, with nine smokes, 36 warm-ups and 200 timed requests in 20 powered blocks. Report per-prompt TTFT, decode tokens/s and completion, exact FPGA counters, gross mixed and single-prompt VCC_SOM energy per useful token and verified reply, tokens/J, idle and active watts, variation, observed failures, peripheral counters and temperature. Report routed LUTs, flip-flops, DSPs, BRAM and timing margins and compare memory use. Use standard software verification at the board and reconcile with RTL. Limit build to one selected candidate for a physical comparison, allowing a corrected attempt for a diagnosed failure. Bound each full RTL replay to 30 minutes, route to 42 minutes, packaging to three minutes, recoverable build export to 20 minutes and board measurements to 30 minutes plus three minutes for restoration. Preserve raw evidence on the Mac, restore original research firmware and weights, and verify all 320 original BOS scores and recorded board state. Stop after Experiment 22.
