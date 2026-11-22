# Exact attention exponential replay

The candidate replaces the three fixed-divisor calls made by each non-cutoff attention exponential. The scalar harness checked 17,310 signed divider rows and 3,040 interface rows, including ties, reset, backpressure and rejection of oversized table words. The first fixture attempt stopped when the unchanged interface rejected out-of-range input. Its source and failure are retained with the corrected replay.

Across seven cases and 716 processed positions, exact scores, token outputs, cache values and cache timing schedules matched. Each complete exponential saved 73 clock cycles. Only the attention wait phase changed. The probability divider executed the same number of steps.

| Prompt | Adopted control cycles | Candidate cycles | Fewer cycles |
| --- | ---: | ---: | ---: |
| Hello | 6,128,767 | 5,387,671 | 12.09% |
| Six-byte prompt | 9,236,437 | 7,913,385 | 14.32% |
| 48-byte prompt | 16,535,149 | 13,663,329 | 17.37% |

These are exact RTL simulation counters for the frozen inputs. The board timing and energy have separate gates.

[Run record](run.json) · [Independent simulation audit](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-attention-exp-div-v1.md)
