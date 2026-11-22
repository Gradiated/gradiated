# Experiment 20 · Give each normalisation stage a five-clock multiplier

Compare the selected Experiment 19 circuit, `ff-scalar-mul-dsp-v1` (A), with `norm-mul-dsp-v1` (B). Keep the five-clock feed-forward multiplier in both arms. Replace only the multiplier used in each of the three RMSNorm instances. Each gets its own copy of the same exact partial-product datapath. Preserve reciprocal-square-root iterations, sign checks, rounding, accumulator widths, lookup tables and other operations. The [multiplier profile](kv260-scalar-multiply-opportunity-v1/findings.md) identified normalisation as the next exposed wait. [Control pins](../implementations/kv260/README.md#selected-circuit-comparison-baseline)

Each 32-coordinate normalisation performs 96 direct products and six products within reciprocal square root on the standard prompts. Removing 11 clocks per product predicts 1,122 fewer clocks per stage, or 3,366 per processed position. Check all three phases in simulation before routing. The following are predicted internal completion counts, with inputs and outputs unchanged.

| Prompt | Positions | Experiment 19 | Clocks saved | Experiment 20 forecast |
| --- | ---: | ---: | ---: | ---: |
| Hello | 101 | 4,469,098 | 339,966 | 4,129,132 |
| Six bytes | 135 | 6,464,215 | 454,410 | 6,009,805 |
| 48 bytes | 201 | 10,893,385 | 676,566 | 10,216,819 |

First-token savings are 3,366 times the encoded prompt length (11, 13 or 97). First-to-last decode savings follow the number of intervals between useful output tokens. Proceed to hardware when simulation verifies the exact transformation and meaningful request savings on the standard prompts. Inspect what Vivado actually maps: each normalisation multiplier may grow from four to 16 DSPs, but routing and synthesis can change the count. Measure the board energy effect.

## Qualification and measurement

Keep the model, weights, numerical contract, resident on-chip memories, host software and clock target fixed. Qualify reset, output stalls, overflow and signed full-width products against an independent oracle. Replay all seven frozen fixtures, including the full context. Check the reference products, scores, cache, emitted tokens, termination and first/last/done clocks. Allow 30 minutes per full replay. Pin the exact inputs, generated RTL, routed firmware and overlay, and account for DSPs in each affected instance and across the design. Require routed setup and hold closure at 50 MHz. Bound the existing Vivado route to 42 minutes, packaging to three minutes and resumable archive recovery to 20 minutes.

Use the [standard measurements](measurement-standard-v2.md) and [matched schedule](kv260-probability-div-v1.md) for each physical comparison separately. Run A1/B1/B2/A2 with nine smoke checks, 36 warm-ups and 200 timed replies in 20 powered blocks. Report absolute board-side TTFT, decode tokens/s, completion, module power and gross joules per verified reply and token alongside paired variation and resource costs. Note peripheral activity and measurement limits. Allow 30 minutes on the board for measurement and three more for restoration. Restore the original research firmware and weights and verify all 320 original BOS scores and board state after each experiment. Preserve raw evidence on the Mac, including unsuccessful attempts.
