# Faster exact attention exponentials on the KV260

The adopted attention cache pipeline and specialised attention divider ran the same frozen model and schedule at 50 MHz across three paired blocks on one KV260. Exact diagnostics, 36 timed requests, 18 warm-ups and all first, last and completion cycle counters passed. The original research circuit and weights were restored and all 320 BOS scores matched.

## Speed

Each row reports medians from six timed requests per arm, from the board's CPU-side observer. One output token is one byte in this model.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 8.831 → 8.617 (-2.42%) | 792.3 → 908.2 (+14.63%) | 122.831 → 107.991 (-12.08%) |
| Six-byte prompt | 10.479 → 10.205 (-2.62%) | 701.5 → 824.8 (+17.59%) | 184.962 → 158.492 (-14.31%) |
| 48-byte prompt | 113.841 → 99.991 (-12.17%) | 479.6 → 599.6 (+25.03%) | 331.199 → 273.762 (-17.34%) |

The candidate saves 73 cycles in every complete attention exponential by using the fixed divisor 45,426. The cache schedule and the probability division were retained. All 108 first, last and terminal counters matched the exact RTL timing. [Matched RTL replay](../attention-exp-div-rtl-20261117T131434Z/findings.md)

## Energy and resources

Gross VCC_SOM energy per verified answer averaged 0.663 J with the adopted control and 0.560 J with the specialised candidate. Relative changes in the three paired blocks were -15.5%, -15.7%, -15.4%. Gross energy per useful output token averaged 0.006298 J and 0.005320 J, respectively. Mean active module-rail power was 3.104 W and 3.100 W. Across all paired sample-alignment checks, the energy changes ranged from -15.7% to -15.4%. The integration window includes the gaps between requests and their final verification. Both arms ran with the separate USB 2 and USB 3 companion hubs absent. The reported energy covers the module rail on this boot. Whole-board input energy and long-run behaviour remain unmeasured. See the SPI1 counter checks below for background peripheral activity.

See the [routed resource and timing report](../attention-exp-div-build-20261117T130122Z/findings.md) for the fixed-clock implementation comparison. [Build record label correction](../attention-exp-div-build-20261117T130122Z/metadata-correction.md)

Two 64 KiB serial probes passed before the verified full transfer. The board’s UART, original circuit and measured peripheral topology were checked after staging and again after restoration.

## SPI1 and TPM activity

| Arm | SPI1 active time change, ms | TPM transfer change | Before / after observation gaps, ms |
| --- | ---: | ---: | ---: |
| p1-candidate | 0 | 0 | 0.200 / 0.015 |
| p1-control | 0 | 0 | 0.211 / 0.017 |
| p2-candidate | 0 | 0 | 0.182 / 0.018 |
| p2-control | 1282 | 0 | 0.190 / 0.019 |
| p3-candidate | 0 | 0 | 0.187 / 0.019 |
| p3-control | 0 | 0 | 0.185 / 0.035 |

The counter reads bracket each active energy window, with observation gaps below 0.22 ms on each side. No arm registered a new TPM transfer. SPI1 active time increased in the second control arm only. Pairs one and three had zero deltas on both arms and showed 15.52% and 15.44% lower module energy per answer. The counter cannot quantify SPI1's energy contribution. All six blocks remain in the comparison.

The supplementary post-restore capture differed from the final gate in the previously diagnosed SPI1 clock rows. UART counters and all original circuit and frequency checks agreed. [SPI1 diagnosis](../../devices/kv260-spi1-clock-diagnosis.md)

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-attention-exp-div-v1.md)
