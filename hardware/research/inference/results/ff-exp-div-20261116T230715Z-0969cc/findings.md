# Exact feed-forward division on the KV260

The adopted `logits-8-lanes-v1` and candidate `ff-exp-div-v1` ran the same frozen model and schedule at 50 MHz across three paired blocks on one KV260 boot. Exact diagnostics, 36 timed requests, 18 warm-ups and all first, last and completion cycle counters passed. The original research circuit and weights were restored and all 320 BOS scores matched.

## Speed

Each row reports medians from six timed requests per arm, from the board's CPU-side observer. One output token is one byte in this model.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 11.870 → 9.805 (-17.40%) | 625.3 → 708.1 (+13.23%) | 156.254 → 137.369 (-12.09%) |
| Six-byte prompt | 14.087 → 11.654 (-17.28%) | 560.3 → 625.8 (+11.69%) | 232.479 → 207.245 (-10.85%) |
| 48-byte prompt | 145.713 → 127.555 (-12.46%) | 394.1 → 425.4 (+7.95%) | 410.175 → 372.578 (-9.17%) |

Each processed position took 34,306 feed-forward cycles with the control and 24,962 with the candidate. The 9,344-cycle saving equals 0.18688 ms at 50 MHz. First output benefits at every processed prompt position, and the saving repeats as generation continues. The seven exact simulations attributed the change to feed-forward processing. [Matched RTL replay](../ff-exp-div-rtl-20261116T214222Z/findings.md)

## Energy and resources

Gross VCC_SOM energy per verified answer averaged 0.831 J with the adopted control and 0.745 J with the divider candidate. Relative changes in the three paired blocks were -10.8%, -10.2%, -10.3%. Gross energy per useful output token averaged 0.007892 J and 0.007068 J, respectively. Mean active module-rail power was 3.113 W and 3.105 W. Across all paired sample-alignment checks, the energy changes ranged from -10.8% to -10.2%. The window includes the gaps between requests and their final verification. The board's separate USB 2 peripheral hub was absent for both arms. Both arms shared this peripheral state. The energy figures cover the module rail in this run. Whole-board input energy and long-run behaviour remain unmeasured.

On this workload the exact division shortcut cut request time and module energy while preserving every checked output. The complete routed design used 403 fewer LUTs and 43 fewer registers, with 37 DSPs and 38 block RAM tiles in both circuits. See the [routed resource and timing report](../ff-exp-div-build-20261116T213813Z/findings.md) for the fixed-clock implementation comparison.

The serial path passed two exact 64 KiB canaries, all group and member checks for the full archive, then fresh UART and board health checks before dispatch and after restoration. The first interrupted transfer and blocked retry remain in their separate records.

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-ff-exp-div-v1.md)
