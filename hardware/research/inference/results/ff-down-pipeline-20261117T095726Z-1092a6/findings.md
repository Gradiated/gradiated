# Overlap down-projection reads and arithmetic on the KV260

The adopted divider and down-projection pipeline ran the same frozen model and schedule at 50 MHz across three paired blocks on one KV260. Exact diagnostics, 36 timed requests, 18 warm-ups and all first, last and completion cycle counters passed. The original research circuit and weights were restored and all 320 BOS scores matched.

## Speed

Each row reports medians from six timed requests per arm, from the board's CPU-side observer. One output token is one byte in this model.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 9.795 → 8.890 (-9.24%) | 708.1 → 751.3 (+6.11%) | 137.360 → 129.139 (-5.98%) |
| Six-byte prompt | 11.654 → 10.579 (-9.22%) | 625.8 → 659.3 (+5.36%) | 207.245 → 196.254 (-5.30%) |
| 48-byte prompt | 127.557 → 119.675 (-6.18%) | 425.4 → 440.7 (+3.58%) | 372.581 → 356.246 (-4.38%) |

Each processed position took 24,962 feed-forward cycles with the control and 20,898 with the candidate. The 4,064-cycle saving equals 0.08128 ms at 50 MHz. First output benefits at every processed prompt position, and the saving repeats as generation continues. The seven exact simulations traced the savings to overlapping the next read with the current arithmetic in the down projection. [Matched RTL replay](../ff-down-rtl-20261117T000318Z/findings.md)

## Energy and resources

Gross VCC_SOM energy per verified answer averaged 0.745 J with the adopted control and 0.708 J with the pipelined candidate. Relative changes in the three paired blocks were -5.0%, -4.9%, -4.9%. Gross energy per useful output token averaged 0.007069 J and 0.006721 J, respectively. Mean active module-rail power was 3.105 W and 3.106 W. Across all paired sample-alignment checks, the energy changes ranged from -5.0% to -4.9%. The integration window includes the gaps between requests and their final verification. Both arms ran with the separate USB 2 and USB 3 companion hubs absent. The reported energy covers the module rail on this boot. Whole-board input energy and long-run behaviour remain unmeasured.

Overlapping reads and arithmetic cut the down projection from 8,256 to 4,192 clocks. That block uses six more LUTs and keeps the same 80 registers, two block RAMs and one DSP. The whole circuit adds 14 LUTs and two registers. The other stages still do the same work, so complete answers took 4.4–6.0% less time. Active module power was nearly the same, consistent with the energy saving coming from the shorter work interval. `ff-exp-div-v1` remains the selected comparison baseline. [Routed resource and timing report](../ff-down-pipeline-build-20261117T000146Z/findings.md)

The full original archive passed every UART group and member check before an intentional power cycle. After reboot, all 23 prior staged files matched their hashes. The new packet reused 19 files, transferred four boot-specific files and their manifest, and verified the complete staged content. On the measurement boot both 64 KiB serial probes and the checks before dispatch and after restoration passed. The earlier Experiment 8 link incidents remain in their separate records.

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-ff-down-pipeline-v1.md)
