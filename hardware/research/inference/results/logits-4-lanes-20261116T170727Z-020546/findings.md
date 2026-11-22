# One versus 4 final-score lanes on the KV260

Both circuits ran the same frozen model and schedule at 50 MHz across three paired blocks on one KV260. Exact diagnostics, 36 timed requests, 18 warm-ups and all first, last and completion cycle counters passed. The original research circuit and weights were restored and all 320 BOS scores matched.

## Speed

Each row reports medians from six timed requests per arm, from the board's CPU-side observer. One output token is one byte in this model.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 12.036 → 11.859 (-1.5%) | 558.8 → 614.9 (+10.0%) | 173.555 → 158.691 (-8.6%) |
| Six-byte prompt | 14.264 → 14.110 (-1.1%) | 506.3 → 551.9 (+9.0%) | 255.885 → 235.820 (-7.8%) |
| 48-byte prompt | 145.871 → 145.723 (-0.1%) | 366.6 → 389.9 (+6.4%) | 430.132 → 413.011 (-4.0%) |

One final projection took 11,200 cycles with one lane and 3,040 cycles with 4. Saving 8,160 cycles per scored position at 50 MHz is equivalent to 0.1632 ms. The matched RTL replay attributes the change to final scoring. Positions that skip scoring receive no circuit-cycle saving. [Matched RTL replay](../logits-lanes-rtl-20261116T161210Z/findings.md)

## Energy and resources

Gross VCC_SOM energy per verified answer averaged 0.896 J with one lane and 0.843 J with 4. Relative changes in the three paired blocks were -6.1%, -6.1%, -5.7%. Gross energy per useful output token averaged 0.008510 J and 0.008001 J, respectively. Mean active module-rail power was 3.121 W and 3.123 W. The window includes the gaps between requests and their final verification. It covers the module rail. Whole-board input energy and long-run behaviour remain unmeasured.

Each extra lane has a DSP and an independently readable weight bank. This changes how the same weights are grouped into physical block RAM. See the [routed resource and timing report](../logits-4-lanes-build-20261116T161510Z/findings.md).

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-logits-lanes-v1.md)
