# Four versus eight final-score lanes on the KV260

Both circuits ran the same frozen model and schedule at 50 MHz across three paired blocks on one KV260 boot. Exact diagnostics, 36 timed requests, 18 warm-ups and all first, last and completion cycle counters passed. The original research circuit and weights were restored and all 320 BOS scores matched.

## Speed

Each row reports medians from six timed requests per arm, from the board's CPU-side observer. One output token is one byte in this model.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 11.879 → 11.851 (−0.24%) | 614.9 → 625.3 (+1.7%) | 158.711 → 156.235 (-1.6%) |
| Six-byte prompt | 14.104 → 14.091 (−0.09%) | 551.9 → 560.3 (+1.5%) | 235.814 → 232.483 (-1.4%) |
| 48-byte prompt | 145.715 → 145.693 (−0.02%) | 389.9 → 394.1 (+1.1%) | 413.004 → 410.152 (-0.7%) |

One final projection took 3,040 cycles with four lanes and 1,680 cycles with eight lanes. Saving 1,360 cycles per scored position at 50 MHz is equivalent to 0.0272 ms. The matched RTL replay attributes the change to final scoring. Positions that skip scoring receive no circuit-cycle saving. [Matched RTL replay](../logits-eight-rtl-20261116T190922Z/findings.md)

## Energy and resources

Gross VCC_SOM energy per verified answer averaged 0.844 J with four lanes and 0.837 J with eight lanes. Relative changes in the three paired blocks were -1.0%, -1.0%, -0.7%. Gross energy per useful output token averaged 0.008017 J and 0.007944 J, respectively. Mean active module-rail power was 3.129 W and 3.134 W. The window includes the gaps between requests and their final verification. It covers the module rail. Whole-board input energy and long-run behaviour remain unmeasured. All five timestamp alignments for all three pairs show a reduction, ranging from 0.63% to 1.05%. The eight-lane run delivered shorter verified blocks at nearly the same average power.

The eight-lane build uses four more DSPs. Both builds use 38 block RAM tiles. The eight weight banks use one 36-Kibit RAM primitive each, compared with two per bank in the four-lane build. Scoring hierarchy LUTs rise from 672 to 1,131. The whole-design increase is 393 LUTs. See the [routed resource and timing report](../logits-8-lanes-build-20261116T190809Z/findings.md).

The first serial transfer stopped when the Mac entered idle sleep. The measured run used a fresh packet and kept the same circuit images and measurement protocol. [Initial transport stop](../logits-8-lanes-20261116T193809Z-a9fdf0-transfer-aborted/findings.md)

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-logits-8-lanes-v1.md)
