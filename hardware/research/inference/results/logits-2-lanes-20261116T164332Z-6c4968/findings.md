# One versus 2 final-score lanes on the KV260

Both circuits ran the same frozen model and schedule at 50 MHz across three paired blocks on one KV260. Exact diagnostics, 36 timed requests, 18 warm-ups and all first, last and completion cycle counters passed. The original research circuit and weights were restored and all 320 BOS scores matched.

## Speed

Each row reports medians from six timed requests per arm, from the board's CPU-side observer. One output token is one byte in this model.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 12.034 → 11.954 (-0.7%) | 558.8 → 595.0 (+6.5%) | 173.554 → 163.681 (-5.7%) |
| Six-byte prompt | 14.284 → 14.177 (-0.8%) | 506.3 → 535.8 (+5.8%) | 255.905 → 242.524 (-5.2%) |
| 48-byte prompt | 145.880 → 145.773 (-0.1%) | 366.6 → 381.8 (+4.2%) | 430.141 → 418.719 (-2.7%) |

One final projection took 11,200 cycles with one lane and 5,760 cycles with 2. Saving 5,440 cycles per scored position at 50 MHz is equivalent to 0.1088 ms. The matched RTL replay attributes the change to final scoring. Positions that skip scoring receive no circuit-cycle saving. [Matched RTL replay](../logits-lanes-rtl-20261116T161210Z/findings.md)

## Energy and resources

Gross VCC_SOM energy per verified answer averaged 0.897 J with one lane and 0.862 J with 2. Relative changes in the three paired blocks were -4.0%, -3.6%, -4.3%. Gross energy per useful output token averaged 0.008521 J and 0.008181 J, respectively. Mean active module-rail power was 3.124 W and 3.125 W. The window includes the gaps between requests and their final verification. It covers the module rail. Whole-board input energy and long-run behaviour remain unmeasured.

Each extra lane has a DSP and an independently readable weight bank. This changes how the same weights are grouped into physical block RAM. See the [routed resource and timing report](../logits-2-lanes-build-20261116T161050Z/findings.md).

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-logits-lanes-v1.md)
