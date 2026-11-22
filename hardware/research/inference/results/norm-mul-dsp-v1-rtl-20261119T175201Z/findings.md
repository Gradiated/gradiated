# Dedicated five-cycle normalization multipliers in RTL

Both arms matched on seven full-model cases and 716 processed positions. Checks covered 219,096 exact raw normalization products, 68,736 normalization outputs, 103,360 autonomous scores and 4,480 legacy BOS scores. Cache values and addresses, feed-forward and attention intermediates, emitted bytes and stopping rules matched.

| Request | Control clocks | Candidate clocks | Fewer clocks |
| --- | ---: | ---: | ---: |
| Hello | 4,469,098 | 4,129,132 | 339,966 (7.61%) |
| Six bytes | 6,464,215 | 6,009,805 | 454,410 (7.03%) |
| 48 bytes | 10,893,385 | 10,216,819 | 676,566 (6.21%) |
| BOS only | 33,809 | 30,443 | 3,366 (9.96%) |
| Hello, cap 0 | 366,559 | 329,533 | 37,026 (10.10%) |
| Hello, cap 1 | 366,559 | 329,533 | 37,026 (10.10%) |
| Full 256-position context | 15,169,588 | 14,307,892 | 861,696 (5.68%) |

| Prompt | First useful byte, clocks | Last useful byte, clocks | First-to-last, clocks |
| --- | ---: | ---: | ---: |
| Hello | 366,559 → 329,533 | 4,414,039 → 4,077,439 | 4,047,480 → 3,747,906 |
| Six bytes | 435,665 → 391,907 | 6,401,864 → 5,950,820 | 5,966,199 → 5,558,913 |
| 48 bytes | 4,107,453 → 3,780,951 | 10,816,976 → 10,143,776 | 6,709,523 → 6,362,825 |

At every occupied depth, each of norm1, norm2 and normfinal performed 96 direct products and six reciprocal-square-root products. No two normalization multipliers operated in the same model clock. The wait dropped from 2,063 to 941 clocks per phase. The full 3,366 clocks saved per processed position reached the request boundary, including positions where the vocabulary projection was skipped. All 21 phase counters reconciled, and the differences were confined to the three normalization waits.

The scalar bench matched 10,890 oracle rows, including 9,013 explicit raw products and 317 reciprocal-square-root commands. It checked output stalls, five direct-multiply cancellation points, and cancellation and reload at each of the five states of all six nested products. Development effort included the exact paired replay and directed suite. Human attention and AI usage costs are unknown.

[Run record](run.json) · [Implementation and proof](../../implementations/kv260/variants/norm-mul-dsp-v1/README.md) · [Protocol](../../experiments/kv260-norm-mul-dsp-v1.md)
