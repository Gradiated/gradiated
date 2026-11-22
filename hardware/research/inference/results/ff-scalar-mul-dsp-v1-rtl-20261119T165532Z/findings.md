# Five-cycle feed-forward scalar multiplication in RTL

Both arms matched across seven full-model cases and 716 processed positions. The comparison covered 274,944 exact 128-bit products, 103,360 autonomous scores and 4,480 legacy BOS scores. The feed-forward intermediates, attention arithmetic, cache contents and ordered cache reads, output bytes and stopping rules matched.

| Request | Control clocks | Candidate clocks | Fewer clocks |
| --- | ---: | ---: | ---: |
| Hello | 4,895,722 | 4,469,098 | 426,624 (8.71%) |
| Six bytes | 7,034,455 | 6,464,215 | 570,240 (8.11%) |
| 48 bytes | 11,742,409 | 10,893,385 | 849,024 (7.23%) |
| BOS only | 38,033 | 33,809 | 4,224 (11.11%) |
| Hello, cap 0 | 413,023 | 366,559 | 46,464 (11.25%) |
| Hello, cap 1 | 413,023 | 366,559 | 46,464 (11.25%) |
| Full 256-position context | 16,250,932 | 15,169,588 | 1,081,344 (6.65%) |

| Prompt | First useful byte, clocks | First-to-last useful byte, clocks |
| --- | ---: | ---: |
| Hello | 413,023 → 366,559 | 4,423,416 → 4,047,480 |
| Six bytes | 490,577 → 435,665 | 6,477,303 → 5,966,199 |
| 48 bytes | 4,517,181 → 4,107,453 | 7,144,595 → 6,709,523 |

Each position performed 128 products for exponential interpolation, 128 for the gate, and 128 for the hidden value. Feed-forward wait fell from 20,898 to 16,674 clocks at every occupied depth. Gate/up pair readiness contributed 65 wait clocks per position in each arm. Each multiplication saved 11 clocks, so all 4,224 clocks per position reached the request boundary. All 21 phase counters reconciled and the retained down-projection schedule matched.

The scalar oracle passed 10,890 rows. Direct multiplication contributed 9,013 full-width raw products, including 4,745 overflow rejections. The bench exercised output backpressure, each of the five new arithmetic states under reset, signed-minimum inputs and unrelated scalar operations. Pipeline and full-model checks verified the same source pin.

A duplicate bench monitor variable blocked the first replay compile. The scoped replay monitor name resolved it. The candidate RTL pin was the same for the final tests. Human attention and AI usage cost were unavailable.

[Run record](run.json) · [Integer proof](../../implementations/kv260/variants/ff-scalar-mul-dsp-v1/README.md) · [Protocol](../../experiments/kv260-scalar-product-opportunity-v1.md)
