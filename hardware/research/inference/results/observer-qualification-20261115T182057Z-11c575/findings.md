# KV260 observation-counter qualification

The reviewed physical sequence completed. The original circuit was restored, the pinned original weights were reloaded, and all 320 original BOS scores matched. All 57 conditioned requests matched the frozen references, covering 2,656,960 signed-score comparisons on the board. The Mac independently checked the compact reference receipts, all 14 returned gates and all six power traces. Initial and final original-model BOS checks each matched 320 scores.

**The counter circuit passed functional checks. Timing neutrality remains inconclusive.** One registered prompt-latency comparison exceeded the descriptive ±2% band. The raw result’s `passed` flag records operational and functional acceptance. The research run uses `inconclusive` to preserve the timing qualification limit.

## Original circuit versus observer

Both used the original software wrapper, unchanged frozen weights and 50 MHz clock. Three pairs ran in AB/BA/AB order, with six timed requests and three warm-ups per arm. Counter reads followed the entire power window and sampler exit.

| Pair | Generation change | Verified block change | Output bytes/s, original / observer | Gross VCC_SOM J/completion, original / observer |
| --- | ---: | ---: | ---: | ---: |
| 1 | -0.519% | -0.354% | 143.97 / 144.48 | 2.3224 / 2.3095 |
| 2 | -0.024% | -0.064% | 144.44 / 144.53 | 2.3084 / 2.3114 |
| 3 | -0.012% | +0.011% | 144.23 / 144.22 | 2.3168 / 2.3090 |

Pair 1’s `encoded-hello` median verified latency differed by −2.217%. Its two original-circuit generation intervals were 466.050 ms and 442.138 ms. The return-to-verified tails were 6.869 ms and 6.169 ms. This variation lies in generation, unlike the earlier verification-tail outlier. Its cause is unresolved. The observation does not demonstrate either a real observer speed-up or timing neutrality, and it has not been removed from the comparison.

All six traces contain 350 power readings with no missed slots. An independent calculation integrated each trace across five timing-alignment cases. These small module-energy differences do not establish an energy improvement or general chip efficiency. They exclude whole-board input power and cannot isolate FPGA-only power.

## What the counters measured

| Final request | Completed input positions | Core busy (ms) | Generation loop (ms) |
| --- | ---: | ---: | ---: |
| `encoded-max48` | 201 | 949.290 | 1040.224 |
| `encoded-fu2p2q` | 135 | 564.058 | 630.636 |
| `encoded-hello` | 101 | 392.433 | 442.598 |

These are three final-request snapshots, one per prompt. Three earlier smoke snapshots also passed. Busy time includes waiting for score transfers, so it is not pure arithmetic time. Phase counters sum exactly to busy cycles. Token, score and cache-transfer counts match the frozen schedule, with no fault or overflow. Other event counters overlap phases and must not be summed as independent time categories. Zero extra cache-wait bubbles do not imply zero memory-access cost.

The separate [routed build](../observer-build-20261115T180508Z/findings.md) adds 761 LUTs and 1,017 registers, with unchanged DSP and block-RAM usage. Resource usage is not physical silicon area.

## End state and next decision

All four planned switches completed. The temporary installed observer firmware file was removed after returning to the original image. The pinned original weights were reloaded and all 320 original BOS scores matched. This is functional restoration evidence, not a full weight-memory readback. The controller exited successfully. Raw captures, build assets, the frozen packet and the independent audit are on the Mac. No baseline source or model was replaced.

Roadmap steps 1–3 have reached the agreed bounded stopping point. No additional repetitions or circuit experiments were started to try to remove the timing caveat. Before step 4, decide together which experiments and measurements to prioritise and whether a stronger timing-neutrality qualification is needed.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Protocol](../../experiments/kv260-observer-v1.md) · [Handoff](../../experiments/kv260-steps-1-3-handoff.md)
