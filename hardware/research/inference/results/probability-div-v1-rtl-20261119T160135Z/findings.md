# Eight-step exact attention probability division

Both RTL arms matched in seven full-model cases covering 716 processed positions, 135,322 probabilities, 103,360 autonomous scores and 4,480 legacy BOS scores. Ordered attention scores, exponentials, running sums, raw quotients and remainders, rounded probabilities, cache addresses and checkpoints, output bytes and stops matched. The control reproduced the pinned Experiment 13 traces. All 21 phase counters reconciled, with every saved cycle in attention.

| Request | Control clocks | Candidate clocks | Fewer clocks |
| --- | ---: | ---: | ---: |
| Hello | 5,142,970 | 4,895,722 | 247,248 (4.81%) |
| Six bytes | 7,475,095 | 7,034,455 | 440,640 (5.89%) |
| 48 bytes | 12,716,857 | 11,742,409 | 974,448 (7.66%) |
| BOS only | 38,081 | 38,033 | 48 (0.13%) |
| Hello, cap 0 | 416,191 | 413,023 | 3,168 (0.76%) |
| Hello, cap 1 | 416,191 | 413,023 | 3,168 (0.76%) |
| Full 256-position context | 17,829,940 | 16,250,932 | 1,579,008 (8.86%) |

Each probability uses 32 radix-four steps on the control and eight on the candidate. The entire wait, including rounding, handoff and retirement, drops from 35 to 11 clocks. The read and launch each still use one clock. The occupied-depth sweep below measures one position of the 256-position replay. Attention includes score calculation and context mixing.

| Occupied positions | Divisions | Control probability wait | Candidate probability wait | Control attention clocks | Candidate attention clocks |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 70 | 22 | 438 | 390 |
| 16 | 32 | 1,120 | 352 | 4,304 | 3,536 |
| 64 | 128 | 4,480 | 1,408 | 16,831 | 13,759 |
| 128 | 256 | 8,960 | 2,816 | 33,534 | 27,390 |
| 256 | 512 | 17,920 | 5,632 | 66,942 | 54,654 |

The scalar bench passed 6,363 oracle rows, including 4,152 valid probability cases, 104 full-path divisions, 81 invalid divisions and 1,899 other commands. It covered zero and full scale, both tie parities, cutoff and shift limits, signed minimum magnitude, held results and reset during division. The attention fixture checked exact intermediates and context for nine requests and verified zero-sum rejection and recovery from a reset during probability division. Only probability uses divide commands on the opted-in scalar in this circuit. A future caller of that scalar would also take the eight-step path whenever its nonnegative numerator has a prefix below the divisor.

Local effort covered the implementation, two paired replays and directed benches. The exact replay and directed stages took under two minutes each after setup. The initial replay used Python 3.9 and stopped at a comparison helper. The first standalone bench sampled readiness before the table signal settled. The final checks used Python 3.13 and the corrected testbench. AI usage and human time were unavailable.

[Run record](run.json) · [Integer proof](../../implementations/kv260/variants/probability-div-v1/README.md) · [Protocol](../../experiments/kv260-probability-div-v1.md)
