# Overlap cache reads and attention arithmetic on the KV260

The adopted down-projection circuit and attention cache pipeline ran the same frozen model and schedule at 50 MHz across three paired blocks on one KV260. Exact diagnostics, 36 timed requests, 18 warm-ups and all first, last and completion cycle counters passed. The original research circuit and weights were restored and all 320 BOS scores matched.

## Speed

Each row reports medians from six timed requests per arm, from the board's CPU-side observer. One output token is one byte in this model. The first-token differences for the two shortest prompts were under 0.1 ms.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 8.883 → 8.828 (-0.61%) | 751.3 → 792.3 (+5.45%) | 129.131 → 122.829 (-4.88%) |
| Six-byte prompt | 10.595 → 10.499 (-0.91%) | 659.3 → 701.5 (+6.39%) | 196.271 → 184.982 (-5.75%) |
| 48-byte prompt | 119.682 → 113.852 (-4.87%) | 440.7 → 479.6 (+8.83%) | 356.253 → 331.210 (-7.03%) |

The attention controller issues the next read during the current multiply-accumulate. The next request removes one clock from each overlapping term. The saving grows with occupied context: across both heads, the candidate hides 30 × length key-request clocks and 32 × (length − 1) value-request clocks. Both circuits use the same number of cache requests and perform the same arithmetic. All 108 first, last and terminal counters matched the exact RTL timing. [Matched RTL replay](../attention-cache-pipeline-rtl-20261117T105443Z/findings.md)

## Energy and resources

Gross VCC_SOM energy per verified answer averaged 0.709 J with the adopted control and 0.663 J with the pipelined candidate. Relative changes in the three paired blocks were -6.7%, -6.6%, -6.1%. Gross energy per useful output token averaged 0.006733 J and 0.006297 J, respectively. Mean active module-rail power was 3.111 W and 3.103 W. Across all paired sample-alignment checks, the energy changes ranged from -6.7% to -6.1%. The integration window includes the gaps between requests and their final verification. Both arms ran with the separate USB 2 and USB 3 companion hubs absent. The reported energy covers the module rail on this boot. Whole-board input energy and long-run behaviour remain unmeasured. SPI1 was disabled at every before-arm boundary and in five of six after-arm captures. It was enabled after the third candidate block. The first two paired energy reductions were 6.73% and 6.57%. The snapshots cannot establish whether the SPI1 activity overlapped the third energy window.

See the [routed resource and timing report](../attention-cache-pipeline-build-20261117T105651Z/findings.md) for the fixed-clock implementation comparison.

Two 64 KiB serial probes passed before the verified full transfer. The board’s UART, original circuit and measured peripheral topology were checked after staging and again after restoration. Both supplementary post-restore snapshots showed a different SPI1 clock enable/count state from the restore gate. All clock rates, including the 50 MHz inference clock, agreed. The cause of the SPI1 activity was unconfirmed.

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-attention-cache-pipeline-v1.md)
