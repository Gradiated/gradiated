# Experiment 18 · Shorten exact attention probability division

Compare the selected Experiment 13 circuit, `attention-exp-pair-v2` (A), with `probability-div-v1` (B) on the AMD Kria KV260. Both use the frozen W16A16 `chip-joke-text-20261109` transformer, on-chip weights and a 50 MHz clock. The control firmware SHA-256 is `a44cc30cad8db1844459470b63d2325b544dcef34709db88366bbc201409930d`. The routed control uses 38,329 LUTs, 14,464 flip-flops, 41 DSPs and 39 block RAM tiles. Experiments 14–17 form a separate DDR4 comparison. [Baseline selection and artifact pins](../implementations/kv260/README.md#selected-circuit-comparison-baseline) · [Experiment 13 physical measurements](../results/attention-exp-pair-v2-20261117T232821Z-e72da4/findings.md)

## Question and preregistered predictions

Each head computes the probability for each occupied cache position. Divide one exponential E, scaled by 32,768, by the positive sum S for that head. The head has already formed the complete sum, so 0 ≤ E ≤ S. The exact quotient before rounding fits in 16 unsigned bits, including the endpoint 32,768. Starting the radix-four division with the high prefix of its dividend in the remainder lets it skip 24 of 32 steps. Preserve the exact remainder, round-to-nearest rule, tie behaviour, result width, error handling and arithmetic for other operations. Compare one change to the divider schedule. The number of heads, exponentials, weights, memory placement, KV accesses, host loop, output contract and workload remain fixed.

In the baseline traces each additional position incurs two divisions, one per head. The predicted saving is 48 FPGA clocks times the occupied length for one position. Both scored and intermediate prompt positions run attention. The following predictions assume no extra setup or retirement clocks and continued closure at 50 MHz. Test the assumptions and retain deviations. [Cache-depth reconstruction and full data](kv260-attention-context-cost-v1/findings.md)

| Occupied positions | Reconstructed baseline clocks for one scored position | Predicted clocks saved | Predicted candidate clocks |
| ---: | ---: | ---: | ---: |
| 1 | 38,081 | 48 | 38,033 |
| 16 | 41,947 | 768 | 41,179 |
| 64 | 54,474 | 3,072 | 51,402 |
| 128 | 71,177 | 6,144 | 65,033 |
| 256 | 104,585 | 12,288 | 92,297 |

| Complete request | Experiment 13 clocks | Predicted saving | Predicted candidate clocks |
| --- | ---: | ---: | ---: |
| Hello | 5,142,970 | 247,248 (4.81%) | 4,895,722 |
| Six-byte prompt | 7,475,095 | 440,640 (5.89%) | 7,034,455 |
| 48-byte prompt | 12,716,857 | 974,448 (7.66%) | 11,742,409 |

## Qualification and physical comparison

Prove the initial remainder and first unprocessed bits are exactly those of the original divider after 24 steps. Check zero, equality, near-equality, high bits, quotient/remainder limits, positive and negative rounding tests where the shared unit supports them, ties and neighbouring cases, invalid and unrelated commands, stalls and resets. Replay both arms through the seven frozen model cases. Require identical numerical intermediates, scores, output, termination and cache checkpoints. Use per-position divider and stage clocks to audit where the savings occur and reconcile totals. Keep scored-position reconstructions separate from simulated entire requests and physical timings. Allow 25 minutes per complete replay. Verify the exact prior control route and the candidate's source/build pins, setup and hold closure, clock and primitive counts. Use the existing Vivado host. Allow 42 minutes to route, three to package and 20 for resumable artifact recovery. Preserve unsuccessful attempts.

Use the [measurement standard](measurement-standard-v2.md) and matched A1/B1/B2/A2 physical sessions with A → B → A image loads. Use both arms' resident weights, the same on-board autonomous software, outputs and timing boundaries. Reopen and load before each block, outside timed requests and power windows. Smoke each prompt after each of the three loads. In each session run two mixed blocks (three warm-ups and six timed replies each), then one block per prompt (one warm-up and 18 Hello, 12 six-byte or eight 48-byte timed replies). Pair rounds 1 and 2 in forward prompt order for A1/B1 and rounds 3 and 4 in reverse for B2/A2. Total: nine smoke, 36 warm-up and 200 timed replies across 20 powered blocks. Bound each request to five seconds and require smoke replies under five-thirds of a second. Allow 30 minutes for measurement and reserve a separate three minutes for restoration. Transfer time is outside the measurement budget.

Verify expected replies and stops, exact control first/last/done FPGA counters and independently qualified candidate counters. Report per-prompt TTFT, decode tokens/s, completion, FPGA clocks and paired variation. Record whole-design and relevant hierarchical resources, implementation timing, setup, temperature, matched idle/active watts and gross VCC_SOM joules per reply and output token, tokens/J, alignment sensitivity and peripheral brackets. Report absolute values and effect sizes. Use one board owner and the original admitted boot state. Terminate on incorrect output, bad state, unqualified timing or unsafe recovery. Restore and verify the original research circuit and weights including all 320 BOS scores. Leave the restored board running. Save raw evidence locally on the Mac, checksums and separate research records. Baseline adoption is a separate decision.
